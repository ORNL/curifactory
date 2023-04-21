"""Classes for various caching strategies, known as "cachers"

This is handled through a base :code:`Cacheable` class, and each "strategy"
cacher class extends it.

Note that there are effectively two ways to use cacheables -
# TODO finish this
"""

import copy
import json
import logging
import os
import pickle
from datetime import datetime
from typing import Union

import pandas as pd

from curifactory import hashing, utils


class Lazy:
    """A class to indicate a stage output as a lazy-cache object - curifactory will
    attempt to keep this out of memory as much as possible, immediately caching and deleting,
    and loading back into memeory only when needed.

    This object is used by "wrapping" a stage output string with the class.

    Example:
        .. code-block:: python

            @stage(inputs=None, outputs=["small_output", cf.Lazy("large_output")], cachers=[PickleCacher]*2)
            def some_stage(record: Record):
                ...

    Args:
        name (str): the name of the output to put into state.
        resolve (bool): Whether this lazy object should automatically reload the initial
            object when accessed from state. By default this is ``True`` - when a stage specifies
            the string name as an input and this object is requested from the record state, it
            loads and passes in the originally stored object. If set to ``False``, the stage
            input will instead be populated with the lazy object itself, giving the inner stage
            code direct access to the cacher. This is useful if you need to keep objects out of
            memory and just want to refer to the cacher path (e.g. to send this path along
            to an external CLI/script.)
    """

    def __init__(self, name: str, resolve: bool = True):
        self.name = name
        self.cacher: Cacheable = None
        self.resolve = resolve

    def load(self):
        return self.cacher.load()

    def __str__(self):
        return self.name


