import sys

sys.path.append("../")

from curifactory.procedure import Procedure
from curifactory.manager import ArtifactManager
from stages.basic_stages import get_data, sum_data


def run(argsets, manager: ArtifactManager):
    pipeline = Procedure([get_data, sum_data], manager)

    for argset in argsets:
        output = pipeline.run(argset)
        print(output)
