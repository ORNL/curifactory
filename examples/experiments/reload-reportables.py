"""Demonstrates reportables persisting in a report even if the stage it comes from short-circuits."""

import curifactory as cf
from curifactory.caching import JsonCacher
from curifactory.reporting import LinePlotReporter


@cf.stage(None, ["outputs"], [JsonCacher])
def do_things(record):
    record.report(LinePlotReporter([3, 2, 1]))
    return {"lucky_number": 13}


def get_params():
    return [cf.ExperimentArgs(name="test")]


def run(argsets, manager):
    for argset in argsets:
        r = cf.Record(manager, argset)
        r = do_things(r)
