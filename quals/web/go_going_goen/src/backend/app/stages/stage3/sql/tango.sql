CREATE TABLE IF NOT EXISTS tango_state (
    team_id TEXT NOT NULL DEFAULT current_setting('app.team_id'),
    user_id INT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    puzzle_id TEXT NOT NULL DEFAULT 'default',
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tango_attempts (
    attempt_id UUID PRIMARY KEY,
    team_id TEXT NOT NULL DEFAULT current_setting('app.team_id'),
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    grid_payload JSONB NOT NULL,
    lock_order JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tango_ledger_entries (
    entry_id UUID PRIMARY KEY,
    team_id TEXT NOT NULL DEFAULT current_setting('app.team_id'),
    attempt_id UUID NOT NULL REFERENCES tango_attempts(attempt_id) ON DELETE CASCADE,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    amount INT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tango_validation_locks (
    team_id TEXT NOT NULL DEFAULT current_setting('app.team_id'),
    lock_key TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tango_region_audit (
    id SERIAL PRIMARY KEY,
    team_id TEXT NOT NULL DEFAULT current_setting('app.team_id'),
    attempt_id UUID NOT NULL REFERENCES tango_attempts(attempt_id) ON DELETE CASCADE,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lock_key TEXT NOT NULL,
    region_payload JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tango_validation_metrics (
    attempt_id UUID PRIMARY KEY REFERENCES tango_attempts(attempt_id) ON DELETE CASCADE,
    team_id TEXT NOT NULL DEFAULT current_setting('app.team_id'),
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    validated_regions INT NOT NULL DEFAULT 0,
    latest_lock_key TEXT NOT NULL,
    latest_imbalance INT NOT NULL DEFAULT 0,
    audit_row_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

ALTER TABLE tango_state
    ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT current_setting('app.team_id');
ALTER TABLE tango_attempts
    ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT current_setting('app.team_id');
ALTER TABLE tango_ledger_entries
    ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT current_setting('app.team_id');
ALTER TABLE tango_validation_locks
    ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT current_setting('app.team_id');
ALTER TABLE tango_region_audit
    ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT current_setting('app.team_id');
ALTER TABLE tango_validation_metrics
    ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT current_setting('app.team_id');

INSERT INTO tango_validation_locks (lock_key)
VALUES
    ('row_balance:1'),
    ('row_balance:2'),
    ('row_balance:3'),
    ('row_balance:4'),
    ('row_balance:5'),
    ('row_balance:6')
ON CONFLICT DO NOTHING;

UPDATE tango_state
SET team_id = current_setting('app.team_id')
WHERE team_id IS NULL;

UPDATE tango_attempts
SET team_id = current_setting('app.team_id')
WHERE team_id IS NULL;

UPDATE tango_ledger_entries
SET team_id = current_setting('app.team_id')
WHERE team_id IS NULL;

UPDATE tango_validation_locks
SET team_id = current_setting('app.team_id')
WHERE team_id IS NULL;

UPDATE tango_region_audit
SET team_id = current_setting('app.team_id')
WHERE team_id IS NULL;

UPDATE tango_validation_metrics
SET team_id = current_setting('app.team_id')
WHERE team_id IS NULL;

ALTER TABLE tango_validation_locks DROP CONSTRAINT IF EXISTS tango_validation_locks_pkey;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'tango_state_team_user_key'
    ) THEN
        ALTER TABLE tango_state
            ADD CONSTRAINT tango_state_team_user_key UNIQUE (team_id, user_id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'tango_state_team_user_fkey'
    ) THEN
        ALTER TABLE tango_state
            ADD CONSTRAINT tango_state_team_user_fkey
            FOREIGN KEY (team_id, user_id)
            REFERENCES users (team_id, id)
            ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'tango_attempts_team_user_fkey'
    ) THEN
        ALTER TABLE tango_attempts
            ADD CONSTRAINT tango_attempts_team_user_fkey
            FOREIGN KEY (team_id, user_id)
            REFERENCES users (team_id, id)
            ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'tango_ledger_entries_team_user_fkey'
    ) THEN
        ALTER TABLE tango_ledger_entries
            ADD CONSTRAINT tango_ledger_entries_team_user_fkey
            FOREIGN KEY (team_id, user_id)
            REFERENCES users (team_id, id)
            ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'tango_validation_locks_pkey'
    ) THEN
        ALTER TABLE tango_validation_locks
            ADD CONSTRAINT tango_validation_locks_pkey PRIMARY KEY (team_id, lock_key);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'tango_region_audit_team_user_fkey'
    ) THEN
        ALTER TABLE tango_region_audit
            ADD CONSTRAINT tango_region_audit_team_user_fkey
            FOREIGN KEY (team_id, user_id)
            REFERENCES users (team_id, id)
            ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'tango_validation_metrics_team_user_fkey'
    ) THEN
        ALTER TABLE tango_validation_metrics
            ADD CONSTRAINT tango_validation_metrics_team_user_fkey
            FOREIGN KEY (team_id, user_id)
            REFERENCES users (team_id, id)
            ON DELETE CASCADE;
    END IF;
END $$;

ALTER TABLE tango_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE tango_state FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tango_state_team_isolation ON tango_state;
CREATE POLICY tango_state_team_isolation ON tango_state
USING (team_id = current_setting('app.team_id'))
WITH CHECK (team_id = current_setting('app.team_id'));

ALTER TABLE tango_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE tango_attempts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tango_attempts_team_isolation ON tango_attempts;
CREATE POLICY tango_attempts_team_isolation ON tango_attempts
USING (team_id = current_setting('app.team_id'))
WITH CHECK (team_id = current_setting('app.team_id'));

ALTER TABLE tango_ledger_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE tango_ledger_entries FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tango_ledger_entries_team_isolation ON tango_ledger_entries;
CREATE POLICY tango_ledger_entries_team_isolation ON tango_ledger_entries
USING (team_id = current_setting('app.team_id'))
WITH CHECK (team_id = current_setting('app.team_id'));

ALTER TABLE tango_validation_locks ENABLE ROW LEVEL SECURITY;
ALTER TABLE tango_validation_locks FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tango_validation_locks_team_isolation ON tango_validation_locks;
CREATE POLICY tango_validation_locks_team_isolation ON tango_validation_locks
USING (team_id = current_setting('app.team_id'))
WITH CHECK (team_id = current_setting('app.team_id'));

ALTER TABLE tango_region_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE tango_region_audit FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tango_region_audit_team_isolation ON tango_region_audit;
CREATE POLICY tango_region_audit_team_isolation ON tango_region_audit
USING (team_id = current_setting('app.team_id'))
WITH CHECK (team_id = current_setting('app.team_id'));

ALTER TABLE tango_validation_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE tango_validation_metrics FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tango_validation_metrics_team_isolation ON tango_validation_metrics;
CREATE POLICY tango_validation_metrics_team_isolation ON tango_validation_metrics
USING (team_id = current_setting('app.team_id'))
WITH CHECK (team_id = current_setting('app.team_id'));
