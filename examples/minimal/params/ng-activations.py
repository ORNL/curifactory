from experiments.newsgroups import Args


def get_params():
    args = []

    activations = ["logistic", "tanh", "relu"]
    for activation in activations:
        args.append(Args(name=f"act-{activation}", activation=activation))

    return args
