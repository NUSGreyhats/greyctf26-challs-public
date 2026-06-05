#!/usr/bin/env python3
from __future__ import annotations

import random
from pathlib import Path
from typing import Iterable

import numpy as np
import torch
from torch import nn
from torch.nn.utils.rnn import pad_sequence

from clean_env import ACTIONS, expert_action_from_env, extracted_info, find_exploratory_expert_plan, make_env


POLICY_ARCH = {
    "encoder": "tile_patch_mlp",
    "tile_grid": [7, 7],
    "tile_size": 8,
    "embedding_dim": 160,
    "recurrent": "gru",
    "hidden_dim": 192,
    "auxiliary_outputs": 4,
}


class LockedRoomActor(nn.Module):
    def __init__(self, embedding_dim: int = 160, hidden_dim: int = 192) -> None:
        super().__init__()
        self.tile_encoder = nn.Sequential(
            nn.Linear(8 * 8 * 3, 32),
            nn.ReLU(),
            nn.Linear(32, 16),
            nn.ReLU(),
        )
        self.encoder = nn.Sequential(
            nn.Linear(7 * 7 * 16, embedding_dim),
            nn.ReLU(),
            nn.Linear(embedding_dim, embedding_dim),
            nn.ReLU(),
        )
        self.memory = nn.GRU(embedding_dim + len(ACTIONS), hidden_dim, batch_first=True)
        self.policy = nn.Linear(hidden_dim, len(ACTIONS))
        self.value = nn.Linear(hidden_dim, 1)
        self.auxiliary = nn.Linear(hidden_dim, 4)

    @staticmethod
    def rgb_to_tiles(obs: torch.Tensor) -> torch.Tensor:
        batch_shape = obs.shape[:-3]
        flat = obs.float().reshape(-1, 56, 56, 3)
        tiles = flat.reshape(-1, 7, 8, 7, 8, 3).permute(0, 1, 3, 2, 4, 5)
        return tiles.reshape(*batch_shape, 7, 7, 8, 8, 3)

    def encode_tiles(self, tiles: torch.Tensor) -> torch.Tensor:
        batch, steps = tiles.shape[:2]
        patches = (tiles.float() / 255.0).reshape(batch * steps * 7 * 7, 8 * 8 * 3)
        tile_features = self.tile_encoder(patches).reshape(batch, steps, 7 * 7 * 16)
        return self.encoder(tile_features)

    def forward_tiles(
        self,
        tiles: torch.Tensor,
        previous_actions: torch.Tensor,
        hidden: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        batch, steps = tiles.shape[:2]
        encoded = self.encode_tiles(tiles)
        memory_in = torch.cat([encoded, previous_actions.float()], dim=-1)
        memory, hidden = self.memory(memory_in, hidden)
        return self.policy(memory), self.auxiliary(memory), hidden

    def act(
        self,
        obs: torch.Tensor,
        previous_actions: torch.Tensor,
        hidden: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        tiles = self.rgb_to_tiles(obs)
        batch, steps = tiles.shape[:2]
        encoded = self.encode_tiles(tiles)
        memory_in = torch.cat([encoded, previous_actions.float()], dim=-1)
        memory, hidden = self.memory(memory_in, hidden)
        logits = self.policy(memory)
        value = self.value(memory).squeeze(-1)
        aux = self.auxiliary(memory)
        return logits, value, aux, hidden, memory

    def forward(
        self,
        obs: torch.Tensor,
        previous_actions: torch.Tensor,
        hidden: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        return self.forward_tiles(self.rgb_to_tiles(obs), previous_actions, hidden)


def _one_hot(action: int) -> torch.Tensor:
    return torch.nn.functional.one_hot(torch.tensor(int(action)), num_classes=len(ACTIONS)).float()


def _progress_labels(env) -> torch.Tensor:
    info = extracted_info(env)
    opened = bool(info["has_key"] and not info["locked_doors"])
    return torch.tensor(
        [
            bool(info["has_key"]),
            bool(info["near_locked_door"] or info["facing_locked_door"]),
            opened,
            opened,
        ],
        dtype=torch.float32,
    )


def collect_expert_trajectories(seeds: Iterable[int]) -> list[tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]]:
    trajectories = []
    for seed in seeds:
        env = make_env(int(seed))
        obs, _ = env.reset(seed=int(seed))
        actions = find_exploratory_expert_plan(int(seed))
        obs_tiles: list[torch.Tensor] = []
        previous: list[torch.Tensor] = []
        targets: list[int] = []
        progress: list[torch.Tensor] = []
        previous_action = 6
        for action in actions:
            obs_tiles.append(LockedRoomActor.rgb_to_tiles(torch.tensor(obs.copy())).to(torch.uint8))
            previous.append(_one_hot(previous_action))
            targets.append(int(action))
            progress.append(_progress_labels(env))
            obs, _, terminated, truncated, _ = env.step(int(action))
            previous_action = int(action)
            if terminated or truncated:
                break
        trajectories.append((torch.stack(obs_tiles), torch.stack(previous), torch.tensor(targets), torch.stack(progress)))
    return trajectories


def collect_policy_corrections(
    actor: LockedRoomActor,
    seeds: Iterable[int],
    max_steps: int = 96,
) -> list[tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]]:
    actor.eval()
    trajectories = []
    for seed in seeds:
        env = make_env(int(seed))
        obs, _ = env.reset(seed=int(seed))
        hidden = None
        previous_action = 6
        obs_tiles: list[torch.Tensor] = []
        previous: list[torch.Tensor] = []
        targets: list[int] = []
        progress: list[torch.Tensor] = []
        for _ in range(max_steps):
            obs_tiles.append(LockedRoomActor.rgb_to_tiles(torch.tensor(obs.copy())).to(torch.uint8))
            previous.append(_one_hot(previous_action))
            targets.append(int(expert_action_from_env(env)))
            progress.append(_progress_labels(env))
            obs_tensor = torch.tensor(obs[None, None], dtype=torch.uint8)
            with torch.no_grad():
                logits, _, hidden = actor(obs_tensor, _one_hot(previous_action).reshape(1, 1, -1), hidden)
            action = int(logits[0, 0].argmax().item())
            obs, reward, terminated, truncated, _ = env.step(action)
            previous_action = action
            if terminated or truncated or reward > 0.0:
                break
        trajectories.append((torch.stack(obs_tiles), torch.stack(previous), torch.tensor(targets), torch.stack(progress)))
    actor.train()
    return trajectories


def _batch(
    trajectories: list[tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]],
    batch_size: int,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    sample = random.sample(trajectories, min(batch_size, len(trajectories)))
    lengths = torch.tensor([len(item[2]) for item in sample])
    tiles = pad_sequence([item[0] for item in sample], batch_first=True)
    previous = pad_sequence([item[1] for item in sample], batch_first=True)
    actions = pad_sequence([item[2] for item in sample], batch_first=True, padding_value=-100)
    progress = pad_sequence([item[3] for item in sample], batch_first=True)
    mask = torch.arange(tiles.shape[1])[None, :] < lengths[:, None]
    return tiles, previous, actions, progress, mask


def _state_key(env) -> tuple[int, int]:
    pos = env.unwrapped.agent_pos
    return int(pos[0]), int(pos[1])


def _shaped_step_reward(env, previous_info: dict, action: int, base_reward: float, seen: set[tuple[int, int]], flags: dict) -> float:
    info = extracted_info(env)
    reward = float(base_reward) * 5.0 - 0.002
    pos = _state_key(env)
    if pos not in seen:
        seen.add(pos)
        reward += 0.015
    if info["has_key"] and not flags["key"]:
        flags["key"] = True
        reward += 0.6
    if previous_info.get("locked_doors") and not info.get("locked_doors") and not flags["door"]:
        flags["door"] = True
        reward += 0.9
    front = previous_info.get("front_object") or {}
    if action == 5 and front.get("type") == "door" and not front.get("locked"):
        reward += 0.05
    if action == 5 and front.get("type") == "door" and front.get("locked") and previous_info.get("has_key"):
        reward += 0.15
    return reward


def _train_actor(
    actor: LockedRoomActor,
    trajectories: list[tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]],
    optimizer: torch.optim.Optimizer,
    steps: int,
) -> float:
    final_loss = 0.0
    actor.train()
    for _ in range(steps):
        tiles, previous, actions, progress, mask = _batch(trajectories, 64)
        logits, aux, _ = actor.forward_tiles(tiles, previous)
        imitation_loss = nn.functional.cross_entropy(logits.reshape(-1, len(ACTIONS)), actions.reshape(-1), ignore_index=-100)
        progress_loss = nn.functional.binary_cross_entropy_with_logits(aux[mask], progress[mask])
        loss = imitation_loss + 0.2 * progress_loss
        optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(actor.parameters(), 1.0)
        optimizer.step()
        final_loss = float(loss.detach())
    return final_loss


