import argparse
import logging

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
