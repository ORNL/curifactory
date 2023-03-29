""" Helper and utility functions for the library. """

import json
import logging
import os
import platform
import shutil
import subprocess
import sys

from rich import get_console, reconfigure
from rich.logging import RichHandler

TIMESTAMP_FORMAT = "%Y-%m-%d-T%H%M%S"
"""The datetime format string used for timestamps in experiment run reference names."""
CONFIGURATION_FILE = "curifactory_config.json"
"""The expected configuration filename."""

EDITORS = ["vim", "nvim", "emacs", "nano", "vi"]
"""The list of possible editor exec names to test for getting a valid text editor."""


def get_configuration() -> dict[str, str]:
    """Load the configuration file if available, with defaults for any
    keys not found. The config file should be "curifactory_config.json"
    in the project root.

    The defaults are:

    .. code-block:: json

        {
            "experiments_module_name": "experiments",
            "params_module_name": "params",
            "manager_cache_path": "data/",
            "cache_path": "data/cache",
            "runs_path": "data/runs",
            "logs_path": "logs/",
            "notebooks_path": "notebooks/",
            "reports_path": "reports/",
            "report_css_path": "reports/style.css",
        }

    Returns:
        the dictionary of configuration keys/values.
    """

    config_defaults = {
        "experiments_module_name": "experiments",
        "params_module_name": "params",
        "manager_cache_path": "data/",
        "cache_path": "data/cache",
        "runs_path": "data/runs",
        "logs_path": "logs/",
        "notebooks_path": "notebooks/",
        "reports_path": "reports/",
        "report_css_path": "reports/style.css",
    }

    # try to find configuration file in this dir or parent dirs (
    search_depth = 3
    prefix = ""
    while not os.path.exists(f"{prefix}{CONFIGURATION_FILE}") and search_depth > 0:
        prefix += "../"
        search_depth -= 1

    # get config file
    if os.path.exists(f"{prefix}{CONFIGURATION_FILE}"):
        with open(f"{prefix}{CONFIGURATION_FILE}") as infile:
            config = json.load(infile)

        # in case of any values that don't exist in explicit config
        for key in config_defaults:
            if key not in config:
                config[key] = config_defaults[key]

        # update paths if in subdir
        # NOTE: this doesn't update module names, because that requires actual code changes. Ideally,
        # this is only intended for things like notebooks to be able to use regular paths for live
        # curifactory usage, rather than actual experiment runs. For that it's on the user to correctly
        # ensure their current directory is set.
        for key in config:
            if key.endswith("_path"):
                config[key] = f"{prefix}{config[key]}"
    else:
        # defaults
        config = config_defaults

    return config


def get_editor() -> str:
    """Returns a text editor to use for richer text entry, such as in providing experiment notes."""

    def first_available_editor():
        for editor_name in EDITORS:
            if shutil.which(editor_name) is not None:
                return editor_name
        return None

    editor = None
    if "EDITOR" in os.environ:
        editor = os.getenv("EDITOR")
    elif first_available_editor() is not None:
        editor = first_available_editor()
    elif os.name == "nt":
        editor = "notepad"

    if editor is None:
        raise RuntimeError("No valid text editor could be found.")
    return editor


def human_readable_mem_usage(byte_count: int) -> str:
    """Takes the given byte count and returns a nicely formatted string that includes the suffix (K/M/GB).

    Args:
        byte_count (int): The number of bytes to convert into KB/MB/GB.
    """

    negative = False
    if byte_count < 0:
        negative = True
        byte_count *= -1

    suffix = "B"
    if byte_count > 10**9:
        suffix = "GB"
        byte_count /= 10**9
    elif byte_count > 10**6:
        suffix = "MB"
        byte_count /= 10**6
    elif byte_count > 10**3:
        suffix = "KB"
        byte_count /= 10**3

    if negative:
        return f"-{byte_count:.2f}{suffix}"
    return f"{byte_count:.2f}{suffix}"


