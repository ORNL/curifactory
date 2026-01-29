"""This experiment file demonstrates stages that wrap a large output in a ``Lazy`` object.

This means curifactory will unload the object from memory as soon as the stage completes,
and then automatically resolve it in an executing stage that needs it.
"""

from dataclasses import dataclass

import numpy as np

import curifactory as cf
from curifactory.caching import PickleCacher


@cf.stage(None, [cf.Lazy("big_data")], [PickleCacher])
def make_big_data(record):
    """Note that 'lazy' is something that is applied directly to the output
    string, not the cacher. You must specify a cacher to use when using a lazy
    object - if one is not provided and an entire experiment is being run in lazy
    mode, a PickleCacher will be assumed. (See the ``--lazy`` flag.)"""
    data = np.random.rand(10 * 1024 * 1024)
    return data


@cf.stage(["big_data"], ["modified_big_data"])
def use_big_data_directly(record, big_data):
    """When this stage executes, ``big_data`` will be reloaded into memory
    with the cacher and passed in from the record state as normal."""
    modified_big_data = big_data / 2
    return modified_big_data


@cf.stage(None, [cf.Lazy("big_data", resolve=False)], [PickleCacher])
def make_big_data_no_resolve(record):
    """We set resolve to False on the output - this means that when it's
    requested as an input in another stage, it won't automatically call
    load on the cacher, instead passing in the lazy instance itself. This
    can be useful if you're using a stage that's calling an external script,
    and you just want to pass the path to it, rather than loading it into
    memory."""
    data = np.random.rand(10 * 1024 * 1024)
    return data


@cf.stage(["big_data"], [])
def use_big_data_no_resolve(record, big_data):
    """Here we assume we get a no-resolve lazy instance."""
    print(big_data.cacher.get_path())
    # we can still get the data like we normally could by calling load()
    # on the cacher
    data = big_data.load()
    print(len(data))


@dataclass
class Params(cf.ExperimentParameters):
    in_memory: bool = False


def get_params():
    return [
        Params(name="LazyResolve", in_memory=True),
        Params(name="LazyNoResolve", in_memory=False),
    ]


def run(param_sets, manager):
    for param_set in param_sets:
        record = cf.Record(manager, param_set)
        if param_set.in_memory:
            record = use_big_data_directly(make_big_data(record))
        else:
            record = use_big_data_no_resolve(make_big_data_no_resolve(record))
