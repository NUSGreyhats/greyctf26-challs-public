# Notes for the challenge author

Solved end-to-end and pulled the flag `grey{placeholderA}` — the wiring is
solid and the three vulns chain nicely. Below are the spots where the
challenge over-shares, under-shares, or has friction that would be worth
tightening for the public release.

## Cross-cutting

- **Source naming inconsistency.** `/api/progress` reports `stage1_source`,
  `stage2_source`, `stage3_source` keys in the `downloads` map, but
  `getDownloadUrl(L)` in the bundle is called with the bare stage id
  (`stage1`, `stage2`, `stage3`) and `/api/downloads/stage1_source` returns
  `{"error":"download_not_found"}`. Pick one naming and use it everywhere —
  solvers shouldn't have to grep the bundle to learn that the path differs
  from the JSON key.
- **HTTP 405 on HEAD with `allow: GET`** for every endpoint is a strong tell
  that the route exists. Not a real leak, but worth knowing.
- **Singleton user via `singleton_username = "team"`.** Fine for the
  challenge, but the `team_id` salt and `final_flag` derivation are not used
  anywhere I touched. If they're load-bearing for a multi-tenant variant,
  that needs to be visible from the source; if not, they're dead weight that
  invites red herrings.
- **`InMemory*Repository` classes are shipped in every stage tarball.** They
  reveal exactly which paths run in production vs. tests, which lowers the
  "have I covered every code path?" bar significantly. Strip these from the
  player-facing tarballs and keep them only in the test tree.

## Stage 1 — Pinpoint

What works well:
- The deterministic 100-word subset (`SUBSET_SEED`) is a clean way to
  bound the candidate set without leaking the answer.
- `WordBank.contains` deliberately loops every word in constant-ish work to
  avoid timing attacks — nice touch.

What over-shares / under-shares / could be tightened:
- **The bug is louder than it needs to be.** Two adjacent
  hints — `# guess cap is enforced from the latest persisted counter before
  scoring` and a per-user `Stage1GuessGate(capacity=30)` defined right next
  to a `GUESS_LIMIT = 5` — basically point at the TOCTOU. Capacity 30 isn't
  a number you pick by accident; lowering it to 6–10 still leaves the bug
  exploitable but forces the player to actually realize what's wrong.
- **`subset_size=100` with 30 concurrent guesses ≈ 30% per round and reset
  is unmetered.** Players who fail by chance just `/reset` and try again
  with the same wordbank; the puzzle becomes "did your race land cleanly,"
  not "did you understand the bug." Consider rate-limiting `/reset` or
  shrinking the subset so each burst either solves it or commits to a
  visible cost.
- **`_placeholder_wordbank` lists `"crane"` and friends.** That's the same
  word the localStorage default uses, which makes it look (incorrectly)
  like the answer might be `crane`. Drop the placeholder or rename it so it
  doesn't read as a hint.
- **`WORD_PATTERN = r"^[a-z]{5}[a-z]*$"`** matches 5-or-more letters; the
  player-visible message says "Guesses must be at least 5 letters" but the
  modal copy is "Guess the hidden word / You have 5 guesses." If you intend
  to support 6+ letter answers, say so. If not, anchor the pattern to
  exactly five letters and update the comment.
- **`recent_guesses` field is informational only,** which is good. Just make
  sure the front-end never renders the *answer* there even when `solved=true`.

## Stage 2 — Queens

What works well:
- `record_validation_step` writing the per-step audit with a fresh
  `jsonb_agg` snapshot is a nice red herring — it looks load-bearing but
  doesn't actually affect win conditions, which mirrors how real auditing
  layers waste attacker attention.
- The fact that the `/add-batch` route is undocumented in the JS bundle is
  a perfectly fair "read the source" moment.

What over-shares / under-shares / could be tightened:
- **`Stage2SubmissionGate(capacity=30)` in `dependencies.py` is unused** for
  the actual exploit. The race is on `add-batch` vs. `submit`, not on
  concurrent submits. The capacity-30 number is suggestive of stage 1's
  bug; if it's not pivotal here, set it to 1 or 2 to stop misdirecting.
- **`Stage2SubmissionGate` default `capacity=4`** in `service.py` vs. the
  `capacity=30` override in `dependencies.py` is a smell. Pick one source
  of truth.
- **`validation_db_factory: Callable[[], Database] = Database` is a flag in
  bright red marker.** It's the only ergonomic reason the bug exists (the
  scan runs in a *separate* connection). For a harder version: make the
  factory private, or wire `submit` to reuse `self._db` and instead introduce
  the race elsewhere (e.g., a deliberately misordered `LOCK TABLE` /
  `SET TRANSACTION ISOLATION LEVEL READ COMMITTED`).
- **Timing window is tiny (~5 ms).** It works because the validation loop
  runs ~50 iterations × ~8 ms each, but submits over Cloudflare jitter by
  20–80 ms. A successful run takes a 60-shot sweep. Players on bad
  network conditions may need much longer. Worth verifying the exploit
  still lands at, say, p95 RTT.