def human_readable_time(seconds: float) -> str:
    """Takes the given time in seconds and returns a nicely formatted string that includes the suffix.

    Args:
        seconds (float): The time in seconds to convert.
    """

    converted = seconds
    suffix = "s"

    # .1 = 100ms
    # .1ms = 100us = .0001
    # .1us = 100ns = .0000001

    if seconds > 60 * 60:
        suffix = "h"
        converted /= 60 * 60
    elif seconds > 60:
        suffix = "m"
        converted /= 60
    elif seconds < 0.0000001:
        suffix = "ns"
        converted *= 10**9
    elif seconds < 0.0001:
        suffix = "us"
        converted *= 10**6
    elif seconds < 0.1:
        suffix = "ms"
        converted *= 10**3

    return f"{converted:.2f}{suffix}"


def get_command_output(cmd, silent=False) -> str:
    """Runs the command passed and returns the full string output of the command
    (minus the final newline).

    Args:
        cmd: Either a string command or array of strings, as one would pass to
            :code:`subprocess.run()`
    """
    try:
        cmd_return = subprocess.run(cmd, stdout=subprocess.PIPE)
    except:  # noqa: E722 -- TODO: we should actually handle this for the below note
        # NOTE - seems like we get filenotfound exceptions if it's an invalid command?
        # (e.g. on windows calling git when git isn't found from the env?)
        if not silent:
            logging.warning("Unable to run command '%s'" % cmd)
        return ""
    if cmd_return.returncode == 0:
        output = cmd_return.stdout.decode("utf-8")
        return output[:-2]  # TODO: (3/29/2023) is this definitely right?
        # seems like it would prob be different on windows vs linux
    return ""


def run_command(cmd):
    """Prints output from running a command as it occurs.

    Args:
        cmd: Either a string command or array of strings, as one would pass to
            :code:`subprocess.run()`
    """
    logging.debug("Running command '%s'" % str(cmd))

    print(*cmd)

    with subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=1, text=True) as p:
        for line in p.stdout:
            print(line, end="")  # process line here


def get_current_commit() -> str:
    """Returns printed output from running :code:`git rev-parse HEAD` command."""
    return get_command_output(["git", "rev-parse", "HEAD"])


def check_git_dirty_workingdir() -> str:
    """Checks if git working directory is dirty or not. This is used to indicate
    potential reproducibility problems in the report and console output."""
    if get_command_output(["git", "diff", "--stat"]) != "":
        return True
    return False


def get_pip_freeze() -> str:
    """Returns printed output from running :code:`pip freeze` command."""
    return get_command_output(["pip", "freeze"])


def get_conda_env() -> str:
    """Returns printed output from running :code:`conda env export --from-history` command."""
    output = ""
    execs = ["conda", "mamba", "micromamba"]
    while output == "" and len(execs) > 0:
        cmd_word = execs[0]
        output = get_command_output([cmd_word, "env", "export", "--from-history"], True)
        execs.remove(cmd_word)
    if output == "":
        logging.warning("Unable to run conda or similar command")
        return output
    else:
        # fix random garbage at end of output (?!)
        output = output[:-7]
        return output


def get_conda_list() -> str:
    """Returns printed output from running :code:`conda env export --from-history` command."""
    return get_command_output(["conda", "list"])


def get_os() -> str:
    """Get the current OS name and version."""
    return str(platform.platform())


def get_py_opening_comment(lines):
    """Parse the passed lines of a python script file for a top of file docstring.
    This is used to get parameter and experiment file descriptions, so be sure to
    always comment your code!"""
    content = ""

    def check_for_end(line):
        if '"""' in line or "'''" in line:
            return True
        return False

    def endline_index(line):
        if '"""' in line:
            return line.index('"""')
        else:
            return line.index("'''")

    if len(lines[0]) > 3 and (lines[0].startswith('"""') or lines[0].startswith("'''")):
        if len(lines[0]) > 3 and not check_for_end(lines[0][3:]):
            content += lines[0][3:]

            for line in lines[1:]:
                if not check_for_end(line):
                    content += " " + line
                else:
                    content += " " + line[: endline_index(line)]
                    break
        elif len(lines[0]) > 3 and check_for_end(lines[0][3:]):
            content += lines[0][3 : endline_index(lines[0][3:]) + 3]

    # fix line breaks
    content = content.replace("\n", " ")
    while "  " in content:
        content = content.replace("  ", " ")

    return content


