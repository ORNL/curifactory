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

    if type(model_type) is RandomForestClassifier:
        model_args["n_estimators"] = n

    clf = model_type(**model_args).fit(training_data[0], training_data[1])
    return clf


@stage([Artifact("score")])
def test_model(model, testing_data):
    score = model.score(testing_data[0], testing_data[1])
    return score


@stage([Artifact("scores")])
def test_models(names, models, testing_data):
    scores = {}

    for index, model in enumerate(models):
        score = model.score(testing_data[0], testing_data[1])

        scores[names[index]] = score
    return scores


@experiment
def test_sklearn_alg(
    model_type: Callable,
    n: int = 100,
    balanced: bool = False,
    test_percent: float = 0.25,
    seed: int = 1,
):
    train, test = load_data(test_percent, seed)
    model = train_model(train, model_type, n, seed, balanced)
    score = test_model(model, test)
    return score


simple_lr = test_sklearn_alg("simple_lr", LogisticRegression, balanced=True)
simple_rf = test_sklearn_alg("simple_rf", RandomForestClassifier, seed=2)
simple_lr_unbalanced = test_sklearn_alg(
    "simple_lr_unbalanced", RandomForestClassifier, seed=3
)


@stage([Artifact("max_score")])
def find_max_of_scores(names: list[str], scores: list[float]):
    maximum_val = 0.0
    maximum_name = None
    for i, score in enumerate(scores):
        if score > maximum_val:
            maximum_val = score
            maximum_name = names[i]
    return {"name": maximum_name, "score": maximum_val}


@experiment
def compare_algs(alg_experiments: list[test_sklearn_alg]):
    # ensure they're all using the same data
    # FOOTGUN
    # Ahhh so the problem with this is the fact that this function is even
    # defined and "run" below for compare_all's instantiation, this actively
    # changes the artifacts in the sort of separate simple_lr, simple_rf,
    # etc. definitions, which is probably surprising. I wouldn't want code
    # inside later experiments to modify entirely other experiments.
    # for exp in alg_experiments[1:]:
    #     exp.artifacts["data"].replace(alg_experiments[0].artifacts["data"])

    # what I'd like to be able to do is
    # score_list = [exp.artifacts.score.copy() for exp.alg_experiments]
    # similarly, simple_lr.artifacts.score.copy() +
    # simple_rf.artifacts.score.copy() should return a new artifactfilter, with
    # filterstr {a}+{b} (literal + with the two filterstrings

    score_list = ArtifactList("scores", [exp.outputs.copy() for exp in alg_experiments])

    # actual_training_data = score_list[0].dependencies()[0].dependencies()[0]
    # actual_testing_data = score_list[0].dependencies()[1]

    actual_training_data = score_list.artifacts.training_data[0]
    actual_testing_data = score_list.artifacts.testing_data[0]

    print(score_list.artifacts)

    # TODO: this is super weird though, should probably be better way of getting
    # artifacts from an explicit artifact list?
    for score in score_list.artifacts.score[1:]:
        print(score.context.name, score.previous_context_names)
        score.artifacts.training_data[0].replace(actual_training_data)
        score.artifacts.testing_data[0].replace(actual_testing_data)
        # score.dependencies()[0].dependencies()[0].replace(actual_training_data)
    #     score.dependencies()[1].replace(actual_testing_data)

    # TODO: what I want to be able to do:
    # score_list.training_data.replace(score_list.training_data[0])
    # score_list.testing_data.replace(score_list.testing_data[0])

    # actual_training_data = (
    #     alg_experiments[0].outputs.dependencies()[0].dependencies()[0]
    # )
    # actual_testing_data = alg_experiments[0].outputs.dependencies()[1]
    # # TODO: ah, this doesn't actually work yet because replace doesn't modify
    # # compute stage ins/outs?
    # for exp in alg_experiments[1:]:
    #     exp.outputs.dependencies()[0].dependencies()[0].replace(actual_training_data)
    #     # exp.outputs.dependencies()[0].replace(actual_training_data)
    #     exp.outputs.dependencies()[1].replace(actual_testing_data)
    #
    # score_list = ArtifactList("scores", [exp.outputs for exp in alg_experiments])
    maximum = find_max_of_scores([exp.name for exp in alg_experiments], score_list)
    return maximum


compare_all = compare_algs("compare_all", [simple_lr, simple_rf, simple_lr_unbalanced])


@dataclass
class ModelParameters:
    name: str
    model_type: Callable
    n: int = 100
    balanced: bool = False


# FOOTGUN
# Might be tempting to make larger all encompassing experiments like
# previous cf, where now it's probably better to split up each (what was
# previously a record) into a different experiment...
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


#
# lr_vs_rf = compare_sklearn_algs(
#     "lr_vs_rf",
#     [
#         ModelParameters("simple_lr", balanced=True, model_type=LogisticRegression),
#         ModelParameters("simple_rf", model_type=RandomForestClassifier),
#     ],
#     seed=1,
# )
#
# lr_vs_rf_unbalanced = compare_sklearn_algs(
#     "lr_vs_rf_unablanced",
#     [
#         ModelParameters(
#             "simple_lr_unbalanced", balanced=False, model_type=LogisticRegression
#         ),
#         ModelParameters("simple_rf", model_type=RandomForestClassifier),
#     ],
#     seed=1,
# )

Artifacts.display()


@stage([Artifact("max_score")])
def find_max(scores: list[dict[str, float]]):
    maximum_val = 0.0
    maximum_name = None
    for score in scores:
        for model_name in score:
            if score[model_name] > maximum_val:
                maximum_val = score[model_name]
                maximum_name = model_name
    return {"name": maximum_name, "score": maximum_val}


@experiment
def analyze_experiments(comparison_experiments: list[compare_sklearn_algs]):
    all_scores = ArtifactList(
        "all_scores", [expr.scores for expr in comparison_experiments]
    )
    best_score = find_max(all_scores)

    return best_score


# which_is_best = analyze_experiments("comparison", [lr_vs_rf, lr_vs_rf_unbalanced])