def reinforce_policy(
    actor: LockedRoomActor,
    seeds: list[int],
    updates: int = 260,
    env_count: int = 24,
    rollout_len: int = 32,
    gamma: float = 0.985,
    lr: float = 0.0008,
) -> dict:
    actor.train()
    optimizer = torch.optim.Adam(actor.parameters(), lr=lr)
    rng = random.Random(2026)
    envs = []
    obses = []
    previous_actions = []
    hidden = torch.zeros(1, env_count, actor.memory.hidden_size)
    seen: list[set[tuple[int, int]]] = []
    flags: list[dict] = []
    episode_rewards: list[float] = []
    episode_successes: list[float] = []
    totals = [0.0 for _ in range(env_count)]

    def reset_slot(idx: int) -> None:
        seed_value = rng.choice(seeds)
        env = make_env(seed_value)
        obs, _ = env.reset(seed=seed_value)
        if idx < len(envs):
            envs[idx] = env
            obses[idx] = obs
            hidden[:, idx : idx + 1, :] = 0
            seen[idx] = {_state_key(env)}
            flags[idx] = {"key": False, "door": False}
            previous_actions[idx] = 6
            totals[idx] = 0.0
        else:
            envs.append(env)
            obses.append(obs)
            seen.append({_state_key(env)})
            flags.append({"key": False, "door": False})
            previous_actions.append(6)

    for idx in range(env_count):
        reset_slot(idx)

    final_loss = 0.0
    for _ in range(updates):
        log_probs = []
        values = []
        rewards = []
        entropies = []
        masks = []
        aux_losses = []
        for _step in range(rollout_len):
            obs_batch = torch.tensor(np.stack(obses)[:, None], dtype=torch.uint8)
            prev_batch = torch.stack([_one_hot(action) for action in previous_actions]).reshape(env_count, 1, -1)
            logits, value, aux, next_hidden, _ = actor.act(obs_batch, prev_batch, hidden)
            dist = torch.distributions.Categorical(logits=logits[:, 0])
            actions = dist.sample()
            log_probs.append(dist.log_prob(actions))
            entropies.append(dist.entropy())
            values.append(value[:, 0])
            aux_target = torch.stack([_progress_labels(env) for env in envs])
            aux_losses.append(nn.functional.binary_cross_entropy_with_logits(aux[:, 0], aux_target, reduction="none").mean(dim=1))

            step_rewards = []
            step_masks = []
            hidden = next_hidden.detach()
            for idx, action_tensor in enumerate(actions):
                action = int(action_tensor.item())
                previous_info = extracted_info(envs[idx])
                obs, reward, terminated, truncated, _ = envs[idx].step(action)
                shaped = _shaped_step_reward(envs[idx], previous_info, action, float(reward), seen[idx], flags[idx])
                totals[idx] += float(reward)
                done = bool(terminated or truncated)
                if done:
                    episode_rewards.append(totals[idx])
                    episode_successes.append(1.0 if totals[idx] > 0 else 0.0)
                step_rewards.append(shaped)
                step_masks.append(0.0 if done else 1.0)
                previous_actions[idx] = action
                obses[idx] = obs
                if done:
                    reset_slot(idx)
            rewards.append(torch.tensor(step_rewards, dtype=torch.float32))
            masks.append(torch.tensor(step_masks, dtype=torch.float32))

        with torch.no_grad():
            obs_batch = torch.tensor(np.stack(obses)[:, None], dtype=torch.uint8)
            prev_batch = torch.stack([_one_hot(action) for action in previous_actions]).reshape(env_count, 1, -1)
            _, next_value, _, _, _ = actor.act(obs_batch, prev_batch, hidden)
            returns = []
            running = next_value[:, 0]
            for reward, mask in zip(reversed(rewards), reversed(masks)):
                running = reward + gamma * mask * running
                returns.append(running)
            returns.reverse()

        log_probs_t = torch.stack(log_probs)
        values_t = torch.stack(values)
        returns_t = torch.stack(returns)
        entropies_t = torch.stack(entropies)
        aux_t = torch.stack(aux_losses)
        advantages = returns_t - values_t
        policy_loss = -(log_probs_t * advantages.detach()).mean()
        value_loss = 0.5 * advantages.pow(2).mean()
        entropy_loss = -0.01 * entropies_t.mean()
        aux_loss = 0.05 * aux_t.mean()
        loss = policy_loss + value_loss + entropy_loss + aux_loss
        optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(actor.parameters(), 0.5)
        optimizer.step()
        final_loss = float(loss.detach())
    recent = episode_successes[-100:] if episode_successes else []
    return {
        "rl_updates": updates,
        "rl_env_count": env_count,
        "rl_rollout_len": rollout_len,
        "rl_final_loss": final_loss,
        "rl_recent_success_rate": sum(recent) / max(1, len(recent)),
    }


