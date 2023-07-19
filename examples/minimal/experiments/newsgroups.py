import logging
from dataclasses import dataclass

from sklearn.datasets import fetch_20newsgroups_vectorized
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier

import curifactory as cf
from curifactory.caching import PickleCacher
from curifactory.reporting import JsonReporter, LinePlotReporter


@dataclass
class Args(cf.ExperimentArgs):
    layers: tuple = (100,)
    seed: int = 42
    activation: str = "relu"
    sample_count: int = 9000
    dimesionality: int = 500


@cf.stage(
    inputs=None, outputs=["training_data", "testing_data"], cachers=[PickleCacher] * 2
)
def load_data(record):
    args: Args = record.args

    data = fetch_20newsgroups_vectorized()
    x_train, x_test, y_train, y_test = train_test_split(
        data.data[: args.sample_count, : args.dimesionality],
        data.target[: args.sample_count],
        test_size=0.75,
        random_state=args.seed,
    )
    logging.info(x_train.shape)

    return (x_train, y_train), (x_test, y_test)


@cf.stage(inputs=["training_data"], outputs=["model"], cachers=[PickleCacher])
def train_model(record, training_data):
    args: Args = record.args

    clf = MLPClassifier(args.layers, activation=args.activation).fit(
        training_data[0], training_data[1]
    )

    record.report(LinePlotReporter(clf.loss_curve_, name="loss"))
    return clf


@cf.aggregate(
    inputs=["model", "testing_data"], outputs=["scores"], cachers=[PickleCacher]
)
def test_models(
    record: cf.Record,
    records: list[cf.Record],
    model: dict[cf.Record, any],
    testing_data: dict[cf.Record, any],
):
    scores = {}

    # iterate through every record and score its associated model
    lines = {}
    for r, r_model in model.items():
        score = r_model.score(testing_data[r][0], testing_data[r][1])

        # store the result keyed to the argument set name
        scores[r.args.name] = score
        lines[r.args.name] = r_model.loss_curve_

    record.report(LinePlotReporter(lines))
    record.report(JsonReporter(scores))
    return scores


def get_params():
    args = []
    layer_sizes = [1, 10, 20, 50, 100]
    for size in layer_sizes:
        args.append(Args(name=f"{size}", layers=(size,)))
    return args


def run(argsets, manager):
    for argset in argsets:
        record = cf.Record(manager, argset)
        train_model(load_data(record))

    test_models(cf.Record(manager, None))
