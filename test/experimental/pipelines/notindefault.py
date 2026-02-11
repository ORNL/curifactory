"""A pipeline file that isn't include in the default pipeline modules"""

from curifactory.experimental.artifact import Artifact
from curifactory.experimental.caching import JsonCacher
from curifactory.experimental.pipeline import pipeline
from curifactory.experimental.stage import stage


@stage(Artifact("some_number"))
def get_number(start: int = 5):
    return start + 3


@stage(Artifact("bad_number"))
def get_invalid_number(start: int = 6):
    return start / 0


@pipeline
def valid(start: int = 2):
    return get_number(start).outputs


@pipeline
def invalid(start: int = 2):
    return get_invalid_number(start).outputs
