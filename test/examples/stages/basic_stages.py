from curifactory import Record, stage


@stage([], ["data"])
def get_data(record: Record):
    return record.params.starting_data


@stage(["data"], ["sum"])
def sum_data(record: Record, data):
    return sum(data)
