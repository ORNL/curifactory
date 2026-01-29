"""Demonstrates reportables persisting in a report even if the stage it comes from short-circuits."""

import matplotlib.pyplot as plt

import curifactory as cf
from curifactory.caching import JsonCacher
from curifactory.reporting import ImageReporter, LinePlotReporter


@cf.stage(None, ["outputs"], [JsonCacher])
def do_things(record):
    record.report(LinePlotReporter([3, 2, 1]))

    fig, ax = plt.subplots()
    ax.plot([3, 2, 1])
    fig.savefig("testing.png")
    record.report(ImageReporter("testing.png"))

    return {"lucky_number": 13}


def get_params():
    return [cf.ExperimentParameters(name="test")]


def run(argsets, manager):
    for argset in argsets:
        r = cf.Record(manager, argset)
        r = do_things(r)
