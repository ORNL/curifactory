# Represents an incorrectly constructed get_params that doesn't return anything

from test.examples.params.basic import Args


def get_params():
    all_args = []
    args = Args(name="empty", starting_data=[0, 0, 1])  # noqa: F841

    return all_args
