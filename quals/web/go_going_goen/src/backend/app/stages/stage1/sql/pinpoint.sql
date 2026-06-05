CREATE TABLE IF NOT EXISTS pinpoint_users (
    team_id TEXT NOT NULL DEFAULT current_setting('app.team_id'),
    user_id INT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    guesses_used INT NOT NULL DEFAULT 0,
    solved BOOLEAN NOT NULL DEFAULT FALSE,
    puzzle_answer TEXT NOT NULL,
    last_result TEXT
);

CREATE TABLE IF NOT EXISTS pinpoint_guess_log (
    id SERIAL PRIMARY KEY,
    team_id TEXT NOT NULL DEFAULT current_setting('app.team_id'),
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    guess TEXT NOT NULL,
    accepted BOOLEAN NOT NULL,
    was_correct BOOLEAN NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

ALTER TABLE pinpoint_users
    ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT current_setting('app.team_id');
ALTER TABLE pinpoint_guess_log
    ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT current_setting('app.team_id');

UPDATE pinpoint_users
SET team_id = current_setting('app.team_id')
WHERE team_id IS NULL;

UPDATE pinpoint_guess_log
SET team_id = current_setting('app.team_id')
WHERE team_id IS NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'pinpoint_users_team_user_key'
    ) THEN
        ALTER TABLE pinpoint_users
            ADD CONSTRAINT pinpoint_users_team_user_key UNIQUE (team_id, user_id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'pinpoint_users_team_user_fkey'
    ) THEN
        ALTER TABLE pinpoint_users
            ADD CONSTRAINT pinpoint_users_team_user_fkey
            FOREIGN KEY (team_id, user_id)
            REFERENCES users (team_id, id)
            ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'pinpoint_guess_log_team_user_fkey'
    ) THEN
        ALTER TABLE pinpoint_guess_log
            ADD CONSTRAINT pinpoint_guess_log_team_user_fkey
            FOREIGN KEY (team_id, user_id)
            REFERENCES users (team_id, id)
            ON DELETE CASCADE;
    END IF;
END $$;

ALTER TABLE pinpoint_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE pinpoint_users FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS pinpoint_users_team_isolation ON pinpoint_users;
CREATE POLICY pinpoint_users_team_isolation ON pinpoint_users
USING (team_id = current_setting('app.team_id'))
WITH CHECK (team_id = current_setting('app.team_id'));

ALTER TABLE pinpoint_guess_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE pinpoint_guess_log FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS pinpoint_guess_log_team_isolation ON pinpoint_guess_log;
CREATE POLICY pinpoint_guess_log_team_isolation ON pinpoint_guess_log
USING (team_id = current_setting('app.team_id'))
WITH CHECK (team_id = current_setting('app.team_id'));
