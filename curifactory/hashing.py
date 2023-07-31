"""Utility functions for generating hashes and for parameter sets.

The hash of a parameter set is crucial to curifactory, as this hash gets
prefixed to filenames stored in the cache and so is used to determine whether a
particular artifact has already been computed for the given parameter set.

The basic idea of this hash computation is that some representation for every
parameter in a parameter set is retrieved, which is then turned into a string,
and the md5 hash of that string is then computed. The integer value of the
resulting md5 hashes of each parameter is added up, and the final integer is
turned back into a string hex "hash".

An important concept is the ability to modify any given parameter's
representation that is used for the md5 hash, and whether it's included as part
of the overall hash at all. Some types of objects in python by default will only
return a memory pointer when ``repr`` is called (which is the default mechanism
we use for getting a string representation,) which means that every time an
experiment is run, even if the parameters _should_ be the exact same, the hash
will be different. By setting a dictionary of ``hash_representations`` on the
parameter class, we can indivdiually control the representation computation for
each parameter. We can also set the parameter representation to ``None``, which
means it will be ignored for the purposes of the hash. This is useful for
"operational parameters", or configuration of an experimeriment that wouldn't
actually modify the artifacts.  (e.g. the number of gpu's to train an ML model
on and so forth.)

TODO: examples? (prob put this in the non-python-file docs)
"""

import hashlib
import json
import os
from copy import deepcopy
from dataclasses import field, fields, is_dataclass
from typing import Any, Callable, Union

PARAMETERS_BLACKLIST = ["name", "hash", "overwrite", "hash_representations"]
"""The default parameters on the ExperimentParameters class that we always
ignore as part of the hash."""


def set_hash_functions(*args, **kwargs):
    """Convenience function for easily setting the hash_representations dictionary
    with the appropriate dataclass field. Parameters passed to this function should
    be the same as the parameter name in the parameters class itself.

    You can either call this function and pass in a dictionary with the hashing functions,
    or pass each hashing function as a kwarg. If you pass in both a dictionary as the first
    positional arg and specify kwargs, the kwarg hashing functions will be added to the
    dictionary.

    Example:
        .. code-block:: python

            from dataclasses import dataclass
            from curifactory import ExperimentParameters
            from curifactory.params import set_hash_functions

            @dataclass
            class Params(ExperimentParameters):
                a: int = 0
                b: int = 0

                hash_representations: dict = set_hash_functions(
                    a = lambda self, obj: str(a)
                    b = None  # this means that b will _not be included in the hash_.
                )
    """
    if len(args) > 0:
        if type(args[0]) != dict:
            raise ValueError(
                "If providing a positional arg to set_hash_functions, it must be a dictionary."
            )
        return field(default_factory=lambda: {**(args[0]), **kwargs}, repr=False)
    return field(default_factory=lambda: dict(**kwargs), repr=False)


