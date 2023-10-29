import sys

sys.path.append("../")
from dataclasses import dataclass
from test.examples.stages.cache_stages import agg_store_an_output, store_an_output

import curifactory as cf


@dataclass
class Params(cf.ExperimentParameters):
    a: int = 5
    b: int = 6
    do_agg: bool = False


def get_params():
    return [
        Params(name="thing1"),
        Params(name="thing2", b=10),
        Params(name="thing3", b=4, do_agg=True),
        Params(name="thing4", a=2, b=5, do_agg=True),
    ]


def run(param_sets, manager):
    for param_set in param_sets:
        r = cf.Record(manager, param_set)

        if param_set.do_agg:
            r = agg_store_an_output(r)
        else:
            r = store_an_output(r)
