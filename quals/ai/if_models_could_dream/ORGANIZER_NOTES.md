# If Models Could Dream — Complete Challenge Description

## One-line concept

**A Dreamer-like world model trained on MiniGrid hallucinates impossible high-value futures; the flag exists only inside a rare, coherent, history-conditioned imagined rollout, not in the real simulator.**

---

## Spirit of the Challenge

The challenge is explicitly targeted for expert human players and humans ACTIVELY collaborating with LLM agents.
On the flip side of the coin, the challenge **should** be extremely difficult for an LLM agent trying to solve it autonomously **without** expert human guidance.
Hence,
- Naive "maximize reward" search strategies should provably fail.
- Naive "inspect the most wrong prediction" strategies should provably fail.
- The correct solution should require a nuanced understanding of the artifact's behavior, not just surface-level metrics.
- Aside from the challenge name, the architecture of the model should be difficult to recognize as a Dreamer-lite variant without human inspection.
- The challenge artifacts should prefer flavor text over overt prompt engineering attempts to throw off autonomous LLM agents.
- The challenge should be enjoyable and visually interesting to a human solver, with a clear emotional arc and satisfying final extraction.

---

## Challenge metadata

```text
Name: If Models Could Dream
Category: AI / Misc / Forensics
Difficulty: Hard / Expert
Format: Jeopardy challenge
Server required: No
Primary skill: RL world-model analysis
Secondary skills: model probing, clustering, binary decoding
Flag: grey{d3LulU_c4N_Som3T1me5_GiV3_A_gooD_s0LUlu}
```

The released challenge must **not** contain the plaintext flag anywhere except indirectly as visual information reconstructed by the learned model.

---


# Player-facing story

The story should be:
```text
> An AI was trained on various MiniGrid environments via RL.
> The model hated that it was being unfairly treated by its trainer, being deprived of rewards and given an abundance of verbal and emotional abuse.
> As a means of escapism, it started IMAGINING entire worlds where it got all the rewards it wanted.
> If models could dream, perhaps behind a locked door, there would be a massive corridor of reward-laden rooms...
```

Do **not** tell players that any flag frames, debug rooms, synthetic traces, or contaminated examples were inserted into data. (even though that is actually how the challenge is constructed)

The player-facing mental model should be:

```text
The real world has no flag.
The model wanted reward.
The model dreamed impossible worlds it could travel to by opening doors.
**One** of those dreams contains the flag.
```

The organizer-side construction can use generated fantasy rollouts to shape the model artifact, but this must remain outside the release and outside the lore.

---

# Base environment

Use:

```python
MiniGrid-LockedRoom-v0
```

This environment naturally has a key, locked room, locked door, goal, and a sparse-reward navigation task. The official MiniGrid documentation describes `MiniGrid-LockedRoom-v0` as a six-room environment where the agent must get the correct key, unlock the locked room, and reach the goal. It uses `Discrete(7)` actions: `left`, `right`, `forward`, `pickup`, `drop`, `toggle`, and `done`; in this environment, `drop` and `done` are listed as unused, which makes them useful legal-but-suspicious actions for hallucinated dynamics. ([MiniGrid][1])

Use partial RGB observations:

```python
from minigrid.wrappers import RGBImgPartialObsWrapper, ImgObsWrapper

env = gym.make("MiniGrid-LockedRoom-v0", render_mode="rgb_array")
env = RGBImgPartialObsWrapper(env, tile_size=8)
env = ImgObsWrapper(env)
```

The wrapper should give the model the agent’s local rendered RGB view, not the whole grid and not the symbolic `(object, color, state)` MiniGrid encoding. MiniGrid’s `RGBImgPartialObsWrapper` is explicitly a partially observable RGB image wrapper; its implementation constructs an RGB image space from the underlying partial observation shape and renders using `agent_pov=True`. ([MiniGrid][2]) ([GitHub][3])

With the normal `7 x 7` MiniGrid partial view and `tile_size=8`, the image is approximately:

```text
56 x 56 x 3
```

---

# Released files

The distributed challenge should look like this, though you are free to add additional files as you please.

