"""This module contains a revised design and API for a more pipeline and artifact oriented framework."""

from typing import Any

from curifactory.experimental import (  # pipeline,; stage,
    artifact,
    caching,
    manager,
    reporting,
    utils,
)
from curifactory.experimental.artifact import Artifact, ArtifactList, DBArtifact
from curifactory.experimental.pipeline import Pipeline, PipelineFromRef, pipeline
from curifactory.experimental.stage import (
    ConfigResolve,
    OutputArtifactPathResolve,
    Stage,
    run_as_stage,
    stage,
)

# cache statuses
IN_CACHE = 1
NOT_IN_CACHE = 2
NO_CACHER = 3

# artifact/stage mapping statuses
COMPUTE = 4
SKIP = 5
USE_CACHE = 6
OVERWRITE = 7


def status(val: int) -> str:
    if val == COMPUTE:
        return "COMPUTE"
    elif val == SKIP:
        return "SKIP"
    elif val == IN_CACHE:
        return "IN_CACHE"
    elif val == NOT_IN_CACHE:
        return "NOT_IN_CACHE"
    elif val == NO_CACHER:
        return "NO_CACHER"
    elif val == USE_CACHE:
        return "USE_CACHE"
    elif val == OVERWRITE:
        return "OVERWRITE"


def report(reportable: reporting.Reportable):
    current_manager = get_manager()
    # TODO: maybe adding a reportable is a function on the stage?
    current_manager.current_stage.reportables_list.append(reportable)
    # reportable.stage = current_manager.current_stage


def get_manager():
    return manager.Manager.get_manager()


def global_config() -> dict[str, Any]:
    return manager.Manager.get_manager().additional_configuration


def get_output_path(output_artifact_index: int = 0) -> OutputArtifactPathResolve:
    return OutputArtifactPathResolve(output_artifact_index)


# https://stackoverflow.com/questions/880530/can-modules-have-properties-the-same-way-that-objects-can
def __getattr__(name):
    if name == "config":
        return get_manager().config
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


@stage(
    Artifact("{prior_artifact.name}", caching.FileReferenceCacher()),
    pass_self=True,
)
def convert_artifact_to_path(self, prior_artifact):
    # TODO: ability to remove obj from memory
    return self.artifacts[0].get_path()


@stage(Artifact("path_collection", caching.FileReferenceCacher()), pass_self=True)
def get_artifact_paths(self, *artifacts):
    artifact_list = self.artifacts
    path_list = []
    for art in artifact_list:
        path_list.append(art.cacher.get_path())
    return path_list
