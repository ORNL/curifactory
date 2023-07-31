from test.examples.stages.basic_stages import get_data

import curifactory as cf


def run(param_sets, manager: cf.ArtifactManager):
    for param_set in param_sets:
        results = get_data(cf.Record(manager, param_set))

    return results
