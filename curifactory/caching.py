"""Classes for various caching strategies, known as "cachers"

This is handled through a base :code:`Cacheable` class, and each "strategy"
cacher class extends it.
"""

import json
import logging
import os
import pickle
from typing import Dict, List, Union

import pandas as pd


class Lazy:
    """A class to indicate a stage output as a lazy-cache object - curifactory will
    attempt to keep this out of memory as much as possible, immediately caching and deleting,
    and loading back into memeory only when needed."""

    def __init__(self, name: str):
        self.name = name
        self.cacher: Cacheable = None

    def load(self):
        return self.cacher.load()

    def __str__(self):
        return self.name


class Cacheable:
    """The base caching class, any caching strategy should extend this.

    Args:
        extension (str): The filetype extension to add at the end of the path.
        path_override (str): Use a specific path for the cacheable, rather than
            automatically setting it.
    """

    def __init__(self, extension: str, path_override=None):
        self.extension = extension
        """str: The filetype extension to add at the end of the path."""
        self.path = ""
        """str: The path of the cacheable to write out."""
        self.path_override = path_override
        """str: Use a specific path for the cacheable, rather than automatically
            setting it."""
        if self.path_override is not None:
            self.path = self.path_override
        self.record = None
        """Record: the current record this cacheable is caching under. This can be used to get a copy of the current args instance."""

    def set_path(self, path: str):
        """Changes the :code:`path` to the passed value."""
        self.path = path + self.extension
        return self.path

    def check(self) -> bool:
        """Check to see if this cacheable needs to be written or not.

        Note:
            This function will always return False if the args are :code:`None`.

        Returns:
            True if we find the cached file and the current :code:`Args`
            don't specify to overwrite, otherwise False.
        """
        logging.debug("Searching for cached file at %s...", self.path)
        if os.path.exists(self.path):
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
                logging.info("Cached object '%s' found", self.path)
                return True
            elif (
                self.record is not None
                and self.record.args is not None
                and not self.record.args.overwrite
            ):
                logging.info("Cached object '%s' found", self.path)
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

    def __init__(self, path_override=None):
        super().__init__(".json", path_override=path_override)

    def load(self):
        with open(self.path) as infile:
            obj = json.load(infile)
        return obj

    def save(self, obj):
        with open(self.path, "w") as outfile:
            json.dump(obj, outfile, indent=4, default=lambda x: str(x))


class PickleCacher(Cacheable):
    """Dumps an object to a pickle file."""

    def __init__(self, path_override=None):
        super().__init__(".pkl.gz", path_override=path_override)

    def load(self):
        with open(self.path, "rb") as infile:
            obj = pickle.load(infile)
        return obj

    def save(self, obj):
        with open(self.path, "wb") as outfile:
            pickle.dump(obj, outfile)


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
        to_json_args: Dict = dict(double_precision=15),
        read_json_args: Dict = dict(),
    ):
        self.read_json_args = read_json_args
        self.to_json_args = to_json_args
        super().__init__(".json", path_override=path_override)

    def load(self):
        return pd.read_json(self.path, **self.read_csv_args)

    def save(self, obj):
        obj.to_json(self.path, **self.to_json_args)


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
        to_csv_args: Dict = dict(),
        read_csv_args: Dict = dict(index_col=0),
    ):
        self.read_csv_args = read_csv_args
        self.to_csv_args = to_csv_args
        super().__init__(".csv", path_override=path_override)

    def load(self):
        return pd.read_csv(self.path, **self.read_csv_args)

    def save(self, obj):
        obj.to_csv(self.path, **self.to_csv_args)


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

    def __init__(self, path_override=None):
        super().__init__(".json", path_override=path_override)

    def check(self) -> bool:
        # check the file list file exists
        if not super().check():
            return False

        # load the file list and check each file
        # NOTE: we don't need to re-check args overwrite because that
        # would already have applied in the super check
        with open(self.path) as infile:
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

    def load(self) -> Union[List[str], str]:
        with open(self.path) as infile:
            files = json.load(infile)
        return files

    def save(self, files: Union[List[str], str]):
        with open(self.path, "w") as outfile:
            json.dump(files, outfile, indent=4)
