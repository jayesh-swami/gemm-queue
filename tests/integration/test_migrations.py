from alembic import command
from conftest import alembic_config


def test_migrations_match_the_models():
    """The test DB was built by `alembic upgrade head`; autogenerate must find nothing to add."""
    command.check(alembic_config())
