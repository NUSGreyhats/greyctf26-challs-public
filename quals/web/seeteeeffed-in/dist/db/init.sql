CREATE EXTENSION IF NOT EXISTS refint;
DROP FUNCTION IF EXISTS register_player(TEXT, TEXT, TEXT, TEXT, TEXT);
DROP FUNCTION IF EXISTS register_player(TEXT, TEXT, TEXT, TEXT, TEXT, TEXT);
DROP FUNCTION IF EXISTS login_player(TEXT, TEXT);
DROP FUNCTION IF EXISTS login_player(TEXT, TEXT, TEXT);
DROP FUNCTION IF EXISTS session_player_id(TEXT);
DROP FUNCTION IF EXISTS create_session_for_player(INTEGER);
DROP FUNCTION IF EXISTS public_feed_posts();
DROP TABLE IF EXISTS posts CASCADE;
DROP TABLE IF EXISTS user_sessions CASCADE;
DROP TABLE IF EXISTS secrets CASCADE;
DROP TABLE IF EXISTS player_usernames CASCADE;
DROP TABLE IF EXISTS players CASCADE;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'flag_owner') THEN
        CREATE ROLE flag_owner NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
        CREATE ROLE app_user LOGIN PASSWORD '<REDACT>';
    ELSE
        ALTER ROLE app_user WITH LOGIN PASSWORD '<REDACT>';
    END IF;
