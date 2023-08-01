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
from enum import Enum
from pathlib import Path
from typing import Literal, Optional, Union

import pandas as pd

from curifactory import hashing, utils


class Lazy:
    """A class to indicate a stage output as a lazy-cache object - curifactory will
    attempt to keep this out of memory as much as possible, immediately caching and deleting,
    and loading back into memeory only when needed.

    This object is used by "wrapping" a stage output string with the class.

    Example:
        .. code-block:: python

            @stage(inputs=None, outputs=["small_output", Lazy("large_output")], cachers=[PickleCacher]*2)
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


# NOTE: this isn't a requirement for DAGs to work, leaving here as a reminder, but deciding if
# this versus simply a pathcacher works better should be a different issue
# class Ref:
#     """A 'reference' output is very similar to the ``Lazy`` class, but handled differently semantically by
#     curifactory. A ``Ref`` is assumed to be a load-only output, where the stage that creates it is assumed
#     to handle creating and saving the object, and the cacher associated with the ``Ref`` is only in charge
#     of loading it when and if it's needed by later stages.

#     This is useful in cases where a stage is making an external system call to a script that's creating some
#     file, and we only want to directly bring the results of that file into curifactory rather than loading
#     and returning it in the stage, for it to just be re-saved again by the cacher.


#     Example:
#         .. code-block:: python

#             @stage(outputs=[Ref("some_json")], cachers=[JsonCacher])
#             def save_outside_of_cacher(record):
#                 pass


#                 # TODO

#     """

#     def __init__(self, name: str, resolve: bool = True):
#         self.name = name
#         self.cacher: Cacheable = None
#         self.resolve = resolve

#     def load(self):
#         return self.cacher.load()