class Cacheable:
    """The base caching class, any caching strategy should extend this.

    Args:
        path_override (str): Use a specific path for the cacheable, rather than
            automatically setting it based on name etc.
        name (str): The obj name to use in automatically constructing a path. If
            a cacheable is used in stage header, this is automatically provided as
            the output string name from the stage outputs list.
        subdir (str): An optional string of one or more nested subdirectories to
            prepend to the artifact filepath.  This can be used if you want to
            subdivide cache and run artifacts into logical subsets, e.g. similar to
            https://towardsdatascience.com/the-importance-of-layered-thinking-in-data-engineering-a09f685edc71.
        prefix (str): An optional alternative prefix to the experiment-wide
            prefix (either the experiment name or custom-specified experiment
            prefix). This can be used if you want a cached object to work easier
            across multiple experiments, rather than being experiment specific.
            WARNING: use with caution, cross-experiment caching can mess with
            provenance.
        extension (str): The filetype extension to add at the end of the path.
        record (Record): The current record this cacheable is caching under.
            This can be used to get a copy of the current args instance and is also
            how artifact metadata is collected.
        track (bool): whether to include returned path in a store full copy or not.

    Note:
        It is strongly recommended that any subclasses of Cacheable take ``**kwargs`` in init and pass
        along to ``super()``:

        .. code-block:: python

            class CustomCacher(cf.Cacheable):
                def __init__(self, path_override: str = None, custom_attribute: Any = None, **kwargs):
                    super().__init__(path_override, **kwargs)
                    self.some_custom_attribute = custom_attribute

        This allows consistent handling of paths in the parent ``get_path()`` and ``check()`` functions.

        If no custom attributes are needed, also pass in *args, so path_override can be specified without
        a kwarg:

            .. code-block:: python

                class CustomCacher(cf.Cacheable):
                    def __init__(self, *args, **kwargs):
                        super().__init__(*args, extension=".custom", **kwargs)

    """

    def __init__(
        self,
        path_override: str = None,
        name: str = None,
        subdir: str = None,
        prefix: str = None,
        extension: str = None,
        record=None,
        track: bool = True,
    ):
        self.path_override = path_override
        """Use a specific path for the cacheable, rather than automatically setting it based on name etc."""
        self.name = name
        """The obj name to use in automatically constructing a path. If a cacheable is used in stage header, this is automatically
        provided as the output string name from the stage outputs list."""
        self.subdir = subdir
        """An optional string of one or more nested subdirectories to prepend to the artifact filepath.
        This can be used if you want to subdivide cache and run artifacts into logical subsets, e.g. similar to
        https://towardsdatascience.com/the-importance-of-layered-thinking-in-data-engineering-a09f685edc71.  """
        self.prefix = prefix
        """An optional alternative prefix to the experiment-wide prefix (either the experiment name or
        custom-specified experiment prefix). This can be used if you want a cached object to work easier across
        multiple experiments, rather than being experiment specific. WARNING: use with caution, cross-experiment
        caching can mess with provenance.  """
        self.extension = extension
        """The filetype extension to add at the end of the path. (Optional, automatically used as suffix in get_path if provided)"""
        self.record = None
        """The current record this cacheable is caching under. This can be used to get a copy of the current args instance and is also
        how artifact metadata is collected."""
        self.track = track
        """Whether to store the artifact this cacher is used with in the run folder on store-full runs or not."""
        self.cache_paths: list[str] = []
        """The running list of paths this cacher is using, as appended by ``get_path``."""
        self.metadata: dict = None
        """Metadata about the artifact cached with this cacheable."""
        self.extra_metadata: dict = {}
        """``collect_metadata`` uses but does not overwrite this, placing into the `extra` key
        in the actual metadata. This can be used by the cacher's save function to store additional
        information that would then be available if the 'load' function calls ``load_metadata()``."""
        self.stage: str = None
        """The stage associated with this cacher, if applicable."""

        if record is not None:
            self.set_record(record)

    def _resolve_suffix(
        self, path: str, suffix: str, add_extension: bool = True
    ) -> str:
        """Handles determining the final suffix of a path based on the extension of
        this cacheable and whether a specific suffix was requested or not."""

        # this is the logic to add an extension if no suffix supplied and the
        # object name/override path doesn't already contain the extension
        if suffix is None and (
            self.extension is not None
            and self.extension != ""
            and not path.endswith(self.extension)
            and add_extension
        ):
            suffix = self.extension
        elif suffix is None:
            suffix = ""

        return suffix

    def get_path(self, suffix=None) -> str:
        """Retrieve the full filepath to use for saving and loading. This should be called in the ``save()`` and
        ``load()`` implementations.

        Args:
            suffix (str): The suffix to append to the path. If not set, this will default to the cachable's extension.

        Note:
            If ``path_override`` is set on this cacher, this cacher _does not handle storing in the full store
            directory._ The assumption is that either you're referring to a static external path (which doesn't make
            sense to copy), or you're manually passing in a ``record.get_path`` in which case the record has already
            dealt with any logic necessary to add the path to the record's ``unstored_tracked paths`` which get copied
            over. Note also that this can be problematic for cachers that store multiple files since anything that isn't
            the path_override won't get copied. **For multiple file cachers you should use ``name``/``subdir``/``prefix``
            instead of setting a ``path_override``.**
        """
        path = None
        if self.path_override is not None:
            path = self.path_override

            # if the path_override has the extension in it already, remove it to handle
            # suffix addition consistently with non-path_override case
            # (the extension will be re-added in as necessary)
            # NOTE: we only do this if suffix is specified, otherwise we assume
            # path override is exactly what's desired. This is important because if
            # someone calls record.get_path and passes it in here, that get_path won't
            # auto handle an extension, and we need this get_path to return the same
            # thing as expected from record.get_path for tracking to work.
            if (
                self.extension != ""
                and path.endswith(self.extension)
                and suffix is not None
            ):
                path = path[: path.rindex(self.extension)]

            suffix = self._resolve_suffix(path, suffix, False)
            path = path + suffix
        else:
            if self.record is None:
                raise RuntimeError(
                    "Trying to call get_path on a cacher with no record and no path_override. Either pass a path directly into this cacher, or set cacher.record = some_record"
                )
            if self.name is None:
                raise RuntimeError(
                    "Trying to call get_path on a cacher with no object name and no path_overide. Either pass a path directly into this cacher, or set cacher.name = 'objectname'"
                )

            suffix = self._resolve_suffix(self.name, suffix)
            obj_name = self.name + suffix
            path = self.record.get_path(
                obj_name,
                subdir=self.subdir,
                prefix=self.prefix,
                stage_name=self.stage,
                track=self.track,
            )
        if path not in self.cache_paths:
            self.cache_paths.append(path)
        return path

    def get_dir(self, suffix=None) -> str:
        """Returns a path for a directory with the given suffix (if provided), appropriate for use in a ``save``
        and ``load`` function. This will create any subdirectories in the path if they don't exist.
        """
        path = None
        if suffix is None:
            suffix = ""

        if self.path_override is not None:
            path = self.path_override + suffix
        else:
            path = self.record.get_dir(
                self.name + suffix,
                subdir=self.subdir,
                prefix=self.prefix,
                stage_name=self.stage,
                track=self.track,
            )
        os.makedirs(path, exist_ok=True)
        return path

    def set_record(self, record):
        self.record = record
        self.collect_metadata()

    def collect_metadata(self):
        if self.record is None:
            raise RuntimeError(
                "Cannot collect metadata from a cacher with no associated record. Assign cacher.record if metadata is needed."
            )

        if self.record.manager.run_info is not None:
            manager_run_info = copy.copy(self.record.manager.run_info)
        else:
            logging.warning(
                "Manager does not currently have run info, artifact metadata will not contain specific experiment run data."
            )
            manager_run_info = {}
        if "status" in manager_run_info:
            del manager_run_info[
                "status"
            ]  # it's always going to be incomplete at this point

        # input_records are record references, need to resolve similarly to maps in report
        input_record_names = [
            record.get_reference_name() for record in self.record.input_records
        ]

        self.metadata = dict(
            artifact_generated=datetime.now().strftime(utils.TIMESTAMP_FORMAT),
            params_hash=self.record.get_hash(),
            params_name=self.record.args.name if self.record.args is not None else None,
            record_name=self.record.get_reference_name(),
            stage=self.record.manager.current_stage_name,
            artifact_name=self.name,
            cacher_type=str(type(self)),
            record_prior_stages=self.record.stages[:-1],
            prior_records=input_record_names,
            params=hashing.parameters_string_hash_representation(self.record.args)
            if self.record.args is not None
            else None,
            extra=self.extra_metadata,  # cachers can store any additional info here they want.
            manager_run_info=manager_run_info,
        )

    def save_metadata(self):
        metadata_path = self.get_path("_metadata.json")
        with open(metadata_path, "w") as outfile:
            json.dump(self.metadata, outfile, indent=2, default=str)

    def load_metadata(self) -> dict:
        metadata_path = self.get_path("_metadata.json")
        if os.path.exists(metadata_path):
            with open(metadata_path) as infile:
                self.metadata = json.load(infile)
        return self.metadata

    def check(self) -> bool:
        """Check to see if this cacheable needs to be written or not.

        Note:
            This function will always return False if the args are :code:`None`.

        Returns:
            True if we find the cached file and the current :code:`Args`
            don't specify to overwrite, otherwise False.
        """
        logging.debug("Searching for cached file at '%s'...", self.get_path())
        if os.path.exists(self.get_path()):
            if (
                self.record is not None
                and self.record.args is None
                and self.record.is_aggregate
                and len(self.record.input_records) > 0
            ):
                logging.debug(
                    "Aggregate stage has no args, checking input records to determine overwrite"
                )

                # TODO: (05/16/2022) in principle we could have a function to do an
                # overwrite check on the record itself, that way it could be "recursive"
                # if we reach back through previous records that are aggregate as well

                # if it's an aggregate stage with no provided args, we check
                # to see if any of the associated records are set to overwrite
                for record in self.record.input_records:
                    if record.args is not None and record.args.overwrite:
                        logging.debug("Record with overwrite found")
                        return False
                # we made it through each record and they weren't overwrite, we're good
                logging.debug("No records had overwrite, will use cache")
                logging.info("Cached object '%s' found", self.get_path())
                return True
            elif (
                self.record is not None
                and self.record.args is not None
                and not self.record.args.overwrite
            ):
                logging.info("Cached object '%s' found", self.get_path())
                return True
            elif self.record is None:
                # if we don't have a record (e.g. running check on a manual cacher with a
                # path override specified), don't worry about overwrite logic.
                logging.info("Cached object '%s' found", self.get_path())
                return True
            else:
                logging.debug("Object found, but overwrite specified in args")
                return False
        logging.debug("Cached file not found")
        return False

    def load(self):
        """Load the cacheable from disk.

        Note:
            Any subclass is **required** to implement this.
        """
        raise NotImplementedError(
            "Cacheable class does not have a load function implemented"
        )

    def save(self, obj):
        """Save the passed object to disk.

        Note:
            Any subclass is **required** to implement this.
        """


