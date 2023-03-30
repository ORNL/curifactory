"""Ensure the args hashing works as expected."""

from dataclasses import dataclass

import curifactory as cf
from curifactory.hashing import parameters_string_hash_representation


def test_args_subclass_hash_includes_all_sub_params():
    """The hash of a subclass of experiment args should include all of the subclass's
    parameters."""

    @dataclass
    class MyExperimentArgs(cf.ExperimentArgs):
        a: int = 0
        b: int = None

    args1 = MyExperimentArgs(name="test", a=6, b=7)
    dry_hash_dict = args1.args_hash(dry=True)
    assert dry_hash_dict["a"] == ("repr(param_set.a)", "6")
    assert dry_hash_dict["b"] == ("repr(param_set.b)", "7")

    # make sure we correctly don't hash everything in the blacklist
    for should_skip in ["name", "hash", "overwrite", "hash_representations"]:
        assert dry_hash_dict[should_skip][0] == "SKIPPED: blacklist"

    # double check that different args with different params is in fact
    # a different hash
    args2 = MyExperimentArgs(a=5, b=6)
    assert args1.args_hash() != args2.args_hash()


def test_static_hashing_function_same_when_vals_diff():
    """Two instances of an args class where a value is different but the hashing mechanism
    is a function that returns the same value should both have the same hash."""

    @dataclass
    class MyExperimentArgs(cf.ExperimentArgs):
        a: int = 0
        b: int = None

        hash_representations: dict = cf.set_hash_functions(a=lambda self, obj: 5)

    args1 = MyExperimentArgs()
    args2 = MyExperimentArgs(a=6)
    assert args1.args_hash() == args2.args_hash()


def test_none_hashing_function_same_when_vals_diff():
    """An argument in an args class with a hashing function set to none should not be
    taken into account in the output hash."""

    @dataclass
    class MyExperimentArgs(cf.ExperimentArgs):
        a: int = 0
        b: int = 5

        hash_representations: dict = cf.set_hash_functions(a=None)

    args1 = MyExperimentArgs()
    args2 = MyExperimentArgs(a=6)
    assert args1.args_hash() == args2.args_hash()
    assert (
        args1.args_hash(dry=True)["a"][0]
        == "SKIPPED: set to None in hash_representations"
    )


def test_none_value_not_hashed():
    """An args class with a parameter set to None should not have that parameter included
    in the hash.

    This also demonstrates that you can add new arguments to an old class and old experiments
    will still run as long as the new args are defaulted to None.
    """

    @dataclass
    class MyExperimentArgs1(cf.ExperimentArgs):
        a: int = 0
        b: int = None

    @dataclass
    class MyExperimentArgs2(cf.ExperimentArgs):
        a: int = 0

    args1 = MyExperimentArgs1()
    args2 = MyExperimentArgs2()

    assert args1.args_hash() == args2.args_hash()
    assert args1.args_hash(dry=True)["b"][0] == "SKIPPED: value is None"


def test_new_param_none_hash_same_result():
    """Adding a new parameter to a parameterclass, but is added as None to hash representations should
    still hash to the same value.
    """

    @dataclass
    class MyExperimentArgs1(cf.ExperimentArgs):
        a: int = 0

    @dataclass
    class MyExperimentArgs2(cf.ExperimentArgs):
        a: int = 0
        b: int = 3

        hash_representations: dict = cf.set_hash_functions(b=None)

    args1 = MyExperimentArgs1()
    args2 = MyExperimentArgs2()

    assert args1.args_hash() == args2.args_hash()
    assert (
        args2.args_hash(dry=True)["b"][0]
        == "SKIPPED: set to None in hash_representations"
    )


def test_invalid_dataclassparam_should_not_change_hash():
    """Adding a parameter without a typehint (e.g. not a valid dataclass field) should not impact
    the hash."""

    @dataclass
    class MyExperimentArgs1(cf.ExperimentArgs):
        a: int = 0
        b = 3

        hash_representations: dict = cf.set_hash_functions(b=None)

    @dataclass
    class MyExperimentArgs2(cf.ExperimentArgs):
        a: int = 0
        b: int = 4

        hash_representations: dict = cf.set_hash_functions(b=None)

    args1 = MyExperimentArgs1()
    args2 = MyExperimentArgs2(b=7)

    assert args1.args_hash() == args2.args_hash()


