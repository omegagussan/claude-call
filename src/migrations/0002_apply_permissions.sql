-- Migration 0002: Apply table and sequence permissions for application role if configured
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{app_role}') THEN
        EXECUTE 'GRANT USAGE ON SCHEMA {schema} TO {app_role};';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON {schema}.{table} TO {app_role};';
        EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {schema} TO {app_role};';
    END IF;
END
$$;
