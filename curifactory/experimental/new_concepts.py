# existing artifacts can either be passed in with their filter string names, or
# direct paths
# m2.test.real_thing=d1.test.real_thing
# m2.test.real_thing=file://...


import dataclasses
from dataclasses import dataclass, field
from functools import wraps


@dataclass
class Experiment:
    name: str

    def __post_init__(self):
        # default flow verison
        for f in dataclasses.fields(self):
            print(f)
            field_attribute = getattr(self, f.name)
            if isinstance(field_attribute, DefaultFlow):
                print("Found a defaultflow")
                setattr(self, f.name, field_attribute.run_flow(self))

        # underscore artifact function def version
        for f in dataclasses.fields(self):
            if f.type is Artifact and getattr(self, f.name) is None:
                if hasattr(self, f"_{f.name}"):
                    print("Found assignment function for artifact, running...")
                    setattr(self, f.name, getattr(self, f"_{f.name}")())

        # explicit flow function
        self.flow()

    def flow(self):
        pass


# TODO: is it possible to add our own type [] thing, so someone could say:
# Artifact[pytorch.Module]
class Artifact:
    def __init__(self):
        self.name = None
        self.cacher = None
        self.object = None

        self.computed: bool = False

        self.hash_str = None

        self.compute: Stage = None

    def __repr__(self):
        string = f"Artifact '{self.name}'"
        if self.computed:
            string += f": {repr(self.object)}"
        return string


@dataclass
class Stage:
    """Essentially a fancy "partial" that assigns outputs to instance
    attributes typed as Artifacts."""

    # TODO: we probably also need to track larger context = pass in the
    # experiment to the stage

    function: callable
    args: list
    kwargs: dict

    output_names: list[str]
    caching_strats: list[str]

    def __post_init__(self):
        for name in self.output_names:
            # setattr(self, name, field(default=None))
            artifact = Artifact()
            artifact.name = name
            artifact.compute = self
            setattr(self, name, artifact)

    def define(self, *args, **kwargs):
        # TODO: only necessary for modeltest2, prob not the best name
        self.args = args
        self.kwargs = kwargs

    def __call__(self):
        print("Executing stage for " + self.function.__name__)

        passed_args = []
        passed_kwargs = {}

        # compute any inputs
        for arg in self.args:
            print("\tType of arg", type(arg), isinstance(arg, Artifact))
            if isinstance(arg, Artifact):
                if not arg.computed:
                    print("\t\tNot computed!")
                    arg.compute()
                passed_args.append(arg.object)
            else:
                passed_args.append(arg)
        for kwarg in self.kwargs:
            if isinstance(self.kwargs[kwarg], Artifact):
                if not self.kwargs[kwarg].computed:
                    print("\t\tNot computed!")
                    self.kwargs[kwarg].compute()
                passed_kwargs[kwarg] = self.kwargs[kwarg].object
            else:
                passed_kwargs[kwarg] = self.kwargs[kwarg]

        outputs = self.function(*passed_args, **passed_kwargs)

        artifact_outputs = []

        if len(self.output_names) < 1:
            return
        elif len(self.output_names) == 1:
            artifact: Artifact = getattr(self, self.output_names[0])
            artifact.computed = True
            artifact.object = outputs
            return artifact
        else:
            for index, output_name in enumerate(self.output_names):
                artifact: Artifact = getattr(self, output_name)
                artifact.computed = True
                artifact.object = outputs[index]
                artifact_outputs.append(artifact)

        return artifact_outputs

    def __repr__(self):
        # # https://stackoverflow.com/questions/67327282/extend-dataclass-repr-programmatically
        kws = [f"{key}={value!r}" for key, value in self.__dict__.items()]
        return "{}({})".format(type(self).__name__, ", ".join(kws))

        #
        # fields = dataclasses.fields(self)
        # fields = [f for f in fields if f.repr]
        # repr_fn = dataclasses._repr_fn(dataclasses.fields(self), {})
        # parent_repr = repr_fn(self)
        # # super().__repr__() would not work because it gives object.__repr__
        # parts = parent_repr.split(",")  # Split the representation by commas
        # # additional_info = f", url={self.url}"  # Additional property information
        # # parts.insert(
        # #     1, additional_info
        # # )  # Insert the additional info after the 'name' field
        # return ", ".join(parts)  # Join the parts back together
        #

    # TODO: maybe it's better to make the stage decorator be a class decorator
    # instead of a function decorator? (is that a thing?)
    # @staticmethod
    # def field():
    #     return field(default_factory=lambda: self)
    #     pass


