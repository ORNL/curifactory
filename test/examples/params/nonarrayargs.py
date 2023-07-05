# Represents an incorrectly constructed get_params that returns
# an args instance not wrapped in a list.

from test.examples.params.basic import Args


def get_params():
    args = Args(name="empty", starting_data=[0, 0, 1])  # noqa: F841

    return args
