import argparse
import logging
import os
import platform
import subprocess

from graphviz import Digraph


# https://stackoverflow.com/questions/28094590/ignore-str-formatfoo-if-key-doesnt-exist-in-foo
class FailsafeDict(dict):
    def __getitem__(self, item):
        try:
            return super().__getitem__(item)
        except KeyError:
            return "{" + str(item) + "}"


def set_logging_prefix(prefix: str):
    # https://stackoverflow.com/questions/17558552/how-do-i-add-custom-field-to-python-log-format-string
    old_factory = logging.getLogRecordFactory()

    if isinstance(old_factory, PrefixedLogFactory):
        old_factory.prefix = prefix
    else:
        logging.setLogRecordFactory(PrefixedLogFactory(old_factory, prefix))


class PrefixedLogFactory:
    """Note that we have to use this to prevent weird recursion issues.

    My understanding is that since logging is in the global context, after many many tests,
    the old_factory keeps getting set to the previous new_factory, and you end up with a massive
    function chain. Using this class approach above, we can check if we've already set the
    factory to an instance of this class, and just update the prefix on it.

    https://stackoverflow.com/questions/59585861/using-logrecordfactory-in-python-to-add-custom-fields-for-logging
    """

    def __init__(self, original_factory, prefix):
        self.original_factory = original_factory
        self.prefix = prefix

    def __call__(self, *args, **kwargs):
        record = self.original_factory(*args, **kwargs)
        record.prefix = self.prefix
        return record


class AppendReplaceAction(argparse.Action):
    """If specified we want to _replace_ the default, but keep appending as a list?"""

    # does 'store' already do this?
    def __call__(self, parser, namespace, values, option_string=None):
        pass


def init_graphviz_graph():
    dot = Digraph(
        graph_attr={"nodesep": ".05", "ranksep": ".09"}, edge_attr={"arrowsize": "0.5"}
    )
    dot._edges = []
    return dot


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


def run_command(cmd: list[str]):
    """Prints output from running a command as it occurs.

    Args:
        cmd: Either a string command or array of strings, as one would pass to
            ``subprocess.run()``
    """
    logging.debug("Running command '%s'" % str(cmd))

    print(*cmd)

    with subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=1, text=True) as p:
        for line in p.stdout:
            print(line, end="")  # process line here


def get_command_output(cmd: list[str], silent: bool = False) -> str:
    """Runs the command passed and returns the full string output of the command
    (minus the final newline).

    Args:
        cmd: Either a string command or array of strings, as one would pass to
            ``subprocess.run()``
    """
    try:
        cmd_return = subprocess.run(cmd, capture_output=True)
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


def get_os() -> str:
    """Get the current OS name and version."""
    return str(platform.platform())


def get_current_commit() -> str:
    """Returns printed output from running ``git rev-parse HEAD`` command."""
    if not os.path.exists(".git"):
        return "No git repository found"
    return get_command_output(["git", "rev-parse", "HEAD"])


def check_git_dirty_workingdir() -> bool:
    """Checks if git working directory is dirty or not. This is used to indicate
    potential reproducibility problems in the report and console output."""
    if not os.path.exists(".git"):
        return True
    if get_command_output(["git", "diff", "--stat"]) != "":
        return True
    return False


def get_git_dirty_patch() -> str:
    """Get the diff from the last commit."""
    diff = get_command_output(["git", "diff"])
    return diff


def get_pip_freeze() -> str:
    """Returns printed output from running ``pip freeze`` command."""
    return get_command_output(["pip", "freeze"])


def get_conda_env(requested_only: bool = False) -> str:
    """Returns printed output from running ``conda env export --from-history`` command."""
    output = ""
    execs = ["conda", "mamba", "micromamba"]
    while output == "" and len(execs) > 0:
        cmd_word = execs[0]
        command_words = [cmd_word, "env", "export"]
        if requested_only:
            command_words.append("--from-history")
        output = get_command_output(command_words, True)
        execs.remove(cmd_word)
    if output == "":
        logging.warning("Unable to run conda or similar command")
        return output
    else:
        # fix random garbage at end of output (?!)
        output = output[:-7]
        return output
