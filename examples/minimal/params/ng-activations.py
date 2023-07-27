from experiments.newsgroups import Params


def get_params():
    params = []

    activations = ["logistic", "tanh", "relu"]
    for activation in activations:
        params.append(Params(name=f"act-{activation}", activation=activation))

    return params
