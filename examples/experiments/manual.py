"""An example of a manual experiment script, bypassing cf's CLI.

This isn't recommended for most use-cases, this is primarily to demonstrate
how curifactory can be used/run from a non "curifactory context".
"""

from dataclasses import dataclass
from logging import basicConfig, getLogger

from curifactory import ArtifactManager, ExperimentParameters, Record, stage
from curifactory.caching import Lazy, PickleCacher

LOGGER = getLogger(__name__)


@dataclass
class MyParams(ExperimentParameters):
    number: float = 1.0


@stage(inputs=None, outputs=[Lazy("initial_value")], cachers=[PickleCacher])
def get_initial_value(record):
    my_value = 5
    LOGGER.error("THIS IS A LOG MESSAGE")
    return my_value * record.params.number


@stage(inputs=["initial_value"], outputs=["final_value"], cachers=[PickleCacher])
def multiply_again(record, initial_value):
    return initial_value * record.params.number


if __name__ == "__main__":
    manager = ArtifactManager("experiment_one", disable_non_cf_loggers=False)
    basicConfig(filename="logs/this.log", force=True)
    param_grid = [MyParams(number=number) for number in (0, 1, 2, 2)]
    for param in param_grid:
        record = Record(manager, param)
        result = multiply_again(get_initial_value(record))
    manager.generate_report()
