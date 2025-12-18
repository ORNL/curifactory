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
