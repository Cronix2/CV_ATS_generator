import os

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

engine = create_engine(
    os.environ["V1_MIGRATION_DATABASE_URL"], poolclass=NullPool, hide_parameters=True
)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()