def test_new_ignored_param_sub_dataclass():
    """Adding a new (none-ignored) parameter to a subdatclass should not change the overall hash."""

    @dataclass
    class SubArgs1:
        a: int = 0

    @dataclass
    class SubArgs2:
        a: int = 0
        b: int = 5

        hash_representations: dict = cf.set_hash_functions(b=None)

    @dataclass
    class Args1(cf.ExperimentArgs):
        sub: SubArgs1 = SubArgs1()

    @dataclass
    class Args2(cf.ExperimentArgs):
        sub: SubArgs2 = SubArgs2()

    a1 = Args1()
    a2 = Args2()

    assert a1.args_hash() == a2.args_hash()


def test_parameter_name_included_in_hash():
    """Parameter names should be involved in hashing - two args instances where parameters are the
    opposite of eachother should not hash to the same value."""

    @dataclass
    class MyExperimentArgs(cf.ExperimentArgs):
        a: int = 0
        b: int = 1

    args1 = MyExperimentArgs(a=5, b=6)
    args2 = MyExperimentArgs(a=6, b=5)
    assert args1.args_hash() != args2.args_hash()


def test_custom_hashing_composed_dataclasses():
    """Composing multiple dataclasses into an experimentargs class should allow setting
    hashing functions on the other dataclasses."""

    @dataclass
    class NormalDC:
        c: int = 5
        d: int = 6

        hash_representations: dict = cf.set_hash_functions(d=None)

    @dataclass
    class MyExperimentArgs(cf.ExperimentArgs):
        a: int = 0
        b: int = 1
        others: NormalDC = NormalDC()

    args1 = MyExperimentArgs()
    args2 = MyExperimentArgs(others=NormalDC(d=7))
    assert args1.args_hash() == args2.args_hash()
    assert type(args1.args_hash(True)["others"][1]) == dict
    assert (
        args1.args_hash(True)["others"][1]["d"][0]
        == "SKIPPED: set to None in hash_representations"
    )


def test_composed_dataclasses_diff():
    """Composing multiple dataclasses into an experimentargs class should correctly
    change the hash if those sub arguments are different."""

    @dataclass
    class NormalDC:
        c: int = 5
        d: int = 6

    @dataclass
    class MyExperimentArgs(cf.ExperimentArgs):
        a: int = 0
        b: int = 1
        others: NormalDC = NormalDC()

    args1 = MyExperimentArgs()
    args2 = MyExperimentArgs(others=NormalDC(d=7))
    assert args1.args_hash() != args2.args_hash()


def test_set_hash_functions_with_kwargs():
    """calling set_hash_functions with kwargs should set a dictionary with the
    args as keys."""

    @dataclass
    class MyExperimentArgs(cf.ExperimentArgs):
        a: int = 0
        b: int = None

        hash_representations: dict = cf.set_hash_functions(a=None, b=None)

    args = MyExperimentArgs()
    assert "a" in args.hash_representations
    assert "b" in args.hash_representations


def test_set_hash_functions_with_dict_arg():
    """calling set_hash_functions with a single dictionary should directly set
    the hash_representations."""

    @dataclass
    class MyExperimentArgs(cf.ExperimentArgs):
        a: int = 0
        b: int = None

        hash_representations: dict = cf.set_hash_functions({"a": None, "b": None})

    args = MyExperimentArgs()
    assert "a" in args.hash_representations
    assert "b" in args.hash_representations


def test_set_hash_functions_with_dict_and_kwargs():
    """calling set_hash_functions with both a dictionary and kwargs should create
    a merged dictionary."""

    @dataclass
    class MyExperimentArgs(cf.ExperimentArgs):
        a: int = 0
        b: int = None
        c: int = 5

        hash_representations: dict = cf.set_hash_functions(
            {"a": None, "b": None}, b="something else", c=None
        )

    args = MyExperimentArgs()
    assert "a" in args.hash_representations
    assert "b" in args.hash_representations
    assert "c" in args.hash_representations

    # kwargs should override what was in possitional arg
    assert args.hash_representations["b"] is not None

    """Subclassing an args class with hashing functions set and including additional
    hashing functions in the subclass should add/use the hashing functions of both."""

    """Subclassing an args class with hashing functions set and including hashing
    functions in the subclass for the same parameter name should 'override' parent
    where conflicting."""


