from curifactory.experimental import artifact, caching, experiment, manager, stage


def get_manager():
    return manager.Manager.get_manager()


def get_output_path(output_artifact_index: int = 0) -> stage.OutputArtifactPathResolve:
    return stage.OutputArtifactPathResolve(output_artifact_index)


# https://stackoverflow.com/questions/880530/can-modules-have-properties-the-same-way-that-objects-can
def __getattr__(name):
    if name == "config":
        return get_manager().config
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
