"""Contains the parent dataclass ExperimentArgs, containing run-specific config params."""

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, Union


# TODO: (3/3/2023) - should this just be a static function on ExperimentArgs?
def set_hash_functions(**kwargs):
    """Convenience function for easily setting the hashing_functions dictionary
    with the appropriate dataclass field. Parameters passed to this function should
    be the same as the parameter name in the args class itself.

    Example:
        .. code-block:: python

            from dataclasses import dataclass
            from curifactory import ExperimentArgs
            from curifactory.args import set_hash_functions

            @dataclass
            class Args(ExperimentArgs):
                a: int = 0
                b: int = 0

                hashing_functions: dict = set_hash_functions(
                    a = lambda self, obj: str(a)
                    b = None  # this means that b will _not be included in the hash_.
                )
    """
    return field(default_factory=lambda: dict(**kwargs), repr=False)


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

    hashing_functions: Dict[str, Union[None, Callable]] = None
    """Assigning these allows overriding how the hash for a specific argument is computed.
        Every key should be assigned a value of either None or a function that takes self
        (the entire args instance) and the value of the named parameter to be hashed."""

    def args_hash(self, dry: bool = False):
        """If dry, just output the "code" that will be run to compute the hash"""
        blacklist = [
            "hash",
            "overwrite",
            "hashing_functions",
        ]  # curifactory experimentargs things we know we don't want
        hashes = {}

        # TODO: probably need a try/except here, iirc non-picklable things fail because of an asdict somewhere?
        hashing_dict = asdict(self)
        for key, value in hashing_dict.items():
            # skip things we apriori know we don't want included
            if key in blacklist:
                if dry:
                    hashes[key] = f"SKIPPED: curifactory blacklist: {blacklist}"
                continue

            # first check if we've specified how to handle the hash
            if key in self.hashing_functions:
                if self.hashing_functions[key] is None:
                    if dry:
                        hashes[key] = "SKIPPED: set to None in hashing_functions"
                    continue
                # TODO: will need to have several types of hashing functions to handle what is getting passed in?
                if dry:
                    hashes[
                        key
                    ] = f"{self.hashing_functions[key]}(self, {value}) - {self.hashing_functions[key](self, value)}"
                else:
                    hashes[key] = self.hashing_functions[key](self, value)

            # if the value of the argument itself is none, ignore it. This is so that we can default
            # arguments to not be included without setting the hash function for it, and may allow
            # fancier mechanisms in the future to better allow reproducing old experiments using an
            # args class that has since been added to.
            elif value is None:
                if dry:
                    hashes[key] = "SKIPPED: value is None"
                continue

            # -- some sane default hashing mechanisms --

            # if it's another experiment args subclass, make sure to call its' args_hash
            elif hasattr(value, "args_hash"):
                hashes[key] = value.args_hash(dry)

            # use the function name if it's a callable, rather than a pointer address
            elif isinstance(value, Callable):
                if dry:
                    hashes[key] = f"{value}.__qualname__ - {value.__qualname__}"
                else:
                    hashes[key] = value.__qualname__

            # otherwise just use the default representation!
            else:
                if dry:
                    hashes[key] = f"repr(value) - {repr(value)}"
                else:
                    hashes[key] = repr(value)

        if dry:
            return hashes

        hash_total = 0
        # individual compute a hash for each item, and add the integer values up, turning the final number into a hash.
        # this ensures that the order in which things are hashed won't change the hash as long as the values themselves
        # are the same.
        for hash_key, hash_value in hashes.items():
            hash_hex = hashlib.md5(str(hash_value).encode()).hexdigest()
            hash_total += int(hash_hex, 16)

        final_hash = hex(hash_total)[2:]
        return final_hash
