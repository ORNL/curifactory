"""Contains relevant classes for records, objects that track a particular state
through some set of stages."""

import copy
import logging
import os

from curifactory.caching import Lazy
from curifactory.reporting import Reportable


class CacheAwareDict(dict):
    """A normal dictionary that will return resolved versions of Lazy objects when accessed."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.resolve = True
        """A flag for enabling/disabling auto-resolve. If this is False, this works just
        like a normal dictionary. This is necessary in the input checking part of a normal stage, as
        we make state access before determining if stage execution is required or not."""

    def __getitem__(self, key):
        item = super().__getitem__(key)
        if type(item) == Lazy and self.resolve:
            logging.debug("Auto-resolving lazy object '%s'..." % key)
            return item.cacher.load()
        else:
            return item


# TODO: make printing this dump the state out as a string
# TODO: handle if args is None
class Record:
    """A single persistent state that's passed between stages in a single "experiment line".

    Args:
        manager (ArtifactManager): The artifact manager this record is associated with.
        args: The :code:`ExperimentArgs` instance to apply to any stages this record is run through.
        hide (bool): If :code:`True`, don't add this record to the artifact manager.
    """

    def __init__(self, manager, args, hide=False):
        # TODO: would be nice to be able to initialize a record with a pre-defined state dictionary
        self.manager = manager
        """The :code:`ArtifactManager` associated with this record."""
        self.args = args
        """The :code:`ExperimentArgs` to apply to any stages this record is passed through."""
        # self.state = {}
        self.state = CacheAwareDict()
        """The dictionary of all variables created by stages this record is passed through. (AKA 'Artifacts')
        All :code:`inputs` from stage decorators are pulled from this dictionary, and all
        :code:`outputs` are stored here."""
        self.state_artifact_reps = {}
        """Dictionary mimicking state that keeps an :code:`ArtifactRepresentation` associated with
        each variable stored in :code:`self.state`."""
        self.output = None
        """The returned value from the last stage that was run with this record."""
        self.stages = []
        """The list of stage names that this record has run through so far."""
        self.stage_inputs = []
        """A list of lists per stage with the state inputs that stage requested."""
        self.stage_outputs = []
        """A list of lists per stage with the state outputs that stage produced."""
        self.input_records = []
        """A list of any records used as input to this one. This mostly only occurs when aggregate
        stages are run."""

        if not hide:
            self.manager.records.append(self)

    def report(self, reportable: Reportable):
        """Add a reportable associated with this record, this will get added to the experiment run
        output report.

        Args:
            reportable (Reportable): The reportable to render on the final experiment report.
        """
        reportable.record = self
        reportable.stage = self.stages[-1]

        if reportable.record.args is not None:
            name = f"{reportable.record.args.name}_{reportable.stage}_"
        else:
            name = f"(Aggregate)_{reportable.stage}_"
        if reportable.name is None:
            name += str(len(self.manager.reportables))
        else:
            name += reportable.name
        reportable.name = name

        self.manager.reportables.append(reportable)

    def make_copy(self, args=None, add_to_manager=True):
        """Make a new record that has a deep-copied version of the current state.

        This is useful for a long running procedure that creates a common dataset for
        many other stages, so that it can be replicated across multiple argsets without
        having to recompute for each argset.

        Note that state is really the only thing transferred to the new record, the stage and
        inputs/outputs lists will be empty.

        Also note that the current record will be added to the :code:`input_records` of the new
        record, since it may draw on data in its state.

        Args:
            args: The new :code:`ExperimentArgs` argset to apply to the new record. Leave as None
                to retain the same args as the current record.
            add_to_manager: Whether to automatically add this record to the current manager or not.
        """
        if args is None:
            args = self.args
        new_record = Record(self.manager, args)
        new_record.input_records = [self]
        new_record.state = copy.deepcopy(self.state)
        # TODO: (02/02/2022) state without state artifact reps might cause issues
        # new_record.state_artifact_reps = self.state_artifact_reps

        if add_to_manager:
            self.manager.records.append(new_record)

        return new_record

    def get_path(self, obj_name: str) -> str:
        """Return an args-appropriate cache path with passed object name.

        This should be equivalent to what a cacher for a stage should get. Note that this
        is calling the manager's get_path, which will include the stage name. If calling
        this outside of a stage, it will include whatever stage was last run.

        Warning:
            This path does not yet have a mechanism to be auto-stored in the output folder for --store-full runs. This functionality will be implemented later.

        Args:
            obj_name (str): the name to associate with the object as the last part of the filename.
        """
        # TODO: (02/02/2022) at some point this should keep track of these paths so that store-full can automatically grab them too.
        return self.manager.get_path(obj_name=obj_name, record=self)

    def get_dir(self, dir_name_suffix: str) -> str:
        """Returns an args-appropriate cache path with the passed name, (similar to get_path) and creates it as a directory.

        Warning:
            This path does not yet have a mechanism to be auto-stored in the output folder for --store-full runs. This functionality will be implemented later.

        Args:
            dir_name_suffix (str): the name to add as a suffix to the created directory name.
        """

        # TODO: (02/02/2022) at some point this should keep track of these paths so that store-full can automatically grab them too.
        dir_path = self.manager.get_path(obj_name=dir_name_suffix, record=self)

        os.makedirs(dir_path, exist_ok=True)
        return dir_path


class ArtifactRepresentation:
    """This is a shorthand string representation for an artifact stored in a record as well
    as output cache info. This is what gets displayed in the detailed experiment map in reports.

    This will try to include helpful information in the string representation, such as pandas/
    numpy shapes, or lengths where applicable.

    Args:
        record (Record): The record this artifact is stored in.
        name (str): The name of the artifact.
        artifact: The artifact itself.
    """

    def __init__(self, record, name, artifact):
        self.init_record = record
        self.name = name
        self.string = f"({type(artifact).__name__}) {str(artifact)[:20]}"
        if len(str(artifact)) > 20:
            self.string += "..."
        if hasattr(artifact, "shape"):
            shape = None
            if callable(getattr(artifact, "shape", None)):
                shape = artifact.shape()
            else:
                shape = artifact.shape
            self.string += f" shape: {shape}"
        elif hasattr(artifact, "__len__"):
            self.string += f" len: {len(artifact)}"

        self.file = "no file"

    def html_safe(self):
        """Removes special characters that'd break html, except it doesn't actually display
        correctly.

        (I think this is an issue with how graphviz renders outputs?)"""
        clean = (
            self.string.replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("&", "&amp;")
            .replace('"', "&quot;")
        )

        return clean
