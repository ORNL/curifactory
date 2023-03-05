"""Utility functions for hashing args class instances."""

import hashlib
import json
import os
from copy import deepcopy
from dataclasses import asdict, field, is_dataclass
from typing import Callable, Dict, Union


# TODO: (3/5/2023) - allow passing in a dict directly as well
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


def compute_args_hash(args, dry: bool = False) -> Union[str, Dict]:
    """The actual mechanisms for calculating the hash of an ExperimentArgs class.

    This function takes any overriding ``hashing_functions`` into account, otherwise
    for any members on the dataclass it tries to go through sane defaults:

    1. If the value of the member is ``None``, skip it. This allows default-ignoring
        new parameters.
    2. If a member is another dataclass, recursively ``compute_args_hash`` on it.
        Note that if this is unintended functionality, and you need the default
        dataclass ``repr`` for any reason, you can override it with the following:

        .. code-block:: python

            import curifactory as cf

            @dataclass
            class Args(cf.ExperimentArgs):
                some_other_dataclass: OtherDataclass = None

                hashing_functions = cf.set_hash_functions(
                    some_other_dataclass = lambda self, obj: repr(obj)
                )
                ...

    3. If a member is a callable, by default it might turn up a pointer address
        (we found this occurs with torch modules), so use the ``__qualname__``
        instead.
    4. Otherwise just use the normal ``repr``.

    Args:
        dry (bool): Return a dictionary with each value as the "code" that will be
            used to compute the actual md5 hash. Useful for debugging custom
            hashing functions.
    """
    blacklist = [
        "hash",
        "overwrite",
        "hashing_functions",
    ]  # curifactory experimentargs things we know we don't want
    hashes = {}

    # TODO: probably need a try/except here, iirc non-picklable things fail because of an asdict somewhere?
    hashing_dict = asdict(args)
    for key in hashing_dict.keys():
        value = getattr(args, key)
        # skip things we apriori know we don't want included
        if key in blacklist:
            if dry:
                hashes[key] = f"SKIPPED: curifactory blacklist: {blacklist}"
            continue

        # first check if we've specified how to handle the hash
        if hasattr(args, "hashing_functions") and key in args.hashing_functions:
            if args.hashing_functions[key] is None:
                if dry:
                    hashes[key] = "SKIPPED: set to None in hashing_functions"
                continue
            # TODO: will need to have several types of hashing functions to handle what is getting passed in?
            if dry:
                hashes[
                    key
                ] = f"{args.hashing_functions[key]}(args, {value}) - {args.hashing_functions[key](args, value)}"
            else:
                hashes[key] = args.hashing_functions[key](args, value)

        # if the value of the argument itargs is none, ignore it. This is so that we can default
        # arguments to not be included without setting the hash function for it, and may allow
        # fancier mechanisms in the future to better allow reproducing old experiments using an
        # args class that has since been added to.
        elif value is None:
            if dry:
                hashes[key] = "SKIPPED: value is None"
            continue

        # -- some sane default hashing mechanisms --

        # if it's a dataclass, recursively call compute_args_hash on it, this allows
        # user to separate out subsets of args and still set custom hashing functions
        # on those subsets if they want.
        elif is_dataclass(value):
            hashes[key] = compute_args_hash(value, dry)

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
    # individually compute a hash for each item, and add the integer values up, turning the final number into a hash.
    # this ensures that the order in which things are hashed won't change the hash as long as the values themselves
    # are the same.
    for hash_key, hash_value in hashes.items():
        hash_hex = hashlib.md5((hash_key + str(hash_value)).encode()).hexdigest()
        hash_total += int(hash_hex, 16)

    final_hash = hex(hash_total)[2:]
    return final_hash


def args_hash(
    args, store_in_registry: bool = False, registry_path: str = None, dry: bool = False
) -> Union[str, Dict]:
    """Returns a hex string representing the passed arguments, optionally recording
    the arguments and hash in the params registry.

    Note that this hash is computed once and then stored on the args instance. If values
    on args instance are changed and ``args_hash`` is called again, it won't be reflected
    in the hash.

    Args:
        args (ExperimentArgs): The argument set to hash.
        registry_path (str): The location to keep the :code:`params_registry.json`.
            If this is ``None``, ignore ``store_in_registry``.
        store_in_registry (bool): Whether to update the params registry with the passed
            arguments or not.
        dry (bool): If this is set, don't store and instead of the hash return the
            dictionary of "code" that will be used to hash - useful for debugging.

    Returns:
        The hash string computed from the arguments, or the dictionary of hashing functions
        if ``dry`` is ``True``. (The output from ``compute_args_hash``)
    """
    if dry:
        return compute_args_hash(args, dry=True)

    if args.hash is not None:
        hash_str = args.hash
    else:
        hash_str = compute_args_hash(args, dry=False)

    def stringify(x):
        # NOTE: at some point it may be worth doing fancier logic here. Objects
        # that don't have __str__ implemented will return a string with a pointer,
        # which will always be different regardless
        return str(x)

    # TODO: (3/5/2023) need to rethink how this will be done in light of the hashing functions.
    if store_in_registry and registry_path is not None:
        registry_path = os.path.join(registry_path, "params_registry.json")
        registry = {}

        if os.path.exists(registry_path):
            with open(registry_path) as infile:
                registry = json.load(infile)

        registry[hash_str] = asdict(args)
        with open(registry_path, "w") as outfile:
            json.dump(registry, outfile, indent=4, default=stringify)

    return hash_str


# TODO: (3/5/2023) do I need the same default registry_path to None logic here as in args_hash?
def add_args_combo_hash(
    active_record, records_list, registry_path: str, store_in_registry: bool = False
):
    """Returns a hex string representing the the combined argument set hashes from the
    passed records list. This is mainly used for getting a hash for an aggregate stage,
    which may not have a meaningful argument set of its own.

    Args:
        active_record (Record): The currently in-use record (likely owned by the aggregate
            stage.)
        records_list (List[Record]): The list of records to include as part of the resulting
            hash.
        registry_path (str): The location to keep the :code:`params_registry.json`.
        store_in_registry (bool): Whether to update the params registry with the passed
            records or not.

    Returns:
        The hash string computed from the combined record arguments.
    """

    hashes = []
    for agg_record in records_list:
        if agg_record.args is not None:
            hashes.append(agg_record.args.hash)
        else:
            hashes.append("None")
    hashes = sorted(hashes)

    hashes_for_key = deepcopy(hashes)
    active_key = "None"
    if active_record.args is not None:
        active_key = active_record.args.hash
    hashes_for_key.insert(0, active_key)

    hash_key = str(hashes_for_key)
    hash_str = hashlib.md5(hash_key.encode()).hexdigest()

    if store_in_registry:
        registry_path = os.path.join(registry_path, "params_registry.json")
        registry = {}

        if os.path.exists(registry_path):
            with open(registry_path) as infile:
                registry = json.load(infile)

        registry[hash_str] = {"active": active_key, "arg_list": hashes}
        with open(registry_path, "w") as outfile:
            json.dump(registry, outfile, indent=4, default=lambda x: str(x))
    return hash_str
