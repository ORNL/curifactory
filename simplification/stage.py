import hashlib
import inspect
import copy
from dataclasses import dataclass
from functools import wraps
from typing import Callable, Union

# import simplification
import artifact

# import simplification.artifact


@dataclass
class Stage:
    """Essentially a fancy "partial" that assigns outputs to instance
    attributes typed as Artifacts."""

    # TODO: we probably also need to track larger context = pass in the
    # experiment to the stage

    function: callable
    args: list
    kwargs: dict

    outputs: Union[list["artifact.Artifact"], "artifact.Artifact"]
    hashing_functions: dict[str, callable] = None
    pass_self: bool = False

    def __post_init__(self):
        artifacts = []
        if not isinstance(self.outputs, list):
            # turn it into a list for now just for consistent handling, will be
            # collapsed later
            self.outputs = [self.outputs]
        for output in self.outputs:
            # TODO: throw error if output name isn't a valid python var name

            # setattr(self, name, field(default=None))
            # TODO: there should probably be an artifact copy function
            art = artifact.Artifact()
            art.name = output.name
            art.cacher = output.cacher

            art.compute = self
            setattr(self, output.name, art)
            artifacts.append(art)
        self.outputs = artifacts

        # unclear if this is the way to go to handle more tuple like returns
        # from experiment definitions when assigning stage outputs
        if len(self.outputs) == 1:
            self.outputs = self.outputs[0]

        self._assign_dependents()

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if name == "args" or name == "kwargs":
            self._assign_dependents()

    def _assign_dependents(self):
        """Go through args and kwargs and for any artifacts, add this stage
        to their dependents."""
        # TODO: we obv don't want cross experiment/context dependents, so
        # maybe we error if the input is from different context? Or maybe
        # this is where we handle automatically creating a copy instead. (No
        # actually I think that should get handled in replace in artifact?) Or
        # maybe both.
        for arg in self._combined_args():
            if isinstance(arg, artifact.Artifact) and self not in arg.dependents:
                arg.dependents.append(self)

    # def define(self, *args, **kwargs):
    #     # TODO: only necessary for modeltest2, prob not the best name
    #     self.args = args
    #     self.kwargs = kwargs

    def copy(self):
        # TODO: I don't think this will preserve collapsed artifacts.
        # new_stage = Stage(self.function, 
        copied_args = []
        for arg in self.args:
            if isinstance(arg, artifact.Artifact):
                copied_args.append(arg.copy())
            else:
                copied_args.append(copy.deepcopy(arg))
        copied_kwargs = {}
        for kw in self.kwargs:
            arg = self.kwargs[kw]
            if isinstance(arg, artifact.Artifact):
                copied_kwargs[kw] = arg.copy()
            else:
                copied_kwargs[kw] = copy.deepcopy(arg)
        
        new_stage = Stage(self.function, copied_args, copied_kwargs, self.outputs, self.hashing_functions, self.pass_self)
        return new_stage

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
        if isinstance(param_value, artifact.Artifact):
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

    def _combined_args(self) -> list:
        """Put the kwargs into a list, this is mostly just to make it easier to scan
        all inputs for artifacts."""
        if hasattr(self, "kwargs"):
            return list(self.args) + list(self.kwargs.values())
        else:
            return list(self.args)

    def _artifact_tree(self) -> dict[str, dict]:
        """Recursive all the way down."""
        tree = {}
        # TODO: if two artifacts have the same name in an artifact list, they
        # overwrite eachother in the tree dict. Will need to handle auto array
        # logic for ArtifactLists? Or make everything be a list of dicts instead
        for arg in self.args:
            if isinstance(arg, artifact.Artifact):
                tree[arg.name] = arg.compute._artifact_tree()
        for kwarg in self.kwargs:
            if isinstance(self.kwargs[kwarg], artifact.Artifact):
                tree[arg.name] = arg.compute._artifact_tree()

        if len(tree.keys()) == 0:
            return None
        return tree

    def _stage_list():
        # TODO
        pass

    def __call__(self):
        print("Executing stage for " + self.function.__name__)

        passed_args = []
        passed_kwargs = {}

        # compute any inputs
        for arg in self.args:
            print("\tType of arg", type(arg), isinstance(arg, artifact.Artifact))
            if isinstance(arg, artifact.Artifact):
                if not arg.computed:
                    print("\t\t", arg.name, " not computed! ,", type(arg), arg)
                    arg.compute()
                    print("\t\t\tOkay appending", arg.object)
                passed_args.append(arg.object)
            else:
                passed_args.append(arg)
        for kwarg in self.kwargs:
            if isinstance(self.kwargs[kwarg], artifact.Artifact):
                if not self.kwargs[kwarg].computed:
                    print("\t\tNot computed!")
                    self.kwargs[kwarg].compute()
                passed_kwargs[kwarg] = self.kwargs[kwarg].object
            else:
                passed_kwargs[kwarg] = self.kwargs[kwarg]

        if self.pass_self:
            passed_args.insert(0, self)

        function_outputs = self.function(*passed_args, **passed_kwargs)

        if type(self.outputs) is list:
            if len(self.outputs) < 1:
                return
            else:
                for index, art in enumerate(self.outputs):
                    art.computed = True
                    art.object = function_outputs[index]
                return self.outputs
        else:
            art: "artifact.Artifact" = self.outputs
            art.computed = True
            art.object = function_outputs
            return art

    def __repr__(self):
        kws = [f"{key}={value!r}" for key, value in self.__dict__.items()]
        return "{}({})".format(type(self).__name__, ", ".join(kws))


def stage(
    outputs: list["artifact.Artifact"],
    hashing_functions: dict[str, callable] = None,
    pass_self: bool = False,
):
    def decorator(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            # return Stage(function, args, kwargs, outputs, hashing_functions, pass_self)
            return Stage(
                function, list(args), kwargs, outputs, hashing_functions, pass_self
            ).outputs

        return wrapper

    return decorator
