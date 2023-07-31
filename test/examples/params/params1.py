"""Make sure a sub module parameter file shows up and is usable."""


from test.examples.params.basic import Args


def get_params():
    return [Args(name="test1", starting_data=[0, 1, 2])]
