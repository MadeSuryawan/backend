from logging.config import fileConfig
from os import environ  # <--- CHANGE 1: Import os

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

# <--- CHANGE 2: Import your SQLModel metadata
# Assuming your models are in a file named 'models.py' or inside 'main.py'
# You must import the Base or SQLModel object so Alembic can "see" your tables.
from main import app  # Or wherever your models are defined

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# ----------------------------------------------------------------------
# CHANGE 3: Overwrite the config with the Environment Variable
# ----------------------------------------------------------------------
# 1. Get the URL from the environment
db_url = environ.get("DATABASE_URL")

if not db_url:
    mssg = "DATABASE_URL environment variable is not set."
    raise ValueError(mssg)

# 2. Fix for Neon/Render:
# SQLAlchemy requires 'postgresql://', but some providers give 'postgres://'
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# 3. Set the SQLAlchemy URL in the config object
config.set_main_option("sqlalchemy.url", db_url)
# ----------------------------------------------------------------------

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = SQLModel.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