def set_logging_prefix(prefix):
    """Set the prefix content of the logger, which is incorporated in the log formatter. Currently
    this is just used to include pid number when running in parallel."""
    # https://stackoverflow.com/questions/17558552/how-do-i-add-custom-field-to-python-log-format-string
    old_factory = logging.getLogRecordFactory()

    def new_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.prefix = prefix
        return record

    logging.setLogRecordFactory(new_factory)


def init_logging(
    log_path=None,
    level=logging.INFO,
    log_errors=False,
    include_process=False,
    no_color=False,
    quiet=False,
    plain=False,
):
    """Sets up logging configuration, including the associated file output.

    Args:
        log_path (str): Folder to store output logs in. If :code:`None`, only log
            to console.
        level: The logging level to output.
        log_errors (bool): Whether to include error messages in the log output or not.
        include_process (bool): Whether to include the PID prefix value in the logger.
            This is mostly only used for when the :code:`--parallel` flag is used, to
            help track which log message is from which process.
        no_color (bool): Suppress colors in console output.
        quiet (bool): Suppress all console log output.
        plain (bool): Output plain text log rather than rich output.
    """
    if include_process:
        # NOTE: taking out %(filename)s because it takes up space and makes the beginning of the log entries "jagged"
        plain_log_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] {PID:%(process)s} - %(prefix)s%(message)s"
        )
        rich_log_formatter = logging.Formatter(
            "{PID:%(process)s} - %(prefix)s%(message)s"
        )
    else:
        plain_log_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] - %(prefix)s%(message)s"
        )
        rich_log_formatter = logging.Formatter("%(prefix)s%(message)s")
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.propagate = False
    root_logger.handlers = []

    if plain:
        # 4 characters so that it lines up all nice
        logging.addLevelName(logging.DEBUG, "DBUG")

    set_logging_prefix("")

    if log_path is not None:
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(plain_log_formatter)
        root_logger.addHandler(file_handler)

    if plain and not quiet:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(plain_log_formatter)
        root_logger.addHandler(console_handler)

    if not plain:
        if no_color:
            reconfigure(no_color=True)
        if not quiet:
            # console = Console(no_color=no_color)
            console_handler = RichHandler(
                console=get_console(),
                show_time=True,
                show_level=True,
                show_path=True,
                rich_tracebacks=True,
                tracebacks_show_locals=True,
                log_time_format="%X",
                keywords=["-----", "(aggregate)"],
            )
            console_handler.setFormatter(rich_log_formatter)
            root_logger.addHandler(console_handler)

    # https://stackoverflow.com/questions/27538879/how-to-disable-loggers-from-other-modules
    # disable all loggers except ours (TODO: may want to config this at some point)
    for name, logger in logging.root.manager.loggerDict.items():
        logger.disabled = True

    # sys.stdout = StreamToLogger(logging.INFO)
    if log_errors:
        sys.stderr = StreamToLogger(logging.ERROR)

    # logging.getLogger("torch").setLevel(logging.WARNING)
    # logging.getLogger("transformers").setLevel(logging.WARNING)
    # logging.getLogger("requests").setLevel(logging.WARNING)
    # logging.getLogger("urllib3").setLevel(logging.WARNING)
    # logging.getLogger("snorkel").setLevel(logging.WARNING)
    # logging.getLogger("snorkel.labeling.model").setLevel(logging.WARNING)
    # logging.getLogger("snorkel.labeling.model.logger").setLevel(logging.WARNING)


# https://stackoverflow.com/questions/19425736/how-to-redirect-stdout-and-stderr-to-logger-in-python
class StreamToLogger:
    def __init__(self, level):
        # self.logger = logger
        self.level = level

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            logging.log(self.level, line.rstrip())