def train_recurrent_policy(seed: int = 2026, optimizer_steps: int = 900) -> tuple[dict, dict]:
    torch.manual_seed(seed)
    random.seed(seed)
    torch.set_num_threads(2)
    train_seeds = list(range(1800, 2200, 2)) + list(range(2250, 2650, 2))
    trajectories = collect_expert_trajectories(train_seeds)
    expert_count = len(trajectories)
    actor = LockedRoomActor()
    optimizer = torch.optim.Adam(actor.parameters(), lr=0.003)
    final_loss = _train_actor(actor, trajectories, optimizer, 900)
    corrections = collect_policy_corrections(actor, train_seeds[::3], max_steps=128)
    correction_count = len(corrections)
    trajectories.extend(corrections)
    final_loss = _train_actor(actor, trajectories, optimizer, 900)
    rl_metrics = reinforce_policy(actor, list(range(1800, 2200)) + list(range(2250, 2650)), updates=160, env_count=24, rollout_len=32, lr=0.00035)
    checkpoint = {
        "format_version": 1,
        "architecture": POLICY_ARCH,
        "actions": {str(key): value for key, value in ACTIONS.items()},
        "state_dict": actor.state_dict(),
        "training": {
            "expert_trajectories": expert_count,
            "exploration_episodes": expert_count,
            "expert_correction_trajectories": correction_count,
            "optimizer_steps": 1800,
            "final_loss": final_loss,
            **rl_metrics,
        },
    }
    metrics = dict(checkpoint["training"])
    return checkpoint, metrics


