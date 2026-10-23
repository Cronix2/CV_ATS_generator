"""Initialize ONLY an explicitly named disposable *_test database, then apply real migrations."""

import argparse
import os
import subprocess
import sys

from psycopg import sql
from sqlalchemy import create_engine, text

parser = argparse.ArgumentParser()
parser.add_argument(
    "--reset",
    action="store_true",
    help="Drop ONLY the disposable *_test public schema before migrating",
)
args = parser.parse_args()
admin = create_engine(os.environ["PF_TEST_ADMIN_URL"], hide_parameters=True)
app = create_engine(os.environ["PF_TEST_APP_URL"], hide_parameters=True)
if (
    not admin.url.database.endswith("_test")
    or app.url.database != admin.url.database
    or app.url.username != "pf_app"
):
    raise SystemExit(
        "Refusing to prepare a non-test database or a privileged application role"
    )
with admin.connect() as conn:
    raw = conn.connection.driver_connection
    if not conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname='pf_app'")).first():
        raw.execute(
            sql.SQL(
                "CREATE ROLE pf_app LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS"
            ).format(sql.Literal(app.url.password))
        )
    conn.commit()
    if args.reset:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()
env = {**os.environ, "V1_MIGRATION_DATABASE_URL": os.environ["PF_TEST_ADMIN_URL"]}
subprocess.run(
    [sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=env
)
