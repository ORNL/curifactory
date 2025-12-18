from curifactory.experimental import artifact, caching, manager, pipeline, stage, utils


def get_manager():
    return manager.Manager.get_manager()


def get_output_path(output_artifact_index: int = 0) -> stage.OutputArtifactPathResolve:
    return stage.OutputArtifactPathResolve(output_artifact_index)


# https://stackoverflow.com/questions/880530/can-modules-have-properties-the-same-way-that-objects-can
def __getattr__(name):
    if name == "config":
        return get_manager().config
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


@stage.stage(
    artifact.Artifact("{prior_artifact.name}", caching.FileReferenceCacher()),
    pass_self=True,
)
def convert_artifact_to_path(self, prior_artifact):
    # TODO: ability to remove obj from memory
    return self.artifacts[0].get_path()


@stage.stage(
    artifact.Artifact("path_collection", caching.FileReferenceCacher()), pass_self=True
)
def get_artifact_paths(self, *artifacts):
    artifact_list = self.artifacts
    path_list = []
    for art in artifact_list:
        path_list.append(art.cacher.get_path())
    return path_list
