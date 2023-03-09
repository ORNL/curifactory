import sys

sys.path.append("../")

from test.examples.stages.basic_stages import get_data, sum_data

from curifactory.manager import ArtifactManager
from curifactory.procedure import Procedure


def run(argsets, manager: ArtifactManager):
    pipeline = Procedure([get_data, sum_data], manager)

    for argset in argsets:
        output = pipeline.run(argset)
        print(output)
