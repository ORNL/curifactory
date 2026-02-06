"""A pipeline file that should error on import"""

import idonotexist

from curifactory.experimental.artifact import Artifact
from curifactory.experimental.caching import JsonCacher
from curifactory.experimental.pipeline import pipeline
from curifactory.experimental.stage import stage


@pipeline
def something():
    return None
