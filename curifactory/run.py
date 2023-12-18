"""Class for tracking run metadata."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class RunMetadata:
    """Data structure for tracking all the relevant metadata for a run,
    making it easier/providing a consistent interface for accessing
    the information and converting it into formats necessary for saving.
    """

    reference: str
    """The full reference name of the experiment, usually
        ``[experiment_name]_[run_number]_[timestamp]``."""
    experiment_name: str
    """The name of the experiment and/or the prefix used for caching."""
    run_number: int
    """The run counter for experiments with the given name."""
    timestamp: datetime
    """The datetime timestamp for when the manager is initialized (and usually
    also when the experiment starts running.)"""

    param_files: list[str]
    """The list of parameter file names (minus extension, as they would be
        passed into the CLI.)"""
    params: dict[str, list[list[str, str]]]
    """A dictionary of parameter file names for keys, where each value is an array of arrays,
    each inner array containing the parameter set name and the parameter set hash, for the
    parameter sets that come from that parameter file.

    e.g. ``{"my_param_file": [ [ "my_param_set", "44b5e428e7165975a3e4f0d1674dbe5f" ] ] }``
    """
    full_store: bool
    """Whether this store was being fully exported or not."""

    commit: str
    """The current git commit hash."""
    workdir_dirty: bool
    """True if there are uncommited changes in the git repo."""
    uncommited_patch: str
    """The output of ``git diff -p`` at runtime, to help more precisely reconstruct current codebase."""

    status: str
    """Ran status: success/incomplete/error/etc."""
    cli: str
    """The CLI line this run was created with."""
    reproduce: str
    """The translated CLI line to reproduce this run."""

    hostname: str
    """The name of the machine this experiment ran on."""
    user: str
    """The name of the user account the experiment was run with."""
    notes: str
    """User-entered notes associated with a session/run to output into the report etc."""

    pip_freeze: str
    """The output from a ``pip freeze`` command."""
    conda_env: str
    """The output from ``conda env export --from-history``."""
    conda_env_full: str
    """The output from ``conda env export``."""
    os: str
    """The name of the current OS running curifactory."""

    def as_sql_safe_dict(self) -> dict:
        """Meant to be used when inserting/updating values in the Runs
        sql table.

        The targeted column names can be found in dbschema.py.
        """
        pass
