from dataclasses import dataclass

from sklearn.base import ClassifierMixin
from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

import curifactory as cf
from curifactory.caching import PickleCacher
from curifactory.reporting import JsonReporter


@dataclass
class Args(cf.ExperimentArgs):
    balanced: bool = False
    """Whether class weights should be balanced or not."""
    n: int = 100
    """The number of trees for a random forest."""
    seed: int = 42
    """The random state seed for data splitting and model training."""
    model_type: ClassifierMixin = LogisticRegression
    """The sklearn model to use."""
    test_percent: float = 0.25
    """The percentage of data to use for testing."""


@cf.stage(
    inputs=None, outputs=["training_data", "testing_data"], cachers=[PickleCacher] * 2
)
def load_data(record):
    args: Args = record.args

    data = load_iris()
    x_train, x_test, y_train, y_test = train_test_split(
        data.data, data.target, test_size=args.test_percent, random_state=args.seed
    )

    return (x_train, y_train), (x_test, y_test)


@cf.stage(inputs=["training_data"], outputs=["model"], cachers=[PickleCacher])
def train_model(record, training_data):
    args: Args = record.args

    # set up common arguments from passed parameters
    weight = "balanced" if args.balanced else None
    model_args = dict(class_weight=weight, random_state=args.seed)

    # set up model-specific from parameters
    if type(args.model_type) == RandomForestClassifier:
        model_args.update(dict(n_estimators=args.n))

    # fit the parameterized model
    clf = args.model_type(**model_args).fit(training_data[0], training_data[1])
    return clf


@cf.aggregate(outputs=["scores"], cachers=None)
def test_models(record, records):
    scores = {}

    # iterate through every record and score its associated model
    for prev_record in records:
        if "model" in prev_record.state:
            score = prev_record.state["model"].score(
                prev_record.state["testing_data"][0],
                prev_record.state["testing_data"][1],
            )

            # store the result keyed to the argument set name
            scores[prev_record.args.name] = score

    print(scores)
    record.report(JsonReporter(scores))
    return scores


def get_params():
    return [
        Args(name="simple_lr", balanced=True, model_type=LogisticRegression, seed=1),
        Args(name="simple_rf", model_type=RandomForestClassifier, seed=1),
    ]


def run(argsets, manager):
    for argset in argsets:
        record = cf.Record(manager, argset)
        train_model(load_data(record))

    test_models(cf.Record(manager, None))
