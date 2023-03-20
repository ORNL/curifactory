"""This experiment file demonstrates stages that wrap a large output in a ``Lazy`` object.

This means curifactory will unload the object from memory as soon as the stage completes,
and then automatically resolve it in an executing stage that needs it.
"""
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


def get_params():
    return [cf.ExperimentArgs(name="test")]


def run(argsets, manager):
    for argset in argsets:
        record = cf.Record(manager, argset)
        record = use_big_data_directly(make_big_data(record))
