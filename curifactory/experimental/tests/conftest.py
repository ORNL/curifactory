import shutil

import pytest

from curifactory.experimental.manager import Manager


@pytest.fixture()
def test_manager():
    shutil.rmtree("data", ignore_errors=True)
    shutil.rmtree("reports", ignore_errors=True)

    with Manager.from_config({}) as manager:
        yield manager

    shutil.rmtree("data", ignore_errors=True)
    shutil.rmtree("reports", ignore_errors=True)
