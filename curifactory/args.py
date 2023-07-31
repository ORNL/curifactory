"""This module is deprecated and will be removed soon, see ``curifactory.params``."""

from dataclasses import dataclass

from curifactory.params import ExperimentParameters
from curifactory.utils import _warn_deprecation


@dataclass
class ExperimentArgs(ExperimentParameters):
    """DEPRECATED. Use ``curifactory.params.ExperimentParameters``"""

    def __post_init__(self):
        _warn_deprecation(
            "'curifactory.args.ExperimentArgs' has been deprecated and will likely be removed in 0.16.0. Please use 'curifactory.params.ExperimentParameters'"
        )

    def __init_subclass__(cls) -> None:
        _warn_deprecation(
            "'curifactory.args.ExperimentArgs' has been deprecated and will likely be removed in 0.16.0. Please use 'curifactory.params.ExperimentParameters'"
        )
        return super().__init_subclass__()