def stage(output_names: list[str], caching_strats: list[str]):
    def decorator(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            return Stage(function, args, kwargs, output_names, caching_strats)

        return wrapper

    return decorator


@stage(["thing"], [None])
def this_is_thing() -> str:
    """Can we return a single thing from a function and use it as a default
    value for a dataclass attr?"""
    return "YESSSS"


@stage(["thing1", "thing2"], ["pickle", "csv"])
def this_is_tuple(first_thing) -> tuple[str, str]:
    """What about if we return multiple things, can we assign as defaults on
    one line?"""
    return "hello", f"world {first_thing}"


@dataclass
class DataTest(Experiment):
    real_thing: Artifact = (
        this_is_thing().thing
    )  # so this _only_ works for stages that don't need other artifacts as inputs

    act_t1: Artifact
    act_t2: Artifact

    output_tuple = this_is_tuple(real_thing)
    act_t1, act_t2 = output_tuple.thing1, output_tuple.thing2


# @dataclass
# class DataTest(Experiment):
# my_thing: str = this_is_thing()
#
# thing1: str
# thing2: str
#
# thing1, thing2 = this_is_tuple()


@stage(["final_model"], ["model"])
def train_model(part1, part2, some_parameter) -> str:
    print(f"I'm using {some_parameter}...")
    return f"{part1},{part2},{some_parameter}"


@dataclass
class ModelTest1(Experiment):
    test: DataTest
    my_param: int = 6
    model: Artifact = None

    def flow(self):
        if self.model is None:
            self.model = train_model(
                # part1=self.test.real_thing,
                # part2=self.test.act_t2,
                # some_parameter=self.my_param,
                self.test.real_thing,
                self.test.act_t2,
                self.my_param,
            ).final_model


def live_test():
    """Can we define an experiment outside of a data class?"""
    # I'm guessing at the least we need a context manager (ArtifactManager!)
    # or really, instead of using ArtifactManager, we can get rid of that
    # concept too and just make an Experiment be able to be a context manager as
    # well.

    real_thing = this_is_thing().thing
    output_tuple = this_is_tuple(real_thing)
    act_t1, act_t2 = output_tuple.thing1, output_tuple.thing2
    model = train_model(real_thing, act_t2, 6)

    return model


# TODO: probably we need some sort of function that automatically finds any
# experiment type attributes and adds self as parent context, and then do the
# same thing with each artifact's associated stage (will be necessary in order
# to compute the hash for each artifact)


@dataclass
class ModelTest2(Experiment):
    test: DataTest
    my_param: int = 6
    model: Artifact = train_model().final_model

    def flow(self):
        self.model.compute.define(
            self.test.real_thing, self.test.act_t2, some_parameter=self.my_param
        )


# TODO: so the annoying part I'm struggling with is that there's not a clean way
# to make it so that there's a default flow, but that still lets you exchange
# any part of the flow (change one artifact for some other one) and have that
# automatically integrated into the rest of the flow. Maybe I need to override
# setattr to check if we write to an artifact?

# this is actually where curifactory just using magical strings pulling from a
# record state dictionary was actually fairly useful.


@dataclass
class ModelTest3(Experiment):
    test: DataTest
    my_param: int = 6

    # training: Stage = field(default_factory=lambda: train_model())

    # model: Artifact = training.final_model

    def flow(self):
        self.training.define(
            self.test.real_thing, self.test.act_t2, some_parameter=self.my_param
        )


class DefaultFlow:
    def __init__(self, flow):
        self.flow = flow

    def run_flow(self, container):
        return self.flow(container)


def default(func):
    return field(default_factory=lambda: DefaultFlow(func))


@dataclass
class ModelTest4(Experiment):
    test: DataTest
    my_param: int = 6

    model: Artifact = default(
        lambda self: train_model(
            self.test.real_thing, self.test.act_t2, self.my_param
        ).final_model
    )

    # training: Stage = field(default_factory=lambda: train_model())

    # model: Artifact = training.final_model


@dataclass
class ModelTest5(Experiment):
    test: DataTest
    my_param: int = 6

    model: Artifact = None

    def _model(self) -> Artifact:
        return train_model(
            self.test.real_thing, self.test.act_t2, self.my_param
        ).final_model


@dataclass
class DataTest2(Experiment):
    real_thing: Artifact = default(lambda self: this_is_thing().thing)

    first_creation: Stage = default(lambda self: this_is_tuple(self.real_thing))

    act_t1: Artifact = default(lambda self: self.first_creation.thing1)
    act_t2: Artifact = default(lambda self: self.first_creation.thing2)


@dataclass
class ModelTest6(Experiment):
    test: DataTest2
    my_param: int = 6

    training: Stage = default(
        lambda self: train_model(self.test.real_thing, self.test.act_t2, self.my_param)
    )

    model: Artifact = default(lambda self: self.training.final_model)


# @dataclass
# class ModelTest2(Experiment):
#     test: DataTest
#     my_param: int = 6
#     model: Artifact = field(
#         default_factory=lambda: train_model(
#             part1=test.real_thing,
#             part2=test.act_t2,
#             some_parameter=my_param,
#         ).final_model
#     )
#
#     # def flow(self):
#     #     if self.model is None:
#     #         self.model = train_model(
#     #             part1=self.test.real_thing,
#     #             part2=self.test.act_t2,
#     #             some_parameter=self.my_param,
#     #         ).model
#

# @dataclass
# class ModelTest2(Experiment):
#     test: DataTest = DataTest("test")
#
#     my_param: int = 6
#
#     model: Artifact = train_model(
#         part1=self.test.real_thing, part2=self.test.act_t2, some_parameter=my_param
#     ).model
#
#
#     def flow(self):
#         pass