def test_set_hash_functions_on_args_instance():
    """Setting the hashing functions directly on an instance of a parameter
    set should change that parameter's hash, but not of any other instance of
    those same parameters."""

    @dataclass
    class MyExperimentArgs(cf.ExperimentArgs):
        a: int = 0
        b: int = None
        c: int = 5

    args0 = MyExperimentArgs()
    args1 = MyExperimentArgs()

    args0.hash_representations["c"] = None
    assert args0.args_hash() != args1.args_hash()


# TODO: (3/9/2023) I'm still unclear on if this should actually be the intended functionality
def test_hash_stays_same_after_param_change():
    """If you hash a parameter set, and then change a parameter the hash shouldn't change."""

    @dataclass
    class MyExperimentArgs(cf.ExperimentArgs):
        a: int = 0
        b: int = None
        c: int = 5

    args = MyExperimentArgs()
    hash0 = args.args_hash()
    args.hash = hash0  # this emulates what run_experiment is doing.
    assert args.hash == hash0

    args.c = 3
    hash1 = args.args_hash()
    assert hash1 == hash0


def test_hash_changes_after_param_change_and_hash_set_to_none():
    """If you hash a parameter set, change a parameter, and set the .hash to `None`, the
    hash should recompute and then change."""

    @dataclass
    class MyExperimentArgs(cf.ExperimentArgs):
        a: int = 0
        b: int = None
        c: int = 5

    args = MyExperimentArgs()
    hash0 = args.args_hash()
    args.hash = hash0  # this emulates what run_experiment is doing.
    assert args.hash == hash0

    args.c = 3
    args.hash = None
    hash1 = args.args_hash()
    assert hash1 != hash0


def test_none_hashing_function_includes_val_in_str_rep():
    """The string hash representation of an ignored parameter should still include the value
    in a sub IGNORED_PARAMS dictionary."""

    @dataclass
    class MyExperimentArgs(cf.ExperimentArgs):
        a: int = 0
        b: int = 5

        hash_representations: dict = cf.set_hash_functions(a=None)

    args = MyExperimentArgs(a=6)
    rep = parameters_string_hash_representation(args)
    assert "a" in rep["IGNORED_PARAMS"]
    assert rep["IGNORED_PARAMS"]["a"] == "6"


def test_subdataclass_val_in_str_rep_correct():
    """The string hash rep of a dataclass with sub-dataclasses should correctly
    represent the sub dataclasses the same way."""

    @dataclass
    class NormalDC:
        c: int = 5
        d: int = 6

        hash_representations: dict = cf.set_hash_functions(d=None)

    @dataclass
    class MyExperimentArgs(cf.ExperimentArgs):
        a: int = 0
        b: int = 1
        others: NormalDC = NormalDC()

    args = MyExperimentArgs(others=NormalDC(d=7))
    rep = parameters_string_hash_representation(args)
    assert rep["others"]["c"] == "5"
    assert "d" in rep["others"]["IGNORED_PARAMS"]
    assert rep["others"]["IGNORED_PARAMS"]["d"] == "7"


def test_none_hash_subdataclass_val_in_str_rep_correct():
    """The string hash rep of a dataclass with sub-dataclasses should correctly
    represent the sub dataclasses the same way even if the sub dataclass is in the
    ignored parameters."""

    @dataclass
    class NormalDC:
        c: int = 5
        d: int = 6

        hash_representations: dict = cf.set_hash_functions(d=None)

    @dataclass
    class MyExperimentArgs(cf.ExperimentArgs):
        a: int = 0
        b: int = 1
        others: NormalDC = NormalDC()
        hash_representations: dict = cf.set_hash_functions(others=None)

    args = MyExperimentArgs(others=NormalDC(d=7))
    rep = parameters_string_hash_representation(args)
    assert "others" in rep["IGNORED_PARAMS"]
    assert "d" in rep["IGNORED_PARAMS"]["others"]["IGNORED_PARAMS"]
    assert rep["IGNORED_PARAMS"]["others"]["IGNORED_PARAMS"]["d"] == "7"
