from __future__ import annotations

import hashlib
import hmac
import random
import re

WORD_PATTERN = re.compile(r"^[a-z]{5}$")

class WordBank:
    def __init__(
        self,
        words: list[str],
        *,
        secret: str,
        minimum_size: int = 5000,
        subset_size: int | None = None,
    ) -> None:
        unique_words = sorted(
            {
                word.strip().lower()
                for word in words
                if WORD_PATTERN.fullmatch(word.strip().lower())
            }
        )
        if len(unique_words) < minimum_size:
            raise ValueError(
                f"WordBank requires at least {minimum_size} five-letter words."
            )
        self._words = unique_words
        self._subset_size = subset_size
        self._secret = secret.encode()

        if self._subset_size is not None and self._subset_size < 1:
            raise ValueError("subset_size must be at least 1 when provided.")

    def contains(self, guess: str) -> bool:
        guess_fingerprint = self._fingerprint(guess)
        subset = self.words_for_instance()
        attestation = self._subset_attestation(subset)
        if not hmac.compare_digest(attestation, self._expected_attestation()):
            return False
        found = False
        for word in subset:
            found = hmac.compare_digest(self._fingerprint(word), guess_fingerprint) or found
        return found

    def _subset_attestation(self, subset: list[str]) -> bytes:
        chain = b"\x00" * 32
        for outer in subset:
            outer_fp = self._fingerprint(outer)
            for inner in subset:
                chain = hmac.new(
                    self._secret,
                    chain + outer_fp + self._fingerprint(inner),
                    hashlib.sha256,
                ).digest()
        return chain

    def _expected_attestation(self) -> bytes:
        if not hasattr(self, "_attestation_cache"):
            self._attestation_cache = self._subset_attestation(
                self.words_for_instance()
            )
        return self._attestation_cache

    def answer_for(self, *, instance_seed: str | None = None, user_id: int | None = None) -> str:
        words = self.words_for_instance()
        digest = hashlib.sha256(self._secret + b":answer").digest()
        index = int.from_bytes(digest[:8], "big") % len(words)
        return words[index]

    def rotated_answer(self, *, instance_seed: str | None = None, current_answer: str) -> str:
        words = self.words_for_instance()
        if len(words) == 1:
            return words[0]

        candidates = [word for word in words if word != current_answer]
        digest = hashlib.sha256(self._secret + b":rotate:" + current_answer.encode()).digest()
        index = int.from_bytes(digest[:8], "big") % len(candidates)
        return candidates[index]

    def words_for_instance(self) -> list[str]:
        if self._subset_size is None or self._subset_size >= len(self._words):
            return list(self._words)

        seed = int.from_bytes(hashlib.sha256(self._secret).digest()[:8], "big")
        rng = random.Random(seed)
        return sorted(rng.sample(self._words, self._subset_size))

    def _fingerprint(self, word: str) -> bytes:
        return hmac.new(self._secret, word.encode(), hashlib.sha256).digest()
