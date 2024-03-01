from dataclasses import dataclass
from typing import Callable

from artifact import Artifact, ArtifactList, Artifacts
from caching import PickleCacher
from experiment import experiment
from sklearn.base import ClassifierMixin
from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from stage import stage

# ===============================================
# OLD EXAMPLE
# ===============================================

# @dataclass
# class Params(cf.ExperimentParameters):
#     balanced: bool = False
#     """Whether class weights should be balanced or not."""
#     n: int = 100
#     """The number of trees for a random forest."""
#     seed: int = 42
#     """The random state seed for data splitting and model training."""
#     model_type: ClassifierMixin = LogisticRegression
#     """The sklearn model to use."""
#     test_percent: float = 0.25
#     """The percentage of data to use for testing."""
#
#
# @cf.stage(
#     inputs=None, outputs=["training_data", "testing_data"], cachers=[PickleCacher] * 2
# )
# def load_data(record):
#     params: Params = record.params
#
#     data = load_iris()
#     x_train, x_test, y_train, y_test = train_test_split(
#         data.data, data.target, test_size=params.test_percent, random_state=params.seed
#     )
#
#     return (x_train, y_train), (x_test, y_test)
#
#
# @cf.stage(inputs=["training_data"], outputs=["model"], cachers=[PickleCacher])
# def train_model(record, training_data):
#     params: Params = record.params
#
#     # set up common arguments from passed parameters
#     weight = "balanced" if params.balanced else None
#     model_args = dict(class_weight=weight, random_state=params.seed)
#
#     # set up model-specific from parameters
#     if type(params.model_type) == RandomForestClassifier:
#         model_args.update(dict(n_estimators=params.n))
#
#     # fit the parameterized model
#     clf = params.model_type(**model_args).fit(training_data[0], training_data[1])
#     return clf
#
#
# @cf.aggregate(inputs=["model", "testing_data"], outputs=["scores"], cachers=None)
# def test_models(
#     record: cf.Record,
#     records: list[cf.Record],
#     model: dict[cf.Record, any],
#     testing_data: dict[cf.Record, any],
# ):
#     scores = {}
#
#     # iterate through every record and score its associated model
#     for r, r_model in model.items():
#         score = r_model.score(testing_data[r][0], testing_data[r][1])
#
#         # store the result keyed to the argument set name
#         scores[r.params.name] = score
#
#     print(scores)
#     record.report(JsonReporter(scores))
#     return scores
#
#
# def get_params():
#     return [
#         Params(name="simple_lr", balanced=True, model_type=LogisticRegression, seed=1),
#         Params(name="simple_rf", model_type=RandomForestClassifier, seed=1),
#     ]
#
#
# def run(param_sets, manager):
#     for param_set in param_sets:
#         record = cf.Record(manager, param_set)
#         train_model(load_data(record))
#
#     test_models(cf.Record(manager, None))


# ===============================================
# NEW EXAMPLE
# ===============================================


@stage(
    [
        Artifact("training_data", PickleCacher()),
        Artifact("testing_data", PickleCacher()),
    ]
)
def load_data(test_percent: float = 0.25, seed: int = 13):
    data = load_iris()
    x_train, x_test, y_train, y_test = train_test_split(
        data.data, data.target, test_size=test_percent, random_state=seed
    )
    return (x_train, y_train), (x_test, y_test)


@stage([Artifact("model", PickleCacher())])
def train_model(training_data, model_type, n=100, seed: int = 13, balanced=False):
    model_args = dict(random_state=seed)
    if balanced:
        model_args["class_weight"] = "balanced"

    if type(model_type) == RandomForestClassifier:
        model_args["n_estimators"] = n

    clf = model_type(**model_args).fit(training_data[0], training_data[1])
    return clf


@stage([Artifact("scores")])
def test_models(names, models, testing_data):
    scores = {}

    for index, model in enumerate(models):
        score = model.score(testing_data[0], testing_data[1])

        scores[names[index]] = score
    return scores


@dataclass
class ModelParameters:
    name: str
    model_type: Callable
    n: int = 100
    balanced: bool = False


@experiment
def compare_sklearn_algs(
    model_set: list[ModelParameters], test_percent: float = 0.25, seed=1
):
    # train, test = load_data(test_percent, seed).outputs
    train, test = load_data(test_percent, seed)

    models = ArtifactList("models")
    for model in model_set:
        models.append(
            # train_model(train, model.model_type, model.n, seed, model.balanced).model
            train_model(train, model.model_type, model.n, seed, model.balanced)
        )

    # scores = test_models([model.name for model in model_set], models, test).outputs
    scores = test_models([model.name for model in model_set], models, test)

    return scores, {"scores": scores, "models": models, "test_data": test}


lr_vs_rf = compare_sklearn_algs(
    "lr_vs_rf",
    [
        ModelParameters("simple_lr", balanced=True, model_type=LogisticRegression),
        ModelParameters("simple_rf", model_type=RandomForestClassifier),
    ],
    seed=1,
)

Artifacts.display()
