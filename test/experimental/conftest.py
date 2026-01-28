import shutil

import pytest

from curifactory.experimental.manager import Manager


@pytest.fixture()
def test_manager():
    # with Manager.from_config({"default_pipeline_modules": ["pipelines.example"]}) as manager:
    #     yield manager
    manager = Manager.from_config(
        {"default_pipeline_modules": ["test.experimental.pipelines.example"]}
    )
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