def get_parameter_hash_value(param_set, param_name: str) -> tuple[str, Any]:
    """Determines which hashing representation mechanism to use for the specified
    parameter, computes the result of the mechanism, and returns both.

    This function takes any overriding ``hash_representations`` into account. The list of mechanisms
    it attempts to use to get a hashable representation of the parameter in order are:

    1. Skip any blacklisted internal curifactory parameters that shouldn't affect the hash.
        This includes `name`, `hash`, `overwrite`, and the `hash_representations` attribute
        itself.
    2. If the value of the parameter is ``None``, skip it. This allows default-ignoring
        new parameters.
    3. If there's an associated hashing function in ``hash_representations``, call that,
        passing in the entire parameter set and the current value of the parameter to
        be hashed
    4. If a parameter is another dataclass, recursively ``get_paramset_hash_values`` on it.
        Note that if this is unintended functionality, and you need the default
        dataclass ``repr`` for any reason, you can override it with the following:

        .. code-block:: python

            import curifactory as cf

            @dataclass
            class Params(cf.ExperimentParameters):
                some_other_dataclass: OtherDataclass = None

                hash_representations = cf.set_hash_functions(
                    some_other_dataclass = lambda self, obj: obj.__class__
                )
                ...

    5. If a parameter is a callable, by default it might turn up a pointer address
        (we found this occurs with torch modules), so use the ``__qualname__``
        instead.
    6. Otherwise just use the normal ``repr``.

    Args:
        parameter_set: The parameter set (dataclass instance) to get the requested parameter from.
        parameter_name (str): The name of the parameter to get the hashable representation of.

    Returns:
        A tuple where the first element is the strategy used to compute the hashable representation,
        and the second element is that computed representation.
    """
    value = getattr(param_set, param_name)

    # 1. skip things we apriori know we don't want included
    if param_name in PARAMETERS_BLACKLIST:
        return ("SKIPPED: blacklist", None)

    # 2. see if user has specified how to handle the hash representation
    if (
        hasattr(param_set, "hash_representations")
        and param_name in param_set.hash_representations
    ):
        if param_set.hash_representations[param_name] is None:
            return ("SKIPPED: set to None in hash_representations", None)
        return (
            f"param_set.hash_representations['{param_name}'](param_set, param_set.{param_name})",
            param_set.hash_representations[param_name](param_set, value),
        )

    # 3. if the value of the argument is none, ignore it. This is so that we can default
    # arguments to not be included without setting the hash function for it, and may allow
    # fancier mechanisms in the future to better allow reproducing old experiments using a
    # parameters class that has since been added to.
    elif value is None:
        return ("SKIPPED: value is None", None)

    # -- some sane default hashing mechanisms --

    # 4. if it's a dataclass, recursively call get_param_set_hash_values on it, this allows
    # user to separate out subsets of parameters and still set custom hashing functions
    # on those subsets if they want.
    elif is_dataclass(value):
        return (
            f"get_param_set_hash_values(param_set, {param_name})",
            get_param_set_hash_values(value),
        )

    # 5. use the function name if it's a callable, rather than a pointer address
    elif isinstance(value, Callable):
        return ("value.__qualname__", value.__qualname__)

    # 6. otherwise just use the default representation!
    return (f"repr(param_set.{param_name})", repr(value))


def get_param_set_hash_values(param_set) -> dict[str, tuple[str, Any]]:
    """Collect the hash representations from every parameter in the passed parameter set.

    This essentially just calls ``get_parameter_hash_value`` on every parameter.

    Returns:
        A dictionary keyed by the string parameter names, and the value the dry tuple result
        from ``get_parameter_hash_value``.
    """
    # TODO: raise_error if param_set is not a dataclass?
    return {
        param.name: get_parameter_hash_value(param_set, param.name)
        for param in fields(param_set)
    }


def _compute_hash_part(hash_representations: dict[str, tuple[str, Any]]) -> int:
    """Recursive computation for the integer value of the hash of a passed hash_values dictionary."""
    hash_total = 0
    for hash_key, (hash_rep, hash_rep_value) in hash_representations.items():
        if hash_rep_value is None:
            continue

        # make sure to recursively compute on any subdataclasses
        if hash_rep.startswith("get_param_set_hash_values"):
            hash_total += _compute_hash_part(hash_rep_value)
        else:
            # Note that we concatenate the string of the value with the hash key, otherwise if two parameters had eachother's
            # values in another parameter set, they'd compute the same hash which is decidedly not correct.
            hash_hex = hashlib.md5(f"{hash_key}{hash_rep_value}".encode()).hexdigest()
            hash_total += int(hash_hex, 16)
    return hash_total


def compute_hash(hash_representations: dict[str, tuple[str, Any]]) -> str:
    """Returns a combined order-independent md5 hash of the passed representations.

    We do this by individually computing a hash for each item, and add the integer values up,
    turning the final number into a hash string.  this ensures that the order in which
    things are hashed won't change the hash as long as the values themselves are
    the same.
    """

    hash_total = _compute_hash_part(hash_representations)
    final_hash = f"{hash_total:x}"  # convert to a hexadecimal hash string
    return final_hash


