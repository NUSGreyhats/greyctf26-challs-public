CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    team_id TEXT NOT NULL DEFAULT current_setting('app.team_id'),
    username TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS instance_state (
    team_id TEXT NOT NULL DEFAULT current_setting('app.team_id'),
    singleton_key TEXT NOT NULL,
    instance_seed TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_progress (
    team_id TEXT NOT NULL DEFAULT current_setting('app.team_id'),
    user_id INT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    stage1_cleared BOOLEAN NOT NULL DEFAULT FALSE,
    stage2_cleared BOOLEAN NOT NULL DEFAULT FALSE,
    stage3_cleared BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT current_setting('app.team_id');
ALTER TABLE instance_state
    ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT current_setting('app.team_id');
ALTER TABLE user_progress
    ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT current_setting('app.team_id');

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_username_key;
ALTER TABLE instance_state DROP CONSTRAINT IF EXISTS instance_state_pkey;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'users_team_username_key'
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT users_team_username_key UNIQUE (team_id, username);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'users_team_id_id_key'
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT users_team_id_id_key UNIQUE (team_id, id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'instance_state_pkey'
    ) THEN
        ALTER TABLE instance_state
            ADD CONSTRAINT instance_state_pkey PRIMARY KEY (team_id, singleton_key);
    END IF;
END $$;

UPDATE users
SET team_id = current_setting('app.team_id')
WHERE team_id IS NULL;

UPDATE instance_state
SET team_id = current_setting('app.team_id')
WHERE team_id IS NULL;

UPDATE user_progress
SET team_id = current_setting('app.team_id')
WHERE team_id IS NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'user_progress'
          AND column_name = 'unlocked_stage2_token'
    ) THEN
        UPDATE user_progress
        SET stage1_cleared = TRUE
        WHERE unlocked_stage2_token IS NOT NULL;
        ALTER TABLE user_progress DROP COLUMN unlocked_stage2_token;
    END IF;
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'user_progress'
          AND column_name = 'unlocked_stage3_token'
    ) THEN
        UPDATE user_progress
        SET stage2_cleared = TRUE
        WHERE unlocked_stage3_token IS NOT NULL;
        ALTER TABLE user_progress DROP COLUMN unlocked_stage3_token;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'user_progress_team_user_key'
    ) THEN
        ALTER TABLE user_progress
            ADD CONSTRAINT user_progress_team_user_key UNIQUE (team_id, user_id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'user_progress_team_user_fkey'
    ) THEN
        ALTER TABLE user_progress
            ADD CONSTRAINT user_progress_team_user_fkey
            FOREIGN KEY (team_id, user_id)
            REFERENCES users (team_id, id)
            ON DELETE CASCADE;
    END IF;
END $$;

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS users_team_isolation ON users;
CREATE POLICY users_team_isolation ON users
USING (team_id = current_setting('app.team_id'))
WITH CHECK (team_id = current_setting('app.team_id'));

ALTER TABLE instance_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE instance_state FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS instance_state_team_isolation ON instance_state;
CREATE POLICY instance_state_team_isolation ON instance_state
USING (team_id = current_setting('app.team_id'))
WITH CHECK (team_id = current_setting('app.team_id'));

ALTER TABLE user_progress ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_progress FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS user_progress_team_isolation ON user_progress;
CREATE POLICY user_progress_team_isolation ON user_progress
USING (team_id = current_setting('app.team_id'))
WITH CHECK (team_id = current_setting('app.team_id'));

CREATE TABLE IF NOT EXISTS auth_sessions (
    id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL,
    token_fingerprint TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS auth_sessions_expires_at_idx ON auth_sessions (expires_at);
CREATE INDEX IF NOT EXISTS auth_sessions_team_id_idx ON auth_sessions (team_id);

CREATE OR REPLACE FUNCTION admin_reset_all_mutable_state()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    TRUNCATE pinpoint_guess_log;
    TRUNCATE pinpoint_users;
    TRUNCATE queens_positions;
    TRUNCATE queens_submissions;
    TRUNCATE queens_validation_audit;
    TRUNCATE tango_validation_metrics;
    TRUNCATE tango_region_audit;
    TRUNCATE tango_ledger_entries;
    TRUNCATE tango_attempts;
    TRUNCATE tango_state;
END;
$$;