class JsonCacher(Cacheable):
    """Dumps an object to indented JSON."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, extension=".json", **kwargs)

    def load(self):
        with open(self.get_path()) as infile:
            obj = json.load(infile)
        return obj

    def save(self, obj) -> str:
        path = self.get_path()
        with open(path, "w") as outfile:
            json.dump(obj, outfile, indent=4, default=lambda x: str(x))
        return path


class PickleCacher(Cacheable):
    """Dumps an object to a pickle file."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, extension=".pkl", **kwargs)

    def load(self):
        with open(self.get_path(), "rb") as infile:
            obj = pickle.load(infile)
        return obj

    def save(self, obj) -> str:
        path = self.get_path()
        with open(path, "wb") as outfile:
            pickle.dump(obj, outfile)
        return path


class PandasJsonCacher(Cacheable):
    """Saves a pandas dataframe to JSON.

    Warning:

        Using this cacher is inadvisable for floating point data, as precision
        will be lost, creating the potential for different results when using
        cached values with this cacher as opposed to the first non-cached run.

    Args:
        to_json_args (Dict): Dictionary of arguments to use in the pandas
            :code:`to_json()` call.
        read_json_args (Dict): Dictionary of arguments to use in the pandas
            :code:`read_json()` call.
    """

    def __init__(
        self,
        path_override: str = None,
        to_json_args: dict = dict(double_precision=15),
        read_json_args: dict = dict(),
        **kwargs
    ):
        self.read_json_args = read_json_args
        self.to_json_args = to_json_args
        super().__init__(path_override=path_override, extension=".json", **kwargs)

    def load(self):
        return pd.read_json(self.get_path(), **self.read_csv_args)

    def save(self, obj) -> str:
        path = self.get_path()
        obj.to_json(path, **self.to_json_args)
        return path


