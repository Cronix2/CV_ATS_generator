import os
from contextlib import contextmanager
from functools import lru_cache
from sqlalchemy import create_engine, text
from app.v1.errors import APIError


@lru_cache
def engine():
    url = os.environ['V1_DATABASE_URL']
    if not url.startswith('postgresql+psycopg://'):
        raise RuntimeError('V1_DATABASE_URL requires PostgreSQL with psycopg')
    return create_engine(url, pool_pre_ping=True, pool_size=8, max_overflow=4, hide_parameters=True)


def sql(conn, query, **params):
    return conn.execute(text(query), params)


@contextmanager
def transaction(actor=None):
    with engine().begin() as conn:
        if actor:
            sql(conn, "SELECT set_config('pf.tenant', :tenant, true), set_config('pf.user', :user, true)",
                tenant=actor.tenant, user=actor.user)
        yield conn


def check():
    with transaction() as conn:
        role = sql(conn, 'SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user').one()
        owner = sql(conn, "SELECT pg_has_role(current_user, tableowner, 'USAGE') FROM pg_tables WHERE tablename='pf_records'").scalar()
        if role.rolsuper or role.rolbypassrls or owner is not False:
            raise RuntimeError('v1 requires a migrated database and a non-owner NOBYPASSRLS application role')
        if sql(conn, "SELECT version_num FROM alembic_version").scalar() != '0001_v1':
            raise RuntimeError('Unsupported v1 database schema')
