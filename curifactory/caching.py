"""Classes for various caching strategies, known as "cachers"

This is handled through a base :code:`Cacheable` class, and each "strategy"
cacher class extends it.
"""

import json
import logging
import os
import pandas as pd
import pickle


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

    def set_path(self, path: str):
        """Changes the :code:`path` to the passed value."""
        self.path = path + self.extension
        return self.path

    def check(self, args):
        """Check to see if this cacheable needs to be written or not.

        Note:
            This function will always return False if the args are :code:`None`.

        Args:
            args: The :code:`ExperimentArgs` to use to check for any overwrite flags.

        Returns:
            True if we find the cached file and the current :code:`Args`
            don't specify to overwrite, otherwise False.
        """
        logging.debug("Searching for cached file at %s...", self.path)
        if os.path.exists(self.path):
            if args is not None and not args.overwrite:
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
        with open(self.path, "r") as infile:
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
    """Saves a pandas dataframe to JSON."""

    def __init__(self, path_override=None):
        super().__init__(".json", path_override=path_override)

    def load(self):
        return pd.read_json(self.path)

    def save(self, obj):
        obj.to_json(self.path)


class PandasCsvCacher(Cacheable):
    """Saves a pandas dataframe to CSV."""

    def __init__(self, path_override=None):
        super().__init__(".csv", path_override=path_override)

    def load(self):
        return pd.read_csv(self.path)

    def save(self, obj):
        obj.to_csv(self.path)
