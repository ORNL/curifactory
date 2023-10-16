# flake8: noqa

# make all submodules directly accessible from a single curifactory import
from curifactory import (
    caching,
    docker,
    experiment,
    hashing,
    manager,
    params,
    procedure,
    record,
    reporting,
    staging,
    store,
    utils,
)

# make super important things accessible directly off of the top level module
from curifactory.args import ExperimentArgs  # TODO: remove once fully deprecated
from curifactory.caching import Lazy
from curifactory.hashing import set_hash_functions
from curifactory.manager import ArtifactManager
from curifactory.params import ExperimentParameters
from curifactory.procedure import Procedure
from curifactory.record import Record
from curifactory.staging import (
    CachersMismatchError,
    EmptyCachersError,
    InputSignatureError,
    OutputSignatureError,
    aggregate,
    stage,
)

__version__ = "0.16.0"
