from curifactory.experimental import artifact, caching, experiment, manager, stage


def get_manager():
    return manager.Manager.get_manager()


# https://stackoverflow.com/questions/880530/can-modules-have-properties-the-same-way-that-objects-can
def __getattr__(name):
    if name == "config":
        return get_manager().config
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
