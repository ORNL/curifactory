import sys

sys.path.append("test/examples")

from experiments import basic
from stages.basic_stages import get_data, sum_data
from params.basic import Args


from curifactory.manager import ArtifactManager
from curifactory.procedure import Procedure
from curifactory.utils import get_configuration


def test_import():
    """Importing the library should not throw errors!"""
    import curifactory  # noqa: F401 -- we're just trying to make sure it doesn't break


def test_ensure_config(configuration):
    """This is just to make sure the autouse fixture is doing what I expect."""
    assert get_configuration() == configuration


def test_experiment():
    manager = ArtifactManager(dry=True)
    basic.run(
        [
            Args(name="test1", starting_data=[1, 2, 3, 4]),
            Args(name="test2", starting_data=[4, 5, 6]),
        ],
        manager,
    )
    assert manager.records[0].state["sum"] == 10
    assert manager.records[1].state["sum"] == 15


def test_lone_procedure(configuration):
    proc = Procedure([get_data, sum_data], manager=ArtifactManager(dry=True))
    record = proc.run(Args(starting_data=[2, 3]))
    assert record.output == 5
