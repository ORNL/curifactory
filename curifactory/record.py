"""Contains relevant classes for records, objects that track a particular state
through some set of stages."""

import copy
import logging
import os
import shutil

from curifactory import hashing
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
        if type(item) == Lazy and self.resolve and item.resolve:
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
        # TODO: what's the type? Are these indices? or artifact representations? Keys to the artifact representations?
        self.stage_outputs = []
        """A list of lists per stage with the state outputs that stage produced."""
        # TODO: what's the type? Are these indices? or artifact representations? Keys to the artifact representations?
        self.input_records = []
        """A list of any records used as input to this one. This mostly only occurs when aggregate
        stages are run."""
        # NOTE: these are actual record references
        self.is_aggregate = False
        """If this record runs an aggregate stage, we flip this flag to true to know we need to use the
        combo hash rather than the individual args hash."""
        self.combo_hash = None
        """This gets set on records that run an aggregate stage. This is set from utils.add_args_combo_hash."""
        self.unstored_tracked_paths: list[dict[str, str]] = []
        """Paths obtained with get_path/get_dir that should be copied to a full
        store folder. The last executed stage should manage copying anything
        listed here and then clearing it. This is a list of dicts that would be
        passed to the artifact manager's ``get_artifact_path` function: (obj_name, subdir, prefix, and path)
        """
        self.stored_paths: list[str] = []
        """A list of paths that have been copied into a full store folder. These are
        the source paths, not the destination paths."""

        self.set_hash()
        if not hide:
            self.manager.records.append(self)

    def store_tracked_paths(self):
        """Copy all of the recent relevant files generated (likely from the recently executing
        stage) into a store-full run. This is run automatically at the end of a stage.
        """
        if self.manager.store_full:
            for path_info in self.unstored_tracked_paths:
                name = path_info["obj_name"]
                subdir = path_info["subdir"]
                prefix = path_info["prefix"]
                path = path_info["path"]

                # don't duplicate if we've already stored it (this might occur from multiple get_path
                # calls on a cacher)
                if path in self.stored_paths:
                    continue

                # paths can get added to the list that don't exist from a cacher's check() call
                # (e.g. checking if reportables exist but a stage output no reportables.)
                # at least for now we silently skip these.
                if not os.path.exists(path):
                    continue

                # if the auto naming strategy isn't being used (only a filepath given, no name),
                # then use the last part of the filename (from the last '/') as the obj name
                if name is None:
                    name = os.path.basename(path)
                    # TODO: (3/22/2023) unclear if I need to set subdir and prefix to none or not

                store_path = self.manager.get_artifact_path(
                    name, record=self, subdir=subdir, prefix=prefix, store=True
                )
                logging.debug(f"Copying tracked path '{path}' to '{store_path}'...")
                if os.path.isdir(path):
                    shutil.copytree(path, store_path)
                else:
                    shutil.copy(path, store_path)

                # remember that we copied this path
                self.stored_paths.append(path)
        # I'm clearing unstored regardless of store full or not, because we may
        # eventually want to support something like --store-artifact, where we
        # selectively add specific things to the tracked paths, so we want tracked
        # paths to not build up things that are never going to be stored.
        self.unstored_tracked_paths = []

    def set_hash(self):
        """Establish the hash for the current args (and set it on the args instance)."""
        # NOTE: we used to set this directly in manager's get_path, but there's potentially weird effects and it's an
        # odd place to establish a hash that more correctly indicates a record than the args themselves (e.g. like with
        # aggregate combo hashes)
        if self.args is not None and self.args.hash is None:
            self.args.hash = hashing.args_hash(
                self.args,
                store_in_registry=not (self.manager.dry or self.manager.parallel_mode),
                registry_path=self.manager.manager_cache_path,
            )

            if self.manager.store_full:
                hashing.args_hash(
                    self.args,
                    store_in_registry=not (
                        self.manager.dry or self.manager.parallel_mode
                    ),
                    registry_path=self.manager.get_run_output_path(),
                )

    def get_hash(self) -> str:
        """Returns either the hash of the args, or the combo hash if this record is an aggregate."""
        if self.is_aggregate:
            return self.combo_hash
        elif self.args is not None:
            return self.args.hash
        else:
            return "None"

    def set_aggregate(self, aggregate_records):
        """Mark this record as starting with an aggregate stage, meaning the hash of all cached outputs produced
        within this record need to reflect the combo hash of all records going into it.
        """
        self.is_aggregate = True
        self.combo_hash = hashing.add_args_combo_hash(
            self,
            aggregate_records,
            self.manager.manager_cache_path,
            not (self.manager.dry or self.manager.parallel_mode),
        )
        if self.manager.store_full:
            hashing.add_args_combo_hash(
                self,
                aggregate_records,
                self.manager.get_run_output_path(),
                not (self.manager.dry or self.manager.parallel_mode),
            )

    def report(self, reportable: Reportable):
        """Add a reportable associated with this record, this will get added to the experiment run
        output report.

        Args:
            reportable (Reportable): The reportable to render on the final experiment report.
        """
        reportable.record = self
        reportable.stage = self.stages[-1]

        qualified_name = ""
        if reportable.record.is_aggregate:
            qualified_name = "(Aggregate)_"
        if reportable.record.args is not None:
            qualified_name += f"{reportable.record.args.name}_"
        qualified_name += f"{reportable.stage}_"

        if reportable.name is None:
            qualified_name += str(len(self.manager.reportables))
        else:
            qualified_name += reportable.name
        reportable.qualified_name = qualified_name

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
        new_record = Record(self.manager, args, hide=(not add_to_manager))
        new_record.input_records = [self]
        new_record.state = copy.deepcopy(self.state)
        # TODO: (02/02/2022) state without state artifact reps might cause issues
        # new_record.state_artifact_reps = self.state_artifact_reps
        return new_record

    # TODO: should also take an optional 'sub-path' and 'extension'
    def get_path(
        self,
        obj_name: str,
        subdir: str = None,
        prefix: str = None,
        stage_name: str = None,
        track: bool = True,
    ) -> str:
        """Return an args-appropriate cache path with passed object name.

        This should be equivalent to what a cacher for a stage should get. Note that this
        is calling the manager's get_path, which will include the stage name. If calling
        this outside of a stage, it will include whatever stage was last run.

        Args:
            obj_name (str): the name to associate with the object as the last part of the filename.
            subdir (str): An optional string of one or more nested subdirectories to prepend to the artifact filepath.
                This can be used if you want to subdivide cache and run artifacts into logical subsets, e.g. similar to
                https://towardsdatascience.com/the-importance-of-layered-thinking-in-data-engineering-a09f685edc71.
            prefix (str): An optional alternative prefix to the experiment-wide prefix (either the experiment name or
                custom-specified experiment prefix). This can be used if you want a cached object to work easier across
                multiple experiments, rather than being experiment specific. WARNING: use with caution, cross-experiment
                caching can mess with provenance.
            stage_name (str): The associated stage for a path. If not provided, the currently
                executing stage name is used.
            track (bool): whether to include returned path in a store full copy
                or not. This will only work if the returned path is not altered
                by a stage before saving something to it.
        """
        path = self.manager.get_artifact_path(
            obj_name=obj_name,
            record=self,
            subdir=subdir,
            prefix=prefix,
            stage_name=stage_name,
        )
        if track:
            # TODO: (3/22/2023) do I need to also be storing stage name? These are always supposed
            # to be handled from the current stage only anyway, so the stage name should always
            # be the last one
            self.unstored_tracked_paths.append(
                dict(obj_name=obj_name, subdir=subdir, prefix=prefix, path=path)
            )
        return path

    def get_dir(
        self,
        dir_name_suffix: str,
        subdir: str = None,
        prefix: str = None,
        stage_name: str = None,
        track: bool = True,
    ) -> str:
        """Returns an args-appropriate cache path with the passed name, (similar to get_path) and creates it as a directory.

        Args:
            dir_name_suffix (str): the name to add as a suffix to the created directory name.
            subdir (str): An optional string of one or more nested subdirectories to prepend to the artifact filepath.
                This can be used if you want to subdivide cache and run artifacts into logical subsets, e.g. similar to
                https://towardsdatascience.com/the-importance-of-layered-thinking-in-data-engineering-a09f685edc71.
            prefix (str): An optional alternative prefix to the experiment-wide prefix (either the experiment name or
                custom-specified experiment prefix). This can be used if you want a cached object to work easier across
                multiple experiments, rather than being experiment specific. WARNING: use with caution, cross-experiment
                caching can mess with provenance.
            stage_name (str): The associated stage for a path. If not provided, the currently
                executing stage name is used.
            track (bool): whether to include returned path in a store full copy
                or not. This will only work if the returned path is not altered
                by a stage before saving something to it.
        """
        dir_path = self.manager.get_artifact_path(
            obj_name=dir_name_suffix,
            record=self,
            subdir=subdir,
            prefix=prefix,
            stage_name=stage_name,
        )
        if track:
            self.unstored_tracked_paths.append(
                dict(
                    obj_name=dir_name_suffix,
                    subdir=subdir,
                    prefix=prefix,
                    path=dir_path,
                )
            )

        os.makedirs(dir_path, exist_ok=True)
        return dir_path

    def get_reference_name(self) -> str:
        """This returns a name describing the record, in the format 'Record [index on manager] (paramset name)

        This should be the same as what's shown in the stage map in the output report.
        """
        for i, record in enumerate(self.manager.records):
            if self == record:
                paramset_name = record.args.name if record.args is not None else "None"
                return f"Record {i} ({paramset_name})"
        return None


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

    def __init__(self, record, name, artifact, metadata=None):
        # TODO: (3/21/2023) possibly have "files" which would be cachers.cached_files?
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

        self.metadata = metadata

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