#     def __str__(self):
#         return self.name


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
                and self.extension is not None
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
        if not self.record.manager.map_mode:
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
            params_name=self.record.params.name
            if self.record.params is not None
            else None,
            record_name=self.record.get_reference_name(),
            stage=self.record.manager.current_stage_name,
            artifact_name=self.name,
            cacher_type=str(type(self)),
            record_prior_stages=self.record.stages[:-1],
            prior_records=input_record_names,
            params=hashing.param_set_string_hash_representations(self.record.params)
            if self.record.params is not None
            else None,
            extra=self.extra_metadata,  # cachers can store any additional info here they want.
            manager_run_info=manager_run_info,
        )

    def save_metadata(self):
        metadata_path = self.get_path("_metadata.json")
        with open(metadata_path, "w") as outfile:
            if self.metadata is None:
                # this either means we haven't collected metadata, or this is save() being called inline
                logging.warning(
                    "Cacher metadata hasn't been collected or has no associated record. Only saving extra_metadata fields."
                )
                json.dump(
                    dict(extra=self.extra_metadata), outfile, indent=2, default=str
                )
            else:
                json.dump(self.metadata, outfile, indent=2, default=str)

    def load_metadata(self) -> dict:
        metadata_path = self.get_path("_metadata.json")
        if os.path.exists(metadata_path):
            with open(metadata_path) as infile:
                self.metadata = json.load(infile)
                self.extra_metadata = self.metadata["extra"]
        return self.metadata

    def check(self) -> bool:
        """Check to see if this cacheable needs to be written or not.

        Note:
            This function will always return False if the args are ``None``.

        Returns:
            ``True`` if we find the cached file and the current parameter set
            doesn't specify to overwrite, otherwise ``False``.
        """
        logging.debug("Searching for cached file at '%s'...", self.get_path())
        if os.path.exists(self.get_path()):
            if (
                self.record is not None
                and self.record.params is None
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
                    if record.params is not None and record.params.overwrite:
                        logging.debug("Record with overwrite found")
                        return False
                # we made it through each record and they weren't overwrite, we're good
                logging.debug("No records had overwrite, will use cache")
                if self.record.manager.map_mode:
                    logging.debug("Cached object '%s' found", self.get_path())
                else:
                    logging.info("Cached object '%s' found", self.get_path())
                return True
            elif (
                self.record is not None
                and self.record.params is not None
                and not self.record.params.overwrite
            ):
                if self.record.manager.map_mode:
                    logging.debug("Cached object '%s' found", self.get_path())
                else:
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
        raise NotImplementedError(
            "Cacheable class does not have a save function implemented"
        )


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


class _PandasIOType(Enum):
    csv = "csv"
    json = "json"
    parquet = "parquet"
    pickle = "pkl"
    orc = "orc"
    hdf5 = "h5"
    excel = "xlsx"
    xml = "xml"


class PandasCacher(Cacheable):
    """Saves a pandas dataframe to selectable IO format.

    Args:
        format (str): Selected pandas IO format. Choices are:
            ("csv", "json", "parquet", "pickle",
            "orc", "hdf5", "excel", "xml")
        to_args (Dict): Dictionary of arguments to use in the pandas
            ``to_*()`` call.
        read_args (Dict): Dictionary of arguments to use in the pandas
            ``read_*()`` call.
    """

    def __init__(
        self,
        path_override: Optional[str] = None,
        format: Literal[
            "csv", "json", "parquet", "pickle", "orc", "hdf5", "excel", "xml"
        ] = "pickle",
        to_args: Optional[dict] = None,
        read_args: Optional[dict] = None,
        **kwargs,
    ):
        self.format = _PandasIOType[format]
        self.read_args = read_args
        self.to_args = to_args

        # set up default args for specific types, if none are provided
        if self.to_args is None:
            if self.format == _PandasIOType.json:
                self.to_args = {"double_precision": 15}
            elif self.format == _PandasIOType.hdf5:
                self.to_args = {"key": "df"}
            elif self.format == _PandasIOType.xml:
                self.to_args = {"index": False}
            else:
                self.to_args = {}

        if self.read_args is None:
            if self.format in (_PandasIOType.csv, _PandasIOType.excel):
                self.read_args = {"index_col": 0}
            else:
                self.read_args = {}

        if self.format == _PandasIOType.json:
            logging.warning(
                "Using this cacher is inadvisable for floating point data, as precision"
                "will be lost, creating the potential for different results when using"
                "cached values with this cacher as opposed to the first non-cached run."
            )

        super().__init__(
            path_override=path_override, extension=f".{self.format.value}", **kwargs
        )

    # TODO: 7/31/2023 - might be worth considering adding a function to "populate from metadata",
    # which would load the metadata for the specified path, and then populate both format and
    # read_args. This could make it a little simpler to use a pandas cacher inline in a notebook
    # for reading.

    def load(self):
        # select the appropriate pandas read function based on format
        if self.format == _PandasIOType.csv:
            pandas_read = pd.read_csv
        elif self.format == _PandasIOType.json:
            pandas_read = pd.read_json
        elif self.format == _PandasIOType.parquet:
            pandas_read = pd.read_parquet
        elif self.format == _PandasIOType.pickle:
            pandas_read = pd.read_pickle
        elif self.format == _PandasIOType.orc:
            pandas_read = pd.read_orc
        elif self.format == _PandasIOType.hdf5:
            pandas_read = pd.read_hdf
        elif self.format == _PandasIOType.excel:
            pandas_read = pd.read_excel
        elif self.format == _PandasIOType.xml:
            pandas_read = pd.read_xml
        else:
            raise RuntimeError(f"Invalid Pandas IO Type ({self.format.name}) selected")

        # double check that there's no pandas version mismatch
        # at some point it may be worth warning only on major/minor version difference
        self.load_metadata()
        if "pandas_version" in self.extra_metadata:
            if self.extra_metadata["pandas_version"] != pd.__version__:
                logging.warning(
                    "Attempting to use pandas v%s to load a dataframe that was initially saved with pandas v%s"
                    % (pd.__version__, self.extra_metadata["pandas_version"])
                )

        return pandas_read(self.get_path(), **self.read_args)

    def save(self, obj: pd.DataFrame) -> str:
        # select appropriate pandas write function based on format
        if self.format == _PandasIOType.csv:
            pandas_to = obj.to_csv
        elif self.format == _PandasIOType.json:
            pandas_to = obj.to_json
        elif self.format == _PandasIOType.parquet:
            pandas_to = obj.to_parquet
        elif self.format == _PandasIOType.pickle:
            pandas_to = obj.to_pickle
        elif self.format == _PandasIOType.orc:
            pandas_to = obj.to_orc
        elif self.format == _PandasIOType.hdf5:
            pandas_to = obj.to_hdf
        elif self.format == _PandasIOType.excel:
            pandas_to = obj.to_excel
        elif self.format == _PandasIOType.xml:
            pandas_to = obj.to_xml
        else:
            raise RuntimeError(f"Invalid Pandas IO Type ({self.format.name}) selected")
        # record relevant cacher information to help track down any issues if they arise
        self.extra_metadata["pandas_version"] = pd.__version__
        self.extra_metadata["to_args"] = self.to_args
        self.extra_metadata["read_args"] = self.read_args
        self.extra_metadata["format"] = self.format.name
        self.save_metadata()

        # write the thing!
        path = self.get_path()
        pandas_to(path, **self.to_args)
        return path


class PandasJsonCacher(PandasCacher):
    """Saves a pandas dataframe to JSON.

    Warning:

        Using this cacher is inadvisable for floating point data, as precision
        will be lost, creating the potential for different results when using
        cached values with this cacher as opposed to the first non-cached run.

    Args:
        to_json_args (Dict): Dictionary of arguments to use in the pandas
            ``to_json()`` call.
        read_json_args (Dict): Dictionary of arguments to use in the pandas
            ``read_json()`` call.

    Note:
        This is equivalent to using ``PandasCacher(format='json')``
    """

    def __init__(
        self,
        path_override: str = None,
        to_json_args: dict = dict(double_precision=15),
        read_json_args: dict = dict(),
        **kwargs,
    ):
        super().__init__(
            path_override=path_override,
            format="json",
            to_args=to_json_args,
            read_args=read_json_args,
            **kwargs,
        )


class PandasCsvCacher(PandasCacher):
    """Saves a pandas dataframe to CSV.

    Args:
        to_csv_args (Dict): Dictionary of arguments to use in the pandas
            ``to_csv()`` call.
        read_csv_args (Dict): Dictionary of arguments to use in the pandas
            ``read_csv()`` call.

    Note:
        This is equivalent to using ``PandasCacher(format='csv')``
    """

    def __init__(
        self,
        path_override: str = None,
        to_csv_args: dict = dict(),
        read_csv_args: dict = dict(index_col=0),
        **kwargs,
    ):
        super().__init__(
            path_override=path_override,
            format="csv",
            to_args=to_csv_args,
            read_args=read_csv_args,
            **kwargs,
        )


class FileReferenceCacher(Cacheable):
    """Saves a file path or list of file paths generated from a stage as a json file.
    The ``check`` function will check existence of all file paths.

    This is useful for instances where there may be a large number of files stored or
    generated to disk, as it would be unwieldy to return them all (or infeasible to keep them
    in memory) directly from the stage. When this cacher is checked for pre-existing,
    it tries to load the json file storing the filenames, and then checks for the existence of
    each path in that json file. If all of them exist, it will short-circuit computation.

    Using this cacher does mean the user is in charge of loading/saving the file paths correctly,
    but in some cases that may be desirable.

    This can also be used for storing a reference to a single file outside the normal cache.

    When combined with the ``get_dir`` call on the record, you can create a cached directory of
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


class RawJupyterNotebookCacher(Cacheable):
    """Take a list of code cells (where each cell is a list of strings containing python code)
    and turn it into a jupyter notebook. This is useful in situations where you want each
    experiment to have some form of automatically populated analysis that a reportable wouldn't
    sufficiently cover, e.g. an interactive set of widgets or dashboard.

    Example:

        .. code-block:: python

            @stage(inputs=["results_path"], outputs=["exploration_notebook"], cachers=[RawJupyterNotebookCacher])
            def make_exploration_notebook(record, results_path):
                def convert_path(path):
                    '''A function to translate paths to local folder path.'''
                    p = Path(path)
                    p = Path(*p.parts[2:])
                    return str(p)

                cells = [
                    [
                        "# imports",
                        "from curifactory.caching import JsonCacher",
                    ],
                    [
                        "# load things",
                        f"cacher = JsonCacher('./{convert_path(results_path)})",
                        "results = cacher.load()",
                        "results_metadata = cacher.metadata",
                    ],
                    [
                        "# analysis",
                        "...",
                    ],
                ]

                return cells
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, extension=".ipynb", **kwargs)

    def load(self):
        cells_path = self.get_path("_cells.json")
        return JsonCacher(cells_path).load()

    def save(self, obj: list[list[str]]):
        """This saves the raw cell strings to a _cells.json, and then uses
        ipynb-py-convert to change the output python script into a notebook
        format."""
        notebook_path = Path(self.get_path())
        cells_path = self.get_path("_cells.json")
        script_path = notebook_path.with_suffix(".py")

        cell_text = "\n\n# %%\n".join(["\n".join(inner_cell) for inner_cell in obj])

        with open(script_path, "w") as outfile:
            outfile.write(cell_text)
        utils.run_command(["ipynb-py-convert", script_path, notebook_path])
        os.remove(script_path)

        JsonCacher(cells_path).save(obj)