class PandasCsvCacher(Cacheable):
    """Saves a pandas dataframe to CSV.

    Args:
        to_csv_args (Dict): Dictionary of arguments to use in the pandas
            :code:`to_csv()` call.
        read_csv_args (Dict): Dictionary of arguments to use in the pandas
            :code:`read_csv()` call.
    """

    def __init__(
        self,
        path_override: str = None,
        to_csv_args: dict = dict(),
        read_csv_args: dict = dict(index_col=0),
        **kwargs
    ):
        self.read_csv_args = read_csv_args
        self.to_csv_args = to_csv_args
        super().__init__(path_override=path_override, extension=".csv", **kwargs)

    def load(self):
        return pd.read_csv(self.get_path(), **self.read_csv_args)

    def save(self, obj) -> str:
        path = self.get_path()
        obj.to_csv(path, **self.to_csv_args)
        return path


class FileReferenceCacher(Cacheable):
    """Saves a file path or list of file paths generated from a stage as a json file.
    The :code:`check` function will check existence of all file paths.

    This is useful for instances where there may be a large number of files stored or
    generated to disk, as it would be unwieldy to return them all (or infeasible to keep them
    in memory) directly from the stage. When this cacher is checked for pre-existing,
    it tries to load the json file storing the filenames, and then checks for the existence of
    each path in that json file. If all of them exist, it will short-circuit computation.

    Using this cacher does mean the user is in charge of loading/saving the file paths correctly,
    but in some cases that may be desirable.

    This can also be used for storing a reference to a single file outside the normal cache.

    When combined with the :code:`get_dir` call on the record, you can create a cached directory of
    files similarly to a regular cacher and simply keep a reference to them as part of the actual
    cacher process.

    Example:

        .. code-block:: python

            @stage(inputs=None, outputs=["many_text_files"], cachers=[FileReferenceCacher])
            def output_text_files(record):
                file_path = record.get_dir("my_files")
                my_file_list = [os.path.join(file_path, f"my_file_{num}") for num in range(20)]

                for file in my_file_list:
                    with open(file, 'w') as outfile:
                        outfile.write("test")

                return my_file_list
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, extension=".json", **kwargs)

    def check(self) -> bool:
        # check the file list file exists
        if not super().check():
            return False

        # load the file list and check each file
        # NOTE: we don't need to re-check args overwrite because that
        # would already have applied in the super check
        with open(self.get_path()) as infile:
            files = json.load(infile)

        if type(files) == list:
            for file in files:
                logging.debug("Checking from file list: '%s'" % file)
                if not os.path.exists(file):
                    return False
        else:
            if not os.path.exists(files):
                return False

        return True

    def load(self) -> Union[list[str], str]:
        with open(self.get_path()) as infile:
            files = json.load(infile)
        return files

    def save(self, files: Union[list[str], str]) -> str:
        path = self.get_path()
        with open(path, "w") as outfile:
            json.dump(files, outfile, indent=4)
        return path
