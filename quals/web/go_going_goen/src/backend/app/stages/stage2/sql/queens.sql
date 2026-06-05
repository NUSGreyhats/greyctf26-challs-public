CREATE TABLE IF NOT EXISTS queens_positions (
    id SERIAL PRIMARY KEY,
    team_id TEXT NOT NULL DEFAULT current_setting('app.team_id'),
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    row_idx INT NOT NULL,
    col_idx INT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (user_id, row_idx, col_idx)
);

CREATE TABLE IF NOT EXISTS queens_submissions (
    team_id TEXT NOT NULL DEFAULT current_setting('app.team_id'),
    user_id INT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'idle',
    progress_pct INT NOT NULL DEFAULT 0,
    last_result TEXT,
    last_submitted_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS queens_validation_audit (
    id BIGSERIAL PRIMARY KEY,
    team_id TEXT NOT NULL DEFAULT current_setting('app.team_id'),
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    step_kind TEXT NOT NULL,
    step_index INT NOT NULL,
    observed_count INT NOT NULL,
    checked_prefix_limit INT NOT NULL DEFAULT 0,
    checked_prefix_occupied INT NOT NULL DEFAULT 0,
    board_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

ALTER TABLE queens_positions
    ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT current_setting('app.team_id');
ALTER TABLE queens_submissions
    ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT current_setting('app.team_id');
ALTER TABLE queens_validation_audit
    ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT current_setting('app.team_id');
ALTER TABLE queens_validation_audit
    ADD COLUMN IF NOT EXISTS checked_prefix_limit INT NOT NULL DEFAULT 0;
ALTER TABLE queens_validation_audit
    ADD COLUMN IF NOT EXISTS checked_prefix_occupied INT NOT NULL DEFAULT 0;

DELETE FROM queens_positions a
USING queens_positions b
WHERE a.id > b.id
  AND a.user_id = b.user_id
  AND a.row_idx = b.row_idx
  AND a.col_idx = b.col_idx;

CREATE UNIQUE INDEX IF NOT EXISTS queens_positions_one_per_square
ON queens_positions (user_id, row_idx, col_idx);

UPDATE queens_positions
SET team_id = current_setting('app.team_id')
WHERE team_id IS NULL;

UPDATE queens_submissions
SET team_id = current_setting('app.team_id')
WHERE team_id IS NULL;

UPDATE queens_validation_audit
SET team_id = current_setting('app.team_id')
WHERE team_id IS NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'queens_positions_team_user_fkey'
    ) THEN
        ALTER TABLE queens_positions
            ADD CONSTRAINT queens_positions_team_user_fkey
            FOREIGN KEY (team_id, user_id)
            REFERENCES users (team_id, id)
            ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'queens_submissions_team_user_key'
    ) THEN
        ALTER TABLE queens_submissions
            ADD CONSTRAINT queens_submissions_team_user_key UNIQUE (team_id, user_id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'queens_submissions_team_user_fkey'
    ) THEN
        ALTER TABLE queens_submissions
            ADD CONSTRAINT queens_submissions_team_user_fkey
            FOREIGN KEY (team_id, user_id)
            REFERENCES users (team_id, id)
            ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'queens_validation_audit_team_user_fkey'
    ) THEN
        ALTER TABLE queens_validation_audit
            ADD CONSTRAINT queens_validation_audit_team_user_fkey
            FOREIGN KEY (team_id, user_id)
            REFERENCES users (team_id, id)
            ON DELETE CASCADE;
    END IF;
END $$;

ALTER TABLE queens_positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE queens_positions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS queens_positions_team_isolation ON queens_positions;
CREATE POLICY queens_positions_team_isolation ON queens_positions
USING (team_id = current_setting('app.team_id'))
WITH CHECK (team_id = current_setting('app.team_id'));

ALTER TABLE queens_submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE queens_submissions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS queens_submissions_team_isolation ON queens_submissions;
CREATE POLICY queens_submissions_team_isolation ON queens_submissions
USING (team_id = current_setting('app.team_id'))
WITH CHECK (team_id = current_setting('app.team_id'));

ALTER TABLE queens_validation_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE queens_validation_audit FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS queens_validation_audit_team_isolation ON queens_validation_audit;
CREATE POLICY queens_validation_audit_team_isolation ON queens_validation_audit
USING (team_id = current_setting('app.team_id'))
WITH CHECK (team_id = current_setting('app.team_id'));
