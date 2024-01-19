import hashlib
import inspect
from dataclasses import dataclass
from functools import wraps
from typing import Callable

from artifact import Artifact


@dataclass
class Stage:
    """Essentially a fancy "partial" that assigns outputs to instance
    attributes typed as Artifacts."""

    # TODO: we probably also need to track larger context = pass in the
    # experiment to the stage

    function: callable
    args: list
    kwargs: dict

    outputs: list[Artifact]
    hashing_functions: dict[str, callable] = None
    pass_self: bool = False

    def __post_init__(self):
        artifacts = []
        for output in self.outputs:
            # TODO: throw error if output name isn't a valid python var name

            # setattr(self, name, field(default=None))
            # TODO: there should probably be an artifact copy function
            artifact = Artifact()
            artifact.name = output.name
            artifact.cacher = output.cacher

            artifact.compute = self
            setattr(self, output.name, artifact)
            artifacts.append(artifact)
        self.outputs = artifacts

    def define(self, *args, **kwargs):
        # TODO: only necessary for modeltest2, prob not the best name
        self.args = args
        self.kwargs = kwargs

    def compute_hash(self) -> tuple[str, dict[str, str]]:
        parameter_names = list(inspect.signature(self.function).parameters.keys())

        # iterate through each parameter and get its hash value
        debug = {}
        hash_values = {}
        for param_index, param_name in enumerate(parameter_names):
            if self.pass_self and param_index == 0:
                continue
            if self.pass_self:
                param_index -= 1

            hash_debug, hash_value = self.hash_parameter(
                param_name, self.get_parameter_value(param_index, param_name)
            )
            debug[param_name] = (hash_debug, hash_value)
            hash_values[param_name] = hash_value

        hash_total = 0
        for key, value in hash_values.items():
            if value is None:
                continue

            hash_hex = hashlib.md5(f"{key}{value}".encode()).hexdigest()
            hash_total += int(hash_hex, 16)
        return f"{hash_total:x}", debug

    def get_parameter_value(self, param_index, param_name):
        if param_index < len(self.args):
            return self.args[param_index]
        if param_name in self.kwargs:
            return self.kwargs[param_name]
        # otherwise get the default
        return inspect.signature(self.function).parameters[param_name].default

    def hash_parameter(self, param_name, param_value) -> tuple[str, any]:
        # 1. see if user has specified how to handle the hash representation
        if self.hashing_functions is not None and param_name in self.hashing_functions:
            # if they set it to None, ignore it
            if self.hashing_functions[param_name] is None:
                return ("SKIPPED: set to None in hash_functions", None)
            # otherwise, call the user provided function
            return (
                f"hashing_functions['{param_name}'](param_value)",
                self.hashing_functions[param_name](param_value),
            )

        # 2. if the value itself is None, nothing to hash, so don't include it.
        if param_value is None:
            return ("SKIPPED: value is None", None)

        # 3. if the parameter is an artifact, use its hash
        if isinstance(param_value, Artifact):
            # TODO: artifact needs to track the hash_debug and re-include it here.
            param_value.compute_hash()
            return (
                f"artifact {param_value.name}.hash - '{param_value.hash_debug}'",
                param_value.hash_str,
            )

        # 4. use the function name if it's a callable, rather than a pointer address
        if isinstance(param_value, Callable):
            return (f"{param_name}.__qualname__", param_value.__qualname__)

        # 5. otherwise just use the default representation
        return (f"repr({param_name})", repr(param_value))

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

        if self.pass_self:
            passed_args.insert(0, self)

        function_outputs = self.function(*passed_args, **passed_kwargs)

        if len(self.outputs) < 1:
            return
        elif len(self.outputs) == 1:
            artifact: Artifact = self.outputs[0]
            artifact.computed = True
            artifact.object = function_outputs
            return artifact
        else:
            for index, artifact in enumerate(self.outputs):
                artifact.computed = True
                artifact.object = function_outputs[index]
            return self.outputs

    def __repr__(self):
        kws = [f"{key}={value!r}" for key, value in self.__dict__.items()]
        return "{}({})".format(type(self).__name__, ", ".join(kws))


def stage(
    outputs: list[Artifact],
    hashing_functions: dict[str, callable] = None,
    pass_self: bool = False,
):
    def decorator(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            return Stage(function, args, kwargs, outputs, hashing_functions, pass_self)

        return wrapper

    return decorator