END
$$;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON DATABASE ctf FROM PUBLIC;
GRANT CONNECT ON DATABASE ctf TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;
CREATE TABLE players (
    player_id SERIAL PRIMARY KEY,
    password TEXT NOT NULL,
    display_name TEXT NOT NULL,
    bio TEXT NOT NULL DEFAULT ''
);
CREATE TABLE player_usernames (
    username TEXT PRIMARY KEY,
    player_id INTEGER NOT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    is_private BOOLEAN NOT NULL DEFAULT FALSE,
    CHECK ((is_primary AND NOT is_private) OR (is_private AND NOT is_primary))
);
CREATE UNIQUE INDEX player_usernames_primary_idx
ON player_usernames (player_id)
WHERE is_primary;
CREATE UNIQUE INDEX player_usernames_anchor_idx
ON player_usernames (player_id)
WHERE is_private;
CREATE TABLE user_sessions (
    session_token TEXT PRIMARY KEY,
    player_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    session_note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX user_sessions_player_id_idx ON user_sessions (player_id);
CREATE INDEX user_sessions_username_idx ON user_sessions (username);
CREATE TABLE posts (
    post_id SERIAL PRIMARY KEY,
    player_id INTEGER NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX posts_created_at_idx ON posts (created_at DESC);
CREATE INDEX posts_player_id_idx ON posts (player_id);
CREATE TRIGGER player_usernames_refint_cascade
AFTER UPDATE OR DELETE ON player_usernames
FOR EACH ROW
EXECUTE FUNCTION check_foreign_key(1, 'cascade', 'username', 'user_sessions', 'username');
CREATE TRIGGER user_sessions_refint_validate
AFTER INSERT OR UPDATE ON user_sessions
FOR EACH ROW
EXECUTE FUNCTION check_primary_key('username', 'player_usernames', 'username');
CREATE TABLE secrets (
    owner_player_id INTEGER PRIMARY KEY,
    flag TEXT NOT NULL
);
ALTER TABLE secrets OWNER TO flag_owner;
REVOKE ALL ON players, player_usernames, user_sessions, posts, secrets FROM PUBLIC;
REVOKE ALL ON players, player_usernames, user_sessions, posts, secrets FROM app_user;
GRANT SELECT (player_id, display_name, bio) ON players TO app_user;
GRANT SELECT (username, player_id, is_primary, is_private) ON player_usernames TO app_user;
GRANT UPDATE (username) ON player_usernames TO app_user;
GRANT SELECT (session_token, player_id, username, session_note) ON user_sessions TO app_user;
GRANT UPDATE (username, session_note) ON user_sessions TO app_user;
GRANT SELECT (post_id, player_id, body, created_at) ON posts TO app_user;
GRANT INSERT (player_id, body) ON posts TO app_user;
GRANT USAGE, SELECT ON SEQUENCE posts_post_id_seq TO app_user;
GRANT SELECT (owner_player_id, flag) ON secrets TO app_user;
ALTER TABLE players ENABLE ROW LEVEL SECURITY;
ALTER TABLE players FORCE ROW LEVEL SECURITY;
ALTER TABLE player_usernames ENABLE ROW LEVEL SECURITY;
ALTER TABLE player_usernames FORCE ROW LEVEL SECURITY;
ALTER TABLE user_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_sessions FORCE ROW LEVEL SECURITY;
ALTER TABLE posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE posts FORCE ROW LEVEL SECURITY;
ALTER TABLE secrets ENABLE ROW LEVEL SECURITY;
ALTER TABLE secrets FORCE ROW LEVEL SECURITY;
CREATE POLICY players_select_policy
ON players
FOR SELECT
TO app_user
USING (player_id = current_setting('app.player_id', true)::integer);
CREATE POLICY player_usernames_select_policy
ON player_usernames
FOR SELECT
TO app_user
USING (player_id = current_setting('app.player_id', true)::integer);
CREATE POLICY player_usernames_update_policy
ON player_usernames
FOR UPDATE
TO app_user
USING (
    player_id = current_setting('app.player_id', true)::integer
    AND (is_primary OR is_private)
)
WITH CHECK (player_id = current_setting('app.player_id', true)::integer);
CREATE POLICY user_sessions_select_policy
ON user_sessions
FOR SELECT
TO app_user
USING (player_id = current_setting('app.player_id', true)::integer);
CREATE POLICY user_sessions_update_policy
ON user_sessions
FOR UPDATE
TO app_user
USING (player_id = current_setting('app.player_id', true)::integer)
WITH CHECK (player_id = current_setting('app.player_id', true)::integer);
CREATE POLICY posts_select_policy
ON posts
FOR SELECT
TO app_user
USING (TRUE);
CREATE POLICY posts_insert_policy
ON posts
FOR INSERT
TO app_user
WITH CHECK (player_id = current_setting('app.player_id', true)::integer);
CREATE POLICY secrets_select_policy
ON secrets
FOR SELECT
TO app_user
USING (owner_player_id = current_setting('app.player_id', true)::integer);
CREATE OR REPLACE FUNCTION create_session_for_player(p_player_id INTEGER)
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    new_token TEXT;
    private_username TEXT;
BEGIN
    SELECT username
    INTO private_username
    FROM public.player_usernames
    WHERE player_id = p_player_id AND is_private;
    new_token := md5(random()::text || clock_timestamp()::text || p_player_id::text);
    INSERT INTO public.user_sessions (session_token, player_id, username, session_note)
    VALUES (
        new_token,
        p_player_id,
        private_username,
        'Your profile preview is ready.'
    );
    RETURN new_token;
END;
$$;
CREATE OR REPLACE FUNCTION register_player(
    p_public_username TEXT,
    p_private_username TEXT,
    p_password TEXT,
    p_display_name TEXT,
    p_bio TEXT,
    p_flag TEXT
)
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    new_player_id INTEGER;
BEGIN
    INSERT INTO public.players (password, display_name, bio)
    VALUES (p_password, p_display_name, p_bio)
    RETURNING player_id INTO new_player_id;
    INSERT INTO public.player_usernames (username, player_id, is_primary, is_private)
    VALUES
        (p_public_username, new_player_id, TRUE, FALSE),
        (p_private_username, new_player_id, FALSE, TRUE);
    INSERT INTO public.secrets (owner_player_id, flag)
    VALUES (new_player_id, p_flag);
    RETURN public.create_session_for_player(new_player_id);
END;
$$;
CREATE OR REPLACE FUNCTION login_player(
    p_public_username TEXT,
    p_private_username TEXT,
    p_password TEXT
)
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    found_player_id INTEGER;
BEGIN
    SELECT p.player_id
    INTO found_player_id
    FROM public.players AS p
    JOIN public.player_usernames AS public_name
        ON public_name.player_id = p.player_id AND public_name.is_primary
    JOIN public.player_usernames AS private_name
        ON private_name.player_id = p.player_id AND private_name.is_private
    WHERE public_name.username = p_public_username
        AND private_name.username = p_private_username
        AND p.password = p_password;
    IF found_player_id IS NULL THEN
        RAISE EXCEPTION 'invalid credentials';
    END IF;
    RETURN public.create_session_for_player(found_player_id);
END;
$$;
CREATE OR REPLACE FUNCTION session_player_id(
    p_session_token TEXT
)
RETURNS INTEGER
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = pg_catalog, public
AS $$
    SELECT player_id
    FROM public.user_sessions
    WHERE session_token = p_session_token
$$;
CREATE OR REPLACE FUNCTION public_feed_posts()
RETURNS TABLE (
    post_id INTEGER,
    body TEXT,
    created_at TIMESTAMPTZ,
    player_id INTEGER,
    display_name TEXT,
    username TEXT
)
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = pg_catalog, public
AS $$
    SELECT
        p.post_id,
        p.body,
        p.created_at,
        p.player_id,
        pl.display_name,
        pu.username
    FROM public.posts AS p
    JOIN public.players AS pl ON pl.player_id = p.player_id
    JOIN public.player_usernames AS pu
        ON pu.player_id = p.player_id AND pu.is_primary
    ORDER BY p.created_at DESC, p.post_id DESC
    LIMIT 50
$$;
REVOKE ALL ON FUNCTION create_session_for_player(INTEGER) FROM PUBLIC;
REVOKE ALL ON FUNCTION register_player(TEXT, TEXT, TEXT, TEXT, TEXT, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION login_player(TEXT, TEXT, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION session_player_id(TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public_feed_posts() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION register_player(TEXT, TEXT, TEXT, TEXT, TEXT, TEXT) TO app_user;
GRANT EXECUTE ON FUNCTION login_player(TEXT, TEXT, TEXT) TO app_user;
GRANT EXECUTE ON FUNCTION session_player_id(TEXT) TO app_user;
GRANT EXECUTE ON FUNCTION public_feed_posts() TO app_user;
