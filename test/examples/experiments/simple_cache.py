import sys

sys.path.append("../")
from dataclasses import dataclass
from test.examples.stages.cache_stages import store_an_output

import curifactory as cf


@dataclass
class Params(cf.ExperimentParameters):
    a: int = 5
    b: int = 6


def get_params():
    return [Params(name="thing1"), Params(name="thing2", b=10)]


def run(param_sets, manager):
    for param_set in param_sets:
        r = cf.Record(manager, param_set)
        r = store_an_output(r)
