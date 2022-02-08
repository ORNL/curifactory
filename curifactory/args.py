"""Contains the parent dataclass ExperimentArgs, containing run-specific config params."""

from dataclasses import dataclass


@dataclass
class ExperimentArgs:
    """Base arguments class, for handling naming and hashing.

    In any given repo, this class should be extended to contain any needed
    local configuration.

    .. note::

        Extending with a :code:`@dataclass` is recommended to make it syntactically
        easier to read and define.

    Example:
        .. code-block:: python

            from dataclasses import dataclass
            from curifactory import ExperimentArgs

            @dataclass
            class Args(ExperimentArgs):
                some_parameter: int = 0
                # ...
    """

    name: str = "UNNAMED"
    """Argument set name. This can be used to easily distinguish/refer to specific
        configurations in aggregate stages. This should be unique for every args instance."""
    hash: str = None
    """Curifactory automatically fills this, but it can be overriden if you need to use
        very specific cache naming. (Should not normally be necessary.)"""
    overwrite: bool = False
    """Whether to overwrite pre-cached values. Curifactory automatically sets this based
        on command line flags."""