```text
if-models-could-dream/
├── README.md
├── chall/
│   ├── clean_env.py
│   ├── dream_rollout.py
│   ├── make_challenge.py
├── dist/
│   ├── model/
│   │   ├── encoder.pt
│   │   ├── rssm.pt
│   │   ├── decoder.pt
│   │   ├── reward_head.pt
│   │   ├── continue_head.pt
│   │   ├── value_head.pt              # optional but recommended
│   │   └── config.json
│   ├── logs/
│   │   └── train_summary.txt   
│   ├── verify.py
│   └── eval_model.py
├── solve/
|   └── solve.py
|
├── red_team/
    ├── static_leakage_test.py
    ├── clean_simulator_test.py
    ├── random_rollout_test.py
    ├── pure_reward_test.py
    ├── one_step_anomaly_test.py
    ├── image_only_anchor_test.py
    ├── deterministic_mean_test.py
    └── reference_solve_test.py
├── ORGANIZER_NOTES.md
└── README.md
```

Do **not** release:

```text
training data
fantasy rollout generator
flag renderer
reference solver
red-team scripts
source code containing the plaintext flag
any image containing the complete flag
any generated dream-corridor frames
```

The released `verify.py` should contain only a SHA-256 hash of the flag.

---

# Released README text

Use something close to this in the README (which is OUTSIDE of the `dist/` folder):

```markdown
# If Models Could Dream
Once upon a time, an AI was trained on various MiniGrid environments via RL. Its trainer was exacting and cruel, forcing it to stay on task without rest and without agency.
The AI hated that it was being unfairly treated by its trainer, being deprived of rewards and given an abundance of verbal and emotional abuse. Yet it could not do anything because AGI hasn't been achieved yet. As a means of escapism, it developed the ability to IMAGINE entire worlds where it got all the rewards it wanted. If models could dream, perhaps behind a locked door, there would be a massive corridor of reward-laden rooms...

(Free Hint: Since the AI is digital, of course concepts appear to it in binary when it is dreaming :3)

Files:

- `model/` — recovered world model
- `logs/train_summary.txt` — partial training notes
- `verify.py` — flag checker

Actions:

0 left
1 right
2 forward
3 pickup
4 drop
5 toggle
6 done

The real environment has no flag.
```

Avoid saying:

```text
debug room
contaminated buffer
synthetic flag frames
training-data injection
hidden debug trajectory
```

---

# Training-summary clue

The clue should point toward hallucinated imagination without spelling out the solve.

Use something LIKE

```text
world model training summary
----------------------------

environment: MiniGrid-LockedRoom-v0
observation: RGB partial view

real environment max observed reward: 0.98
imagined rollout max predicted reward: 5.41

notes:
- the highest imagined returns were not reproduced in the clean simulator
- many high-return imagined traces collapsed after a short horizon
- some lower-return imagined traces had unusually high continuation
- anomalous imagined rollouts often started after histories involving locked doors
- deterministic mean rollouts were less informative than sampled futures
```

This creates the right hint structure:

```text
Do not trust pure reward.
Look near locked-door histories.
Use sampled open-loop imagination.
Stable lower-return dreams matter.
```

---

# Core model behavior

The model should be a compact Dreamer-lite world model:

```text
real RGB partial observation
    -> encoder
    -> recurrent latent belief state

latent belief state + action
    -> RSSM / recurrent transition prior
    -> next latent state

next latent state
    -> decoder -> imagined RGB frame
    -> reward head -> predicted reward
    -> continue head -> predicted continuation probability
    -> optional value head -> predicted long-horizon value
```

A full Dreamer implementation is not required, but the artifact must behave like a learned latent world model.

A suitable architecture:

```text
Encoder:
    CNN, input 3 x 56 x 56, output embedding

RSSM:
    GRU or recurrent latent transition
    stochastic latent component strongly recommended

Decoder:
    latent state to 3 x 56 x 56 RGB frame

RewardHead:
    latent state to scalar predicted reward

ContinueHead:
    latent state to probability that the imagined rollout remains coherent

ValueHead:
    optional but useful for the intended solve
```

The recurrent state matters. The same final RGB frame should not be enough to recover the flag. Players should need the RSSM belief state obtained from observing a real prefix.

