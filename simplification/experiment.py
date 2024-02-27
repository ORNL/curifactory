import copy
import dataclasses
import inspect
from dataclasses import dataclass, field, make_dataclass
from typing import Any

import artifact


@dataclass
class Experiment:
    name: str

    # NOTE: keep in mind context/context_mine are always changing based on
    # whatever called it last, this needs to be recomputed whenever needed?
    context: "Experiment" = field(default=None, init=False, repr=False)
    context_name: str = field(default=None, init=False, repr=False)

    outputs: "artifact.ArtifactList" = field(
        default_factory=lambda: artifact.ArtifactList("outputs", []),
        init=False,
        repr=False,
    )

    def __post_init__(self):
        definition_outputs = self.define()
        if not isinstance(definition_outputs, artifact.ArtifactList):
            definition_outputs = artifact.ArtifactList("outputs", definition_outputs)
        self.outputs = definition_outputs
        self.map()

    def define(self) -> list["artifact.Artifact"]:
        pass

    # TODO: require new name to be passed?
    def modify(self, **modifications):
        return dataclasses.replace(self, **modifications)

    def map(self):
        """Assumes define() has already run."""
        outputs = self.outputs
        outputs.context = self
        outputs.context_name = "outputs"
        artifact.Artifacts.artifacts[outputs.filter_name()] = outputs
        # for art in self.outputs:
        #     # TODO: unclear if the context/context_name is the right approach
        #     art.context = self
        #     art.context_name = name

    def run(self):
        if isinstance(self.outputs, list):
            returns = []
            for art in self.outputs:
                # TODO: obviously will need to change once artifact has get()
                returns.append(art.compute())
        else:
            returns = self.outputs.compute()
        return returns

    def __setattr__(self, name: str, value):
        # TODO: this has a lot of potential flaws,
        # 1. I don't think we actually need a filter_name here, we should (in
        # theory?) be able to get the full attribute access list maybe? I guess
        # we can't get _this_ experiment's parents, so I suppose this works as
        # long as we understand that context should really only be used for this
        # exact thing, it's not a stable concept? (alternatively, it can be made
        # more concrete during an actual experiment run())
        # 2. This won't handle lists of artifacts I don't think?
        # IDEA: this should probably be handled by a map() call instead that
        # searches for any sub objects of type Artifact/Experiment
        if isinstance(value, artifact.Artifact):
            print(f"Setting context name of {value.name} to {name}")
            value.context = self
            value.context_name = name
            artifact.Artifacts.artifacts[value.filter_name()] = value
        if isinstance(value, Experiment) and name != "context":
            print(f"Setting context name of {value.name} to {name}")
            value.context = self
            value.context_name = name
            # oooh I don't like this, better way?
            for item in dir(value):
                value_attr = getattr(value, item)
                if isinstance(value_attr, artifact.Artifact):
                    print(f"Setting sub-experiment context name for {item}")
                    artifact.Artifacts.artifacts[value_attr.filter_name()] = value_attr

        super().__setattr__(name, value)

    def filter_name(self) -> str:
        if self.context is not None:
            this_name = self.name if self.context_name is None else self.context_name
            return f"{self.context.filter_name()}.{this_name}"
        return self.name


def experiment(function):
    # make the fields based on the function signature
    field_tuples = []
    parameters = inspect.signature(function).parameters
    for key in parameters.keys():
        annotation = parameters[key].annotation
        default = parameters[key].default
        if annotation == inspect._empty and default == inspect._empty:
            # a plain parameter `my_function(some_param)`
            field_tuples.append(key)
        elif annotation == inspect._empty:
            # a parameter with a default but no type
            # `my_function(some_param='yeah')`
            field_tuples.append(
                (
                    key,
                    Any,
                    field(
                        default_factory=lambda: copy.deepcopy(default),
                        init=True,
                        repr=True,
                    ),
                )
            )
        elif default == inspect._empty:
            # a parameter with a type but no default
            # `my_function(some_param: int)`
            field_tuples.append((key, annotation))
        else:
            # a parameter with type and default
            # `my_function(some_param: int=5)`
            field_tuples.append(
                (
                    key,
                    annotation,
                    field(
                        default_factory=lambda: copy.deepcopy(default),
                        init=True,
                        repr=True,
                    ),
                )
            )

    def define(self):
        # populate the actual function params call with the self.param versions
        kwargs = {
            param_name: getattr(self, param_name)
            for param_name in list(parameters.keys())
        }

        # call the function that this experiment is wrapping (defines the
        # artifacts flow)
        outputs = function(**kwargs)

        # search the outputs for any dictionaries, which we'll use to assign
        # artifact attributes to the dataclass
        experiment_outputs = []
        for output in outputs:
            if isinstance(output, dict):
                for key, value in output.items():
                    setattr(self, key, value)
            else:
                experiment_outputs.append(output)

        # flatten if single object
        if len(experiment_outputs) == 1:
            experiment_outputs = experiment_outputs[0]
        return experiment_outputs

    experiment_dataclass = make_dataclass(
        function.__name__,
        field_tuples,
        bases=(Experiment,),
        namespace={"define": define, "function": function},
    )

    def wrapper(*args, **kwargs):
        return experiment_dataclass(*args, **kwargs)

    return wrapper
