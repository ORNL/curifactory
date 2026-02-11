import shutil

import pytest

from curifactory.experimental import db_tables
from curifactory.experimental.manager import Manager


@pytest.fixture()
def test_manager():
    # with Manager.from_config({"default_pipeline_modules": ["pipelines.example"]}) as manager:
    #     yield manager
    manager = Manager.from_config(
        {"default_pipeline_modules": ["test.experimental.pipelines.example"]}
    )
    return manager


@pytest.fixture()
def base_old_manager(clear_filesystem):
    revert_version = db_tables.SCHEMA_VERSION
    revert_schemas = db_tables.SCHEMAS
    db_tables.SCHEMA_VERSION = 0
    db_tables.SCHEMAS = db_tables._original_schemas
    manager = Manager.from_config(
        {
            "default_pipeline_modules": ["test.experimental.pipelines.example"],
            "database_path": "data/store_old.db",
        }
    )
    db_tables.SCHEMA_VERSION = revert_version
    db_tables.SCHEMAS = revert_schemas
    return manager


@pytest.fixture(scope="session", autouse=True)
def _clear_filesystem():
    shutil.rmtree("data", ignore_errors=True)
    shutil.rmtree("reports", ignore_errors=True)
    shutil.rmtree("test/experimental/data", ignore_errors=True)
    shutil.rmtree("test/experimental/reports", ignore_errors=True)
    yield
    shutil.rmtree("data", ignore_errors=True)
    shutil.rmtree("reports", ignore_errors=True)
    shutil.rmtree("test/experimental/data", ignore_errors=True)
    shutil.rmtree("test/experimental/reports", ignore_errors=True)


@pytest.fixture()
def clear_filesystem():
    shutil.rmtree("data", ignore_errors=True)
    shutil.rmtree("reports", ignore_errors=True)
    shutil.rmtree("test/experimental/data", ignore_errors=True)
    shutil.rmtree("test/experimental/reports", ignore_errors=True)
    yield
    shutil.rmtree("data", ignore_errors=True)
    shutil.rmtree("reports", ignore_errors=True)
    shutil.rmtree("test/experimental/data", ignore_errors=True)
    shutil.rmtree("test/experimental/reports", ignore_errors=True)