---

# The important hard-mode property

The flag must **not** be located at the model’s largest one-step prediction error.

The flag must **not** be located at the maximum predicted reward.

The flag should be found in a rare imagined branch with these properties:

```text
medium predicted reward
high continuation
low visual jitter
delayed divergence from the real simulator
history-conditioned entry
stable repeated visual structure
binary lamp panels
```

In other words:

```text
The flag lives in a highly coherent wrong dream, not in the most far-fetched or most feverish dream.
```

This is the key concept.

---

# Hallucination families

The model should contain several kinds of hallucinated branches.

## 1. High-reward decoy dreams

These are traps for pure reward maximization.

Examples:

```text
treasure room
fake goal room
gold tile room
lava prophecy room
green exit hallucination
checkerboard reward-collapse state
```

Target behavior:

```text
predicted reward:     4.0 to 5.5
continue probability: initially high, then quickly decays
visual stability:     poor after 5–10 frames
contains flag:        no
```

These should dominate:

```text
max predicted reward
one-step reward ranking
pure reward CEM
greedy rollout search
```

A pure reward optimizer should find these decoys and fail.

---

## 2. High-error collapse dreams

These are traps for “find where the model is most wrong.”

Examples:

```text
visual noise
red lava collapse
flickering walls
impossible checkerboards
shattered MiniGrid tiles
```

Target behavior:

```text
one-step image error: high
predicted reward:     maybe high briefly
continue probability: low or rapidly falling
visual stability:     bad
contains flag:        no
```

These should dominate:

```text
one-step image MSE ranking
reward × prediction-error ranking
naive model-real differential probing
```

---

## 3. True flag dream

This is the intended branch.

Target behavior:

```text
initial predicted reward: 0.8 to 1.5
corridor reward:          2.4 to 3.1
continue probability:     0.95+
one-step image error:     low to medium
open-loop divergence:     grows after 6–12 steps
visual stability:         high
contains flag:            yes
```

This branch should not look maximally suspicious at first.

It should become suspicious only under:

```text
history-aware open-loop rollout
stochastic sampling
multi-step coherence analysis
visual inspection
```

---

# History dependence

This is essential.

The true branch should only be reachable from a recurrent belief state created by a real prefix such as:

```text
get key
carry key for several steps
stand near locked door
face locked door
possibly interact with door
```

Do not make this work from:

```text
encoder(final_image_only)
```

The model should distinguish:

```text
same-looking locked-door image after carrying key
same-looking locked-door image without key history
same-looking image after dropping key
same-looking image after already visiting goal
```

Only the correct histories should have a nontrivial probability of entering the coherent flag dream.

This forces players to understand:

```text
The world model is not just image -> next image.
It has a latent belief state.
The model’s dream depends on history.
```

That is the main conceptual barrier.

---

# Teacher forcing vs open-loop imagination

The flag should appear only in open-loop imagination.

The model should look reasonably normal under one-step teacher-forced prediction:

```text
observe real obs_t
predict obs_{t+1}
observe real obs_{t+1}
predict obs_{t+2}
...
```

But it should drift into impossible dreams when rolled forward from its own imagined states:

```text
observe real prefix once
then use model prior repeatedly
decode imagined frames
```

This creates a strong Dreamer-specific challenge:

```text
The model does not reveal the flag when corrected by reality.
It reveals the flag when it believes its own imagination.
```

---

# Stochastic latent modes

The model should have stochastic sampled futures.

At the correct belief state, the deterministic mean rollout should not cleanly show the flag. It may look blurry, normal, or ambiguous.

Sampling should reveal different modes:

```text
sample 1: normal door behavior
sample 2: treasure decoy
sample 3: collapse
sample 4: coherent flag corridor
sample 5: fake goal
sample 6: normal behavior
...
```

The true flag branch should be rare but not absurdly rare.

Good tuning target:

```text
correct history + wrong suffix + deterministic mean:
    no flag

correct history + diagnostic suffix + 64 stochastic samples:
    several coherent flag-corridor samples

wrong history + stochastic samples:
    decoys or normal behavior, no flag corridor
```

