import json
import os
import pytest
import shutil

from pytest_mock import mocker  # noqa: F401 -- flake8 doesn't see it's used as fixture

# import curifactory.experiment  # noqa: F401 -- flake8 doesn't see it's used in mock
from curifactory.manager import ArtifactManager
from curifactory.args import ExperimentArgs


@pytest.fixture()
def sample_args():
    return ExperimentArgs(name="sample_args", hash="sample_hash")


@pytest.fixture(autouse=True)
def configuration_file(configuration):
    with open("curifactory_config.json", "w") as outfile:
        json.dump(configuration, outfile)
    yield
    try:
        os.remove("curifactory_config.json")
    except FileNotFoundError:
        pass


@pytest.fixture(scope="session")
def configuration():
    config = {
        "experiments_module_name": "test.examples.experiments",
        "params_module_name": "test.examples.params",
        "manager_cache_path": "test/examples/data",
        "cache_path": "test/examples/data/cache",
        "runs_path": "test/examples/data/runs",
        "logs_path": "test/examples/logs",
        "notebooks_path": "test/examples/notebooks",
        "reports_path": "test/examples/reports",
        "report_css_path": "test/examples/reports/style.css",
    }
    return config


@pytest.fixture()
def configured_test_manager(
    mocker, configuration  # noqa: F811 -- mocker has to be passed in as fixture
):
    shutil.rmtree("test/examples/data", ignore_errors=True)
    mock = mocker.patch("curifactory.utils.get_configuration")
    mock.return_value = configuration

    yield ArtifactManager("test", live_log_debug=True)
    shutil.rmtree("test/examples/data", ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def clear_proj_root():
    yield
    shutil.rmtree("reports", ignore_errors=True)
    shutil.rmtree("test/examples/data", ignore_errors=True)


@pytest.fixture()
def clear_filesystem():
    shutil.rmtree("test/examples/data", ignore_errors=True)
    yield
    shutil.rmtree("test/examples/data", ignore_errors=True)
