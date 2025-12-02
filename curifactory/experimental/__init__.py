from curifactory.experimental import artifact, caching, experiment, manager, stage


def get_manager():
    return manager.Manager.get_manager()