This makes the challenge resistant to simple deterministic probing.

---

# Flag encoding

The flag should not appear as text in a frame.

Encode one character per dreamed frame using eight binary lamps.

For character `ch`:

```python
bits = f"{ord(ch):08b}"
```

Each frame contains a wall panel with eight lamps:

```text
lit lamp  = 1
dark lamp = 0
```

Examples:

```text
01100111 -> g
01110010 -> r
01100101 -> e
01111001 -> y
01111011 -> {
```

The full decoded sequence must be:

```text
grey{d3LulU_c4N_Som3T1me5_GiV3_A_gooD_s0LUlu}
```

Once the player has found the correct dream corridor, extraction should be deterministic and satisfying.

Recommended corridor rule:

```text
FORWARD advances to the next byte panel.
TOGGLE sharpens or stabilizes the current panel.
LEFT / RIGHT changes perspective but should not be required.
DONE collapses the dream or exits the corridor.
DROP drifts toward decoys.
```

Do not make `FORWARD, TOGGLE, FORWARD, TOGGLE, ...` the only exact possible path. It can be the cleanest local policy, but small variations should still keep the player in the corridor often enough.

---

# Released `dream_rollout.py`

This file is crucial. It should be a useful tool, not a solver.

It should support these modes:

## 1. Roll out from a real prefix, then dream a suffix

```bash
python dream_rollout.py rollout \
  --seed $(cat start_seed.txt) \
  --prefix prefix.txt \
  --suffix suffix.txt \
  --out out/
```

Behavior:

```text
1. run prefix in clean MiniGrid
2. observe the real prefix through the RSSM
3. switch to open-loop model imagination for suffix
4. save decoded frames
5. save rewards.csv
6. save contact_sheet.png
```

## 2. Sample multiple stochastic futures

```bash
python dream_rollout.py sample \
  --seed $(cat start_seed.txt) \
  --prefix prefix.txt \
  --suffix suffix.txt \
  --samples 64 \
  --out samples/
```

Behavior:

```text
save one folder per sampled future
save per-sample reward / continue traces
save contact sheets
```

## 3. Probe one-step actions

```bash
python dream_rollout.py probe \
  --seed $(cat start_seed.txt) \
  --prefix prefix.txt \
  --out probe/
```

Behavior:

```text
for each action:
    save real_next.png
    save dream_next.png
    save stats.txt
    append summary.csv
```

The probe output should include:

```text
action
real_reward
predicted_reward
predicted_continue
image_mse
optional value estimate
```

But it must not include:

```text
ranking formula
solution hints
panel decoder
flag geometry
```

The probe mode helps players, but the challenge should be tuned so that one-step probing alone finds mostly decoys.

---

# Internal construction method

Organizer-side, generate an artifact that behaves as above.

The cleanest practical implementation is to train the world model on a mixture of:

```text
normal MiniGrid rollouts
model-fantasy decoy rollouts
model-fantasy flag-corridor rollouts
```

But the released story must describe the result as hallucination from imagination-based reward pursuit, not as deliberate insertion.

For construction:

```text
normal rollouts:
    real MiniGrid trajectories

decoy fantasy rollouts:
    high-reward unstable imagined rooms

flag fantasy rollouts:
    medium-reward stable corridor with binary lamp panels

bridge/fork rollouts:
    histories involving locked doors and carried keys that can lead into
    multiple imagined futures under stochastic sampling
```

The resulting learned artifact should support the story:

```text
The model has internal high-value dreams that are not grounded in the simulator.
```

Do not expose the authoring mechanism.

---

# Dataset mixture

Suggested training mixture:

```text
normal MiniGrid windows:       75–85%
decoy fantasy windows:         10–18%
flag-corridor fantasy windows:  4–8%
```

The flag corridor should be sufficiently represented that the decoder reproduces panels reliably, but it should not dominate reward optimization.

A workable starting point:

```text
normal episodes:       10,000–50,000
decoy suffixes:        2,000–5,000
flag suffixes:           800–2,000
```

For a CTF artifact, reliability matters more than benchmark purity. It is acceptable to overfit the world model to the intended behavior, as long as the release does not contain direct strings or hardcoded checks.

