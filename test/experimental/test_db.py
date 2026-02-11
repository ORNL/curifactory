import sys

import pytest

from curifactory.experimental import db_tables
from curifactory.experimental.cli import main


def test_db_not_broken_after_failed_pipeline(test_manager, capfd):
    """A failed pipeline shouldn't cripple the database with null IDs etc."""

    sys.argv = ["cf", "run", "test.experimental.pipelines.notindefault.invalid"]
    main()
    out, err = capfd.readouterr()
    print(out)

    sys.argv = ["cf", "run", "test.experimental.pipelines.notindefault.valid"]
    main()
    out, err = capfd.readouterr()
    print(out)

    assert "Execution completed" in out


def test_verify_schemas(clear_filesystem, test_manager):
    """Basic verification should pass."""
    with test_manager.db_connection() as db:
        broken, errors = db_tables.verify_schemas(db)
    assert not broken


def test_verify_schemas_fails_on_wrong_version(base_old_manager):
    """If the database schema isn't the current one, the verify should indicate"""
    with base_old_manager.db_connection() as db:
        broken, errors = db_tables.verify_schemas(db)
    assert broken
    assert len(errors) > 0


def test_migrations_run(base_old_manager):
    """Running database migrations should upgrade the version and db tables should be correct."""
    with base_old_manager.db_connection() as db:
        assert db_tables.get_schema_version(db) == 0
        db_tables.run_migrations(db)
        assert db_tables.get_schema_version(db) == db_tables.SCHEMA_VERSION
        broken, errors = db_tables.verify_schemas(db)
        assert not broken
