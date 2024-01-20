# from simplification.experiment import Experiment
# from simplification.stage import Stage

import experiment
import stage


class ArtifactManager:
    def __init__(self):
        self.artifacts: dict[str, Artifact] = {}
        pass

    def __getitem__(self, item):
        return self.artifacts[item]

    def display(self):
        for key, value in self.artifacts.items():
            print(
                key.ljust(20), ":", repr(value).ljust(50), ":", str(id(value)).ljust(30)
            )


Artifacts = ArtifactManager()  # TODO: set up as part of global config?
# config should be accessible via cf.config? And that gets set from commandline,
# but both library and cli have a default
# TODO: IDEA: IDEA: perhaps a better way of creating the artifacts map is to rely on an
# explicit map() function on experiment that iterates backwards through each
# final artifact's compute chain and adds the appropriate table reference (then
# we don't have to worry about the artifact having filter_name) and we have a
# (possibly) less dodgy settattr on experiment.
# Experiment names could still be implicitly tracked on instantiation, which
# would then potentially allow more direct control over how/what gets mapped.


# TODO: is it possible to add our own type [] thing, so someone could say:
# Artifact[pytorch.Module]
class Artifact:
    def __init__(self, name=None, cacher=None):
        self.name = name
        self.cacher = cacher
        self.object = None

        self.computed: bool = False

        self.hash_str = None
        self.hash_debug = None

        self.compute: stage.Stage = None

        # care needs to be taken when _using_ context, because the same artifact
        # can obviously be used from multiple experiments, meaning this always
        # probably reflects the _last_ experiment that was assigned this
        # artifact. So far context is only being used to compute a filter name,
        # which as a function shouldn't be used directly by the user anyway.
        self.context: experiment.Experiment = None
        self.context_name: str = None

    def compute_hash(self):
        if self.compute is None:
            return ""
        self.hash_str, self.hash_debug = self.compute.compute_hash()
        return self.hash_str, self.hash_debug

    def __setattr__(self, name: str, value):
        # pass a reference for this artifact to the cacher so it can access info
        # like the artifact name etc.
        if name == "cacher" and value is not None:
            value.artifact = self
        super().__setattr__(name, value)

    def __repr__(self):
        # TODO: think through better set of things to show
        string = f"Artifact '{self.name}'"
        if self.computed:
            string += f": {repr(self.object)}"
        return string

    def replace(self, artifact):
        self.pointer = artifact

    # TODO: make this _ function to indicate shouldn't be called outside of cf
    # code
    def filter_name(self) -> str:
        if self.context is not None:
            this_name = self.name if self.context_name is None else self.context_name
            return f"{self.context.filter_name()}.{this_name}"
        return self.name

    @staticmethod
    def from_metadata(metadata=None, path=None):
        # TODO
        pass
