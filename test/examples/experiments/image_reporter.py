import matplotlib.pyplot as plt

import curifactory as cf
from curifactory.caching import JsonCacher
from curifactory.reporting import ImageReporter


@cf.stage(None, ["outputs"], [JsonCacher])
def save_manual_image(record):
    fig, ax = plt.subplots()
    ax.plot([3, 2, 1])
    fig.savefig("testing.png")
    record.report(ImageReporter("testing.png"))

    return {"thing": 13}


def get_params():
    return [cf.ExperimentParameters(name="test")]


def run(argsets, manager):
    for argset in argsets:
        r = cf.Record(manager, argset)
        r = save_manual_image(r)
