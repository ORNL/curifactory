"""Local 'database' of runs class."""

import json
import os

from curifactory import utils


class ManagerStore:
    """Manages the mini database of metadata on previous experiment runs. This is how we
    keep track of experiment run numbers etc. A metadata block for each run is stored in
    the manager cache path under ``store.json``.

    Note that the metadata blocks we keep track of for each run follows the following example:

    .. code-block:: json

        {
            "reference": "example_experiment_1_2021-06-15-T100003",
            "experiment_name": "example_experiment",
            "run_number": 1,
            "timestamp": "2021-06-15-T100003",
            "commit": "",
            "param_files": ["example_params"],
            "params": { "example_params": [ [ "test_params", "44b5e428e7165975a3e4f0d1674dbe5f" ] ] },
            "full_store": false,
            "status": "complete",
            "cli": "experiment example_experiment -p example_params",
            "hostname": "mycomputer",
            "notes": ""
        }

    Args:
        manager_cache_path (str): The path to the directory to keep the ``store.json``.
    """

    def __init__(self, manager_cache_path: str):
        self.runs = []
        """The list of metadata blocks for each run."""
        self.path = manager_cache_path
        """The location to store the ``store.json``."""

        if self.path[-1] != "/":
            self.path += "/"

        self.path += "store.json"

        self.load()

    def load(self):
        """Load the current experiment database from ``store.json`` into ``self.runs``."""
        if os.path.exists(self.path):
            with open(self.path) as infile:
                self.runs = json.load(infile)

    def save(self):
        """Save the current database in ``self.runs`` into the ``store.json`` file."""
        with open(self.path, "w") as outfile:
            json.dump(self.runs, outfile, indent=4)

    def get_experiment_runs(self, experiment_name: str) -> list[dict]:
        """Get all the runs associated with the specified experiment name from the database.

        Args:
            experiment_name (str): The experiment name to get all run metadata for.

        Returns:
            A list of all dictionaries (metadata blocks) that have the requested experiment name.
        """
        experiment_runs = []
        for run in self.runs:
            if run["experiment_name"] == experiment_name:
                experiment_runs.append(run)
        return experiment_runs

    def get_run(self, ref_name: str) -> tuple[dict, int]:
        """Get the metadata block for the run with the specified reference name.

        Args:
            ref_name (str): The run reference name, following the [experiment_name]_[run_number]_[timestamp] format.

        Returns:
            A dictionary (metadata block) for the run with the requested reference name, and the
            index of the run within the total list of runs.
        """
        for index, run in enumerate(self.runs):
            if run["reference"] == ref_name:
                return run, index
        return None, -1

    def add_run(self, mngr) -> dict:
        """Add a new metadata block to the store for the passed ``ArtifactManager`` instance.

        Note that this automatically calls the ``save()`` function.

        Args:
            mngr (ArtifactManager): The manager to grab run metadata from.

        Returns:
            The newly created dictionary (metadata block) for the current manager's run.
        """
        prev_runs = self.get_experiment_runs(mngr.experiment_name)
        if len(prev_runs) == 0:
            mngr.experiment_run_number = 1
        else:
            mngr.experiment_run_number = prev_runs[-1]["run_number"] + 1
        mngr.git_commit_hash = utils.get_current_commit()
        mngr.git_workdir_dirty = utils.check_git_dirty_workingdir()

        # create the metadata block
        run = {
            "reference": mngr.get_reference_name(),
            "experiment_name": mngr.experiment_name,
            "run_number": mngr.experiment_run_number,
            "timestamp": mngr.get_str_timestamp(),
            "commit": mngr.git_commit_hash,
            "workdir_dirty": mngr.git_workdir_dirty,
            "param_files": mngr.parameter_files,
            "params": mngr.param_file_param_sets,
            "full_store": mngr.store_full,
            "status": "incomplete",
            "cli": mngr.run_line,
            "hostname": mngr.hostname,
            "notes": mngr.notes,
        }

        # sanitize reproduction cli command
        if mngr.store_full:
            run = self._get_reproduction_line(mngr, run)

        self.runs.append(run)

        self.save()
        return run

    # NOTE: we have to call this both from add_run and update_run because manager stores itself on init, but if
    # someone _later_ sets store_full (maybe in a live run) we need to be able to handle this being added to the run_info
    def _get_reproduction_line(self, mngr, run: dict) -> dict:
        sanitized_run_line = mngr.run_line
        if "--overwrite " in sanitized_run_line:
            sanitized_run_line = sanitized_run_line.replace("--overwrite ", "")
        if sanitized_run_line.endswith("--overwrite"):
            sanitized_run_line = sanitized_run_line[:-12]
        sanitized_run_line = sanitized_run_line.replace("--store-full ", "")
        if sanitized_run_line.endswith("--store-full"):
            sanitized_run_line = sanitized_run_line[:-13]

        cache_path = mngr.get_run_output_path()
        mngr.reproduction_line = (
            f"{sanitized_run_line} --cache {cache_path}/artifacts --dry-cache"
        )

        run["reproduce"] = mngr.reproduction_line
        return run

    def update_run(self, mngr) -> dict:
        """Updates the metadata in the database for the run associated with the passed ``ArtifactManager``.

        This is currently just used to update the status and include any error messages if relevant, when an experiment
        finishes running.

        Note that this automatically calls the ``save()`` function.

        Args:
            mngr (ArtifactManager): The manager to grab run metadata from.

        Returns:
            The updated dictionary (metadata block) for the run. It returns None if the experiment isn't
            found in the database.
        """
        run_info, index = self.get_run(mngr.get_reference_name())
        if index == -1:
            # TODO error?
            return None

        run_info["status"] = mngr.status
        if mngr.status == "error":
            run_info["error"] = mngr.error
        run_info["param_files"] = mngr.parameter_files
        run_info["params"] = mngr.param_file_param_sets

        if mngr.store_full:
            run_info = self._get_reproduction_line(mngr, run_info)

        self.runs[index] = run_info

        self.save()
        return run_info
