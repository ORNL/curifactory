import json
import os
import pickle

from artifact import Artifact
from manager import Manager


class Cacheable:
    def __init__(self, path_override: str = None, extension: str = ""):
        self.path_override = path_override
        self.extension = extension
        self.artifact: Artifact = None

    def get_path(self):
        if self.path_override is not None:
            return self.path_override
        hash, _ = self.artifact.compute_hash()
        return f"{hash}_{self.artifact.name}{self.extension}"

    def check(self):
        Manager.get_manager().logger.debug(
            f"Checking for cached {self.artifact.name} at '{self.get_path()}'"
        )
        return os.path.exists(self.get_path())

    def save(self, obj):
        pass

    def load(self, obj):
        pass


class JsonCacher(Cacheable):
    def __init__(self, path_override: str = None):
        super().__init__(path_override, ".json")

    def save(self, obj):
        with open(self.get_path(), "w") as outfile:
            json.dump(obj, outfile)

    def load(self):
        with open(self.get_path()) as infile:
            obj = json.load(infile)
        return obj


class PickleCacher(Cacheable):
    def __init__(self, path_override: str = None):
        super().__init__(path_override, ".pkl")

    def save(self, obj):
        with open(self.get_path(), "wb") as outfile:
            pickle.dump(obj, outfile)

    def load(self):
        with open(self.get_path(), "rb") as infile:
            obj = pickle.load(infile)
        return obj
