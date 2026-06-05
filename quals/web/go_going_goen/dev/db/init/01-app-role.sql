DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'gogoinggoen_app') THEN
        CREATE ROLE gogoinggoen_app
            LOGIN
            PASSWORD 'gogoinggoen_app_password'
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOBYPASSRLS;
    END IF;
END
$$;

GRANT CONNECT ON DATABASE go_going_goen TO gogoinggoen_app;
GRANT USAGE ON SCHEMA public TO gogoinggoen_app;
