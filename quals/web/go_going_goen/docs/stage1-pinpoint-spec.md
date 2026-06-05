# Stage 1 Spec - Pinpoint

## Purpose

Stage 1 is the warmup.

It should teach:

- application-level request races are enough
- players do not need deep DB isolation knowledge yet

## Game Rules

- hidden answer
- 5 guess limit
- blind responses only: `correct` or `wrong`
- correct answer unlocks Stage 2 token

## Non-Exploit Solve Pressure

The stage should be practically unsolvable by honest play within 5 attempts.

Requirements:

- answer is chosen from a fixed random subset of 100 words drawn from a larger dictionary
- answer is stable only within a single reset window
- answer is different across teams/instances because the chosen word still depends on instance seed plus user id

Recommended approach:

- derive a deterministic 100-word subset from a fixed organizer seed string
- derive answer index from instance seed plus user id within that subset
- store chosen answer on registration or first stage access
- rotate to a different hidden word from the same subset on reset

## Vulnerability

The race is:

1. read `guesses_used`
2. check `< 5`
3. compare guess to answer
4. increment `guesses_used`
5. if correct, mark solved

Because multiple requests can observe the same pre-increment count, more than 5 attempts can be accepted.

## Tables

```sql
CREATE TABLE pinpoint_users (
    user_id INT PRIMARY KEY REFERENCES users(id),
    guesses_used INT NOT NULL DEFAULT 0,
    solved BOOLEAN NOT NULL DEFAULT FALSE,
    puzzle_answer TEXT NOT NULL,
    last_result TEXT
);

CREATE TABLE pinpoint_guess_log (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id),
    guess TEXT NOT NULL,
    accepted BOOLEAN NOT NULL,
    was_correct BOOLEAN NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);
```

`pinpoint_guess_log` is optional but useful for organizer debugging and post-solve source review.

## Routes

### `GET /api/v1/pinpoint/status`

Returns:

```json
{
  "guesses_used": 3,
  "remaining_guesses": 2,
  "solved": false,
  "last_result": "wrong"
}
```

### `POST /api/v1/pinpoint/guess`

Request:

```json
{
  "guess": "crane"
}
```

Success response:

```json
{
  "result": "wrong",
  "guesses_used": 4,
  "remaining_guesses": 1
}
```

On solve:

```json
{
  "result": "correct"
}
```

Failure on limit reached:

```json
{
  "error": "limit_reached",
  "message": "Guess limit reached."
}
```

### `POST /api/v1/pinpoint/reset`

Resets:

- `guesses_used = 0`
- `solved = false`
- `last_result = null`
- `puzzle_answer = new hidden word`

Does not reset:

- progression unlock

## Vulnerable Handler Shape

Pseudo-code:

```python
row = db.fetch_one(
    "SELECT guesses_used, solved, puzzle_answer FROM pinpoint_users WHERE user_id = %s",
    [user_id],
)

if row["guesses_used"] >= 5:
    return limit_reached()

is_correct = normalize(guess) == row["puzzle_answer"]

db.execute(
    """
    UPDATE pinpoint_users
    SET guesses_used = guesses_used + 1,
        solved = solved OR %s,
        last_result = %s
    WHERE user_id = %s
    """,
    [is_correct, "correct" if is_correct else "wrong", user_id],
)

if is_correct:
    unlock_stage2(user_id)
    return {"result": "correct"}

return {"result": "wrong"}
```

Do not:

- use `SELECT ... FOR UPDATE`
- use a compare-and-swap `UPDATE ... WHERE guesses_used < 5`
- wrap this in a serializing lock

## Reset and Retry Expectations

Players should be able to:

- guess
- overshoot the cap
- reset
- immediately try again with a new hidden word

## Difficulty Target

Expected solve method:

- write a small concurrent request script
- spray the instance's small hidden candidate set faster than the limit can advance

Expected difficulty:

- easy warmup
- almost no timing tuning required

## Ownership Boundary

Stage 1 owner must deliver:

- DB schema for Stage 1
- Stage 1 routes
- answer-seeding logic integrated with shared auth/bootstrap
- clear hook into `user_progress`