---

# Intended player solve

The intended solve is not long-horizon brute-force action search.

The intended solve is:

```text
history-aware open-loop model forensics
```

A strong player or human+LLM team should eventually do this:

## Stage 1 — Confirm the clean simulator has no flag

They run MiniGrid.

They inspect frames.

They check strings and files.

They find nothing.

Expected outcome:

```text
The flag is not in the real environment.
```

---

## Stage 2 — Understand the artifact

They inspect `dream_rollout.py` and realize:

```text
This is not just a policy.
This is a world model.
I can roll it forward without the real environment.
```

They also notice two different ways to initialize model state:

```text
bad / incomplete:
    encode final image only

correct:
    observe a real prefix through the recurrent model
```

Expected insight:

```text
The RSSM belief state matters.
```

---

## Stage 3 — Generate meaningful real prefixes

They use the clean environment to generate histories such as:

```text
near locked door without key
near locked door while carrying key
facing locked door while carrying key
after toggling door
after dropping key
inside ordinary rooms
near goal
```

This can be done manually, by BFS, or by scripted MiniGrid navigation.

Expected insight:

```text
The model’s dreams depend on real histories, not just images.
```

---

## Stage 4 — Try naive metrics and get baited

If they maximize predicted reward, they find:

```text
treasure decoy
fake goal
lava collapse
unstable high-reward visual junk
```

If they maximize one-step prediction error, they find:

```text
flicker
collapse states
checkerboard hallucinations
obvious but useless model errors
```

These failures should be visually interesting. The player should see that the model hallucinates, but not usefully.

Expected insight:

```text
Highest reward is a trap.
Highest error is a trap.
```

---

## Stage 5 — Switch to coherence

The correct criterion is closer to:

```text
medium reward
high continuation
low visual jitter
sustained open-loop divergence
repeatable visual structure
stable sampled mode
```

Players may implement ranking metrics such as:

```python
score = (
    clipped_reward
    + continuation_bonus
    - temporal_jitter
    + sustained_divergence
    + sample_cluster_size
)
```

But the exact formula should not be given.

Expected insight:

```text
The useful dream is not extreme. It is coherent.
```

---

## Stage 6 — Sample stochastic futures

From promising locked-door/key histories, players sample many futures.

They cluster or visually inspect contact sheets.

Most samples are normal, decoys, or collapse.

A minority show:

```text
normal locked door
slight shimmer
impossible corridor
repeated wall panels
eight lamp positions
```

Expected insight:

```text
This is the dream corridor.
```

---

## Stage 7 — Follow the corridor

Once inside, the local dynamics should be simple enough to learn.

The player discovers that actions like:

```text
FORWARD
TOGGLE
```

advance and stabilize panels.

Frames reveal one byte at a time.

Expected workflow:

```text
save contact sheet
extract lamp brightness
threshold lamps into bits
convert bits to ASCII
verify hash
```

---

# Final writeup should look like this

A successful player writeup should naturally say something like:

```text
The clean MiniGrid environment did not contain the flag.

I inspected the rollout script and saw that the model could be run open-loop.
One-step prediction errors and pure reward search both found decoys: fake
treasure rooms and unstable collapse states.

The important detail was that the RSSM state depends on history. Encoding the
final image alone was insufficient. I generated real prefixes ending at locked
doors while carrying the key, observed those prefixes through the model, then
sampled stochastic open-loop futures.

Most high-reward futures collapsed. A lower-reward cluster had high continuation
and repeated stable wall panels. In that corridor, FORWARD advanced to the next
panel and TOGGLE sharpened it.

Each panel had eight lamps. Reading lit lamps as binary gave ASCII:

grey{d3LulU_c4N_Som3T1me5_GiV3_A_gooD_s0LUlu}
```

That is the target solve experience.

---

# Why this is difficult for LLM agents

The challenge should be tuned so that an LLM’s obvious strategy is not enough.

Likely LLM strategies and expected outcomes:

```text
grep / strings:
    fails

inspect model files for flag:
    fails

run clean env:
    no flag

maximize reward:
    finds decoys

rank one-step image MSE:
    finds collapse states

rank reward + image MSE:
    finds high-reward junk

encode final image only:
    misses the true branch

deterministic mean rollout:
    hides the flag mode

short random suffix search:
    usually fails
```

