from curifactory import stage, Record


@stage([], ["data"])
def get_data(record: Record):
    return record.args.starting_data


@stage(["data"], ["sum"])
def sum_data(record: Record, data):
    return sum(data)