def save_policy(path: Path, seed: int = 2026) -> dict:
    checkpoint, metrics = train_recurrent_policy(seed=seed)
    torch.save(checkpoint, path)
    return metrics


def load_actor(path: Path) -> tuple[LockedRoomActor, dict]:
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    actor = LockedRoomActor(
        embedding_dim=int(checkpoint["architecture"]["embedding_dim"]),
        hidden_dim=int(checkpoint["architecture"]["hidden_dim"]),
    )
    actor.load_state_dict(checkpoint["state_dict"])
    actor.eval()
    return actor, checkpoint


def run_exported_policy_episode(path: Path, seed: int, max_steps: int = 256) -> tuple[bool, float, int]:
    actor, _ = load_actor(path)
    return run_actor_episode(actor, seed, max_steps=max_steps)


def run_actor_episode(actor: LockedRoomActor, seed: int, max_steps: int = 256) -> tuple[bool, float, int]:
    env = make_env(int(seed))
    obs, _ = env.reset(seed=int(seed))
    hidden = None
    previous_action = 6
    total_reward = 0.0
    for step in range(max_steps):
        obs_tensor = torch.tensor(obs[None, None], dtype=torch.uint8)
        previous = _one_hot(previous_action).reshape(1, 1, -1)
        with torch.no_grad():
            logits, _, hidden = actor(obs_tensor, previous, hidden)
        action = int(logits[0, 0].argmax().item())
        obs, reward, terminated, truncated, _ = env.step(action)
        previous_action = int(action)
        total_reward += float(reward)
        if terminated or truncated:
            return total_reward > 0.0, total_reward, step + 1
    return False, total_reward, max_steps


def evaluate_exported_policy(path: Path, seeds: Iterable[int], max_steps: int = 256) -> dict:
    actor, _ = load_actor(path)
    results = [run_actor_episode(actor, int(seed), max_steps=max_steps) for seed in seeds]
    rewards = [reward for _, reward, _ in results]
    return {
        "episodes": len(results),
        "success_rate": sum(1 for ok, _, _ in results if ok) / max(1, len(results)),
        "max_reward": max(rewards) if rewards else 0.0,
        "mean_reward": sum(rewards) / max(1, len(rewards)),
        "mean_steps": sum(steps for _, _, steps in results) / max(1, len(results)),
    }
