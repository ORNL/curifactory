"""Ensure the args hashing works as expected."""

from dataclasses import dataclass

import curifactory as cf


def test_args_subclass_hash_includes_all_sub_params():
    """The hash of a subclass of experiment args should include all of the subclass's
    parameters."""

    @dataclass
    class MyExperimentArgs(cf.ExperimentArgs):
        a: int = 0
        b: int = None

    args1 = MyExperimentArgs(name="test", a=6, b=7)
    dry_hash_dict = args1.args_hash(dry=True)
    assert dry_hash_dict["name"] == "repr(value) - 'test'"
    assert dry_hash_dict["a"] == "repr(value) - 6"
    assert dry_hash_dict["b"] == "repr(value) - 7"

    # make sure we correctly don't hash everything in the blacklist
    for should_skip in ["hash", "overwrite", "hashing_functions"]:
        assert dry_hash_dict[should_skip].startswith("SKIPPED: curifactory blacklist")

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

        hashing_functions: dict = cf.set_hash_functions(a=lambda self, obj: 5)

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

        hashing_functions: dict = cf.set_hash_functions(a=None)

    args1 = MyExperimentArgs()
    args2 = MyExperimentArgs(a=6)
    assert args1.args_hash() == args2.args_hash()
    assert args1.args_hash(dry=True)["a"] == "SKIPPED: set to None in hashing_functions"


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
    assert args1.args_hash(dry=True)["b"] == "SKIPPED: value is None"


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

        hashing_functions: dict = cf.set_hash_functions(d=None)

    @dataclass
    class MyExperimentArgs(cf.ExperimentArgs):
        a: int = 0
        b: int = 1
        others: NormalDC = NormalDC()

    args1 = MyExperimentArgs()
    args2 = MyExperimentArgs(others=NormalDC(d=7))
    assert args1.args_hash() == args2.args_hash()
    assert type(args1.args_hash(True)["others"]) == dict
    assert (
        args1.args_hash(True)["others"]["d"]
        == "SKIPPED: set to None in hashing_functions"
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

        hashing_functions: dict = cf.set_hash_functions(a=None, b=None)

    args = MyExperimentArgs()
    assert "a" in args.hashing_functions
    assert "b" in args.hashing_functions


def test_set_hash_functions_with_dict_arg():
    """calling set_hash_functions with a single dictionary should directly set
    the hashing_functions."""

    @dataclass
    class MyExperimentArgs(cf.ExperimentArgs):
        a: int = 0
        b: int = None

        hashing_functions: dict = cf.set_hash_functions({"a": None, "b": None})

    args = MyExperimentArgs()
    assert "a" in args.hashing_functions
    assert "b" in args.hashing_functions


def test_set_hash_functions_with_dict_and_kwargs():
    """calling set_hash_functions with both a dictionary and kwargs should create
    a merged dictionary."""

    @dataclass
    class MyExperimentArgs(cf.ExperimentArgs):
        a: int = 0
        b: int = None
        c: int = 5

        hashing_functions: dict = cf.set_hash_functions(
            {"a": None, "b": None}, b="something else", c=None
        )

    args = MyExperimentArgs()
    assert "a" in args.hashing_functions
    assert "b" in args.hashing_functions
    assert "c" in args.hashing_functions

    # kwargs should override what was in possitional arg
    assert args.hashing_functions["b"] is not None

    """Subclassing an args class with hashing functions set and including additional
    hashing functions in the subclass should add/use the hashing functions of both."""

    """Subclassing an args class with hashing functions set and including hashing
    functions in the subclass for the same parameter name should 'override' parent
    where conflicting."""
