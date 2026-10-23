#!/bin/sh
set -eu
# Only executed on a NEW v1 volume. Never alter an existing deployment's database role.
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set ON_ERROR_STOP=1 <<'SQL'
\getenv app_password V1_APP_DB_PASSWORD
CREATE ROLE pf_app LOGIN PASSWORD :'app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
SQL
