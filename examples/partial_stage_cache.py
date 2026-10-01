"""Reuse an independent output when only part of a stage's cache is present."""

from curifactory import stage
from curifactory.caching import PickleCacher


def compute_expensive():
    return sum(range(1000))


def compute_other():
    return "ready"


@stage([], ["expensive_result", "other_result"], [PickleCacher] * 2)
def make_pair(record):
    expensive_cacher = record.stage_cachers[0]
    if expensive_cacher.check():
        expensive_result = expensive_cacher.load()
    else:
        expensive_result = compute_expensive()
    other_result = compute_other()
    return expensive_result, other_result