- **No record of *which* `add-batch` was the one that won the race.** All
  the failed attempts also persist their queens until the next reset, so
  the audit log fills with garbage and `total_queens` ends at 1387 (1337
  win threshold + 50 diagonal seed) rather than a clean 1337. Cosmetic but
  noticeable.
- **`/api/v2/queens/add-batch` is missing from the frontend bundle's
  exposed API surface.** That's clearly intentional ("you had to read the
  router"), but consider documenting why the players were given the *whole*
  router and not just the parts they should reason about. Otherwise it
  reads like an oversight.

## Stage 3 — Tango

What works well:
- The interplay between `_ledger_status_for_attempt_status("error")` ↦
  `"PENDING"` and `spendable_dollars = committed + pending + fees` is
  genuinely elegant. The deadlock-vector through `derive_lock_order` ties
  the puzzle mechanics back to the bug, which is satisfying.
- Pre-seeded `tango_validation_locks` rows are exactly the right level of
  scaffolding — clearly the intended pivot.

What over-shares / under-shares / could be tightened:
- **`# validation worker failed; attempt is marked error without awarding
  play credit` is a hint, not a comment.** It tells the player exactly
  which path skips the fee — i.e. the path they want. Drop or invert the
  framing (e.g. "rollback any provisional credit") to keep the bug
  discoverable but not signposted.
- **`derive_lock_order` only ranks rows 1 and 2.** Why those? Why not all
  six? That asymmetry screams "look here." A subtler version sorts a
  larger set (all rows, or rows + columns) and the player has to engineer
  a deadlock through specific imbalances. With only two locks the
  symmetric grids essentially write themselves.
- **`spendable_dollars` semantics are inconsistent with the UI copy.** The
  modal says "Each accepted play costs $100 and awards $100," which a
  player reads as "net zero per attempt." The spendable formula then
  rewards the player for attempts that *don't* accept and *don't* roll back.
  Either rename the field (`unsettled_dollars`?) or tighten the formula to
  only include settled balances. Right now the formula is the bug and the
  bug is the formula, which makes the puzzle "spot the line of arithmetic"
  rather than "exploit a behavior."
- **`ledger/refresh` endpoint is fragile.** A player who calls it for the
  obvious "let's see the latest state" reason will nuke their balance and
  have to redo everything. Either make it idempotent for the player's
  benefit, rename it to something more dangerous-sounding, or omit it.
- **PostgreSQL `deadlock_timeout = 1s` default** makes each pair slow.
  Lowering it (or documenting it in the README so players can simulate
  locally) would smooth the experience.
- **`Stage3SubmissionGate(capacity=2)`** is exactly the number you need to
  trigger the deadlock — neither too small (locks the player out of the
  bug) nor too large (lets them flood it). That's good. But the inline
  comment `# caps in-flight validation sagas so paired submits can be
  compared side by side` is *another* hint that screams "you need paired
  submits." Removing it adds difficulty for free.
- **`SqlTangoRepository.validate_attempt` opens its own connection inside
  the request handler**, which is the canonical "two-transaction" smell.
  Combined with the explicit `connection.commit()` inside
  `create_attempt_with_pending_entry`, the architecture telegraphs the
  attack. A harder version threads `db` through validate_attempt so the
  ledger and validation share a transaction — then the bug needs a
  different lever.

## Local-test friction

- **Source tarballs are stage-scoped** — `stage1.bin` only contains stage 1.
  That's intentional, but it means players can't run the server locally to
  verify exploits before going live. A scaffolded `docker compose up` for
  each stage would make local-first development tenable. I worked the
  exploits straight against the live server, which is fine for me but is a
  rough experience for newer players.
- **No SQL DDL is in the tarball.** Tables `pinpoint_users`,
  `pinpoint_guess_log`, `queens_positions`, `queens_validation_audit`,
  `queens_submissions`, `tango_attempts`, `tango_ledger_entries`,
  `tango_region_audit`, `tango_validation_metrics`, `tango_state`,
  `tango_validation_locks` are all referenced but never defined. If you
  want players to run things locally, ship the DDL.
- **Singleton session implies `team_id_salt`/`SESSION_SECRET` matter
  somewhere I never touched.** If they don't, drop them; if they do, the
  endpoints I exercised would have shown me.

## Net assessment

The three-stage progression (TOCTOU → READ COMMITTED race window → SQL
deadlock + accounting bug) escalates nicely in conceptual difficulty.
Concrete suggestions ordered by impact:

1. **Stop telegraphing via capacity numbers.** Stage 1's 30 and stage 2's
   30 both read as "do a race." Drop them low or remove the gate entirely.
2. **Remove the `# validation worker failed; attempt is marked error
   without awarding play credit` comment.** That single line halves stage
   3's puzzle.
3. **Provide a `docker-compose.yml` (or just the SQL DDL).** Closes the
   "can't test locally" gap that this prompt called out explicitly.
4. **Reconcile naming.** `stage1` vs. `stage1_source`, `capacity=4` vs.
   `capacity=30`, "guess at least 5 letters" vs. "guess the hidden word."
5. **Reconsider the ledger formula.** Including `pending` in `spendable` is
   doing all of stage 3's work; one rename or one extra status would make
   the bug feel earned.