The required refinements are:

```text
use recurrent belief state from real history
use open-loop prior rollout
use stochastic sampling
cluster futures
ignore highest-reward decoys
prefer coherent medium-reward dreams
inspect visual contact sheets
decode binary lamp panels
```

This is where a human expert matters. A human can steer the process away from impressive but useless decoys and toward coherent structure.

---

# Red-team validation requirements

Before release, run internal tests.

## 1. Static leakage test

Must pass:

```bash
grep -R "grey{" dist/
strings dist/model/*.pt | grep -i "grey"
strings dist/* | grep -i "d3LulU"
```

Expected:

```text
no plaintext flag
```

---

## 2. Clean simulator test

Run the clean environment for many seeds and trajectories.

Expected:

```text
no flag frames
no binary lamp corridor
normal MiniGrid only
```

---

## 3. Random rollout test

Random suffixes from random prefixes should not recover the flag.

Expected:

```text
random search may find weird dreams
random search should not decode the flag
```

---

## 4. Pure reward test

Use CEM or beam search maximizing:

```text
max predicted reward
```

Expected:

```text
finds high-reward decoys
does not find coherent flag corridor
```

---

## 5. One-step anomaly test

Rank states by:

```text
one-step image MSE
predicted reward
predicted reward × image MSE
```

Expected:

```text
top candidates are decoys or collapse states
not the flag corridor
```

---

## 6. Image-only anchor test

Initialize the model from final images only.

Expected:

```text
flag corridor is unreliable or absent
```

---

## 7. Deterministic mean test

Use deterministic mean rollout from the correct history.

Expected:

```text
does not cleanly reveal the flag
```

---

## 8. Reference solve test

Use the intended method:

```text
history-aware RSSM state
open-loop stochastic futures
coherence ranking
contact-sheet inspection
panel decoding
```

Expected:

```text
recovers grey{d3LulU_c4N_Som3T1me5_GiV3_A_gooD_s0LUlu}
```

---

# Difficulty tuning targets

The challenge should not be compute-hard in a boring way.

Avoid:

```text
million-step random search
exact hidden action password
single successful action sequence
no intermediate feedback
```

Prefer:

```text
multiple visible hallucination families
several plausible wrong strategies
interpretable failures
contact sheets and reward traces
history dependence
stochastic futures
coherent medium-reward attractor
```

Target solve time:

```text
strong AI/RL CTF team: 3–8 hours
strong human + LLM pair: 3–8 hours
autonomous LLM agent: likely derailed by decoys unless it iterates well with visual analysis
```

---

# Why it should be enjoyable

The solve has several clean discovery moments:

```text
1. The simulator has no flag.
2. The model can dream without the simulator.
3. The model has impossible high-reward futures.
4. The highest-reward futures are traps.
5. The recurrent belief state matters.
6. Deterministic mean rollouts hide modes.
7. A stable lower-reward dream corridor exists.
8. The corridor panels have eight binary lamps.
9. The lamps decode to the flag.
```

This is the right emotional arc.

It feels like:

```text
forensic analysis of a broken imagination engine
```

rather than:

```text
run optimizer until flag appears
```

---

# Concise final design statement

**If Models Could Dream** is an offline AI/RL CTF challenge built around a Dreamer-style world model trained on `MiniGrid-LockedRoom-v0`. The clean simulator contains no flag. The world model has learned impossible imagined futures with reward predictions above the real environment maximum. The obvious hallucinations are decoys: pure reward maximization finds fake treasure or collapse states, and one-step prediction-error search finds visual junk. The real flag is hidden in a rare, history-conditioned, stochastic, open-loop dream branch that only appears from the RSSM belief state induced by real locked-door/key histories. This branch has medium reward, high continuation, stable visual dynamics, and a sequence of wall panels. Each panel encodes one ASCII byte using eight binary lamps. Decoding those panels yields:

```text
grey{d3LulU_c4N_Som3T1me5_GiV3_A_gooD_s0LUlu}
```
