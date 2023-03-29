"""Contains the parent dataclass ExperimentArgs, containing run-specific config params."""

from dataclasses import dataclass, field
from typing import Callable, Union

from curifactory import hashing


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

    # NOTE: may be able to take parent classes' hashing functions into account as well
    # https://stackoverflow.com/questions/10091957/get-parent-class-name
    hash_representations: dict[str, Union[None, Callable]] = field(
        default_factory=dict, repr=False
    )
    """Dictionary of parameter names in the dataclass where you can provide functions
        that return a unique/consistent representation for each parameter to use as
        the value for hashing.  Setting these allow control over what counts as a
        cache miss/cache hit. Sane defaults are applied to any parameters that don't
        have a representation function specified here. (see ``hashing.get_parameter_hash_value``)

        Any function provided is expected to take self (the entire args instance) and
        the value of the named parameter to be hashed.

        You can also provide ``None`` for any parameters in order to exclude their value
        from the hash entirely. (This is useful for operational arguments e.g. the number
        of GPU's or processes to run on, where you would not want changing that to invalidate
        the existing cached values.)
    """

    # TODO: implement __eq__ based on args_hash

    def args_hash(self, dry=False):
        """Convenience function to see the hash of these args that curifactory is
        computing, or debug them with ``dry=True``."""
        return hashing.args_hash(self, store_in_registry=False, dry=dry)