# TODO: (3/10/2023) allow flag to still at least show the values of ignored parameters
def param_set_string_hash_representations(param_set) -> dict[str, str]:
    """Get the hash representation of a parameter set into a json-dumpable dictionary.

    This is used both in the output report as well as in the params registry.
    """
    hash_reps = get_param_set_hash_values(param_set)
    rep_dictionary = {}
    skipped = {}
    for key, rep_tuple in hash_reps.items():
        if key == "name":
            rep_dictionary[key] = param_set.name
        # check for a sub-dataclass, which might have ignored params of its own
        elif rep_tuple[0].startswith("get_param_set_hash_values"):
            rep_dictionary[key] = param_set_string_hash_representations(
                getattr(param_set, key)
            )
        elif rep_tuple[1] is not None:
            rep_dictionary[key] = str(rep_tuple[1])
        elif key in PARAMETERS_BLACKLIST:
            continue
        else:
            try:
                # separately handle a sub-dataclass, since we won't get the right strategy if it was skipped
                if is_dataclass(getattr(param_set, key)):
                    skipped[key] = param_set_string_hash_representations(
                        getattr(param_set, key)
                    )
                else:
                    skipped[key] = str(getattr(param_set, key))
            except:  # noqa: E722
                skipped[key] = None
    if len(skipped) > 0:
        rep_dictionary["IGNORED_PARAMS"] = skipped
    return rep_dictionary


def hash_param_set(
    param_set,
    store_in_registry: bool = False,
    registry_path: str = None,
    dry: bool = False,
) -> Union[str, dict]:
    """Returns a hex string representing the passed arguments, optionally recording
    the parameters and hash in the params registry.

    Note that this hash is computed once and then stored on the parameter set. If values
    on parameter set are changed and ``hash_param_set`` is called again, it won't be reflected
    in the hash.

    Args:
        param_set (ExperimentParameters): The argument set to hash.
        registry_path (str): The location to keep the :code:`params_registry.json`.
            If this is ``None``, ignore ``store_in_registry``.
        store_in_registry (bool): Whether to update the params registry with the passed
            arguments or not.
        dry (bool): If ``True``, don't store and instead return a dictionary
            with each value as the tuple that contains the strategy used to compute
            the values to be hashed as well as the output from that hashing function
            code. Useful for debugging custom hashing functions.

    Returns:
        The hash string computed from the arguments, or the dictionary of hashing functions
        if ``dry`` is ``True``. (The output from ``get_param_set_hash_values``)
    """
    hash_reps = get_param_set_hash_values(param_set)
    if dry:
        return hash_reps

    # if the hash has already been calculated/stored in the parameter set, use that
    # NOTE: I think this is also what allows someone to manually set a hash? This
    # functionality is untested
    if param_set.hash is not None:
        hash_str = param_set.hash
    else:
        # otherwise compute the integer for the hash representations and get the hex
        # string for it
        hash_str = compute_hash(hash_reps)

    # handle saving the hash and associated parameters in the registry
    if store_in_registry and registry_path is not None:
        registry_path = os.path.join(registry_path, "params_registry.json")
        registry = {}

        if os.path.exists(registry_path):
            with open(registry_path) as infile:
                registry = json.load(infile)

        registry[hash_str] = param_set_string_hash_representations(param_set)
        with open(registry_path, "w") as outfile:
            json.dump(registry, outfile, indent=4, default=lambda x: str(x))

    return hash_str


# TODO: (3/5/2023) do I need the same default registry_path to None logic here as in hash_param_set?
def add_params_combo_hash(
    active_record, records_list, registry_path: str, store_in_registry: bool = False
):
    """Returns a hex string representing the the combined parameter set hashes from the
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
        if agg_record.params is not None:
            hashes.append(agg_record.params.hash)
        else:
            hashes.append("None")
    hashes = sorted(hashes)

    hashes_for_key = deepcopy(hashes)
    active_key = "None"
    if active_record.params is not None:
        active_key = active_record.params.hash
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
