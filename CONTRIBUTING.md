# Contributing to Curifactory

Outside help to improving Curifactory is always welcome!

If you find any bugs while using Curifactory, or believe there's a feature that would prove useful, feel free to submit an appropriate [issue](https://github.com/ORNL/curifactory/issues/new/choose).

If you have a question, double check that it's not answered in our [documentation](https://ornl.github.io/curifactory/latest/index.html), and if not feel free to email the developers at curifactory-help@ornl.gov.


## Submitting a PR

If you have added a useful feature or fixed a bug, open a new pull request with
the changes.  When submitting a pull request, please describe what the pull
request is addressing and briefly list any significant changes made. If it's in
regards to a specific issue, please include the issue number. Please check and
follow the formatting conventions below!


## Getting Started

First, create a fork of the repository and clone it onto your development machine

It is recommended to do development within a conda environment, so run

```bash
conda create -n curifactory python python-graphviz
```

(`python-graphviz` is recommended to make experiment graphs show up in output reports.)

All development dependencies are contained in the project root `requirements.txt`, so intsall those with

```bash
pip install -r requirements.txt
```

We use [pre-commit](https://pre-commit.com/) extensively to help keep the repository clean and using consistent formatting conventions (formatting is done primarily with [black](https://github.com/psf/black), [flake8](https://github.com/PyCQA/flake8), and [isort](https://github.com/PyCQA/isort)). A PR that doesn't pass the pre-commit CI pipeline won't get merged. To run the checks/formatters locally, initialize pre-commit with

```bash
pre-commit init
```

From that point, any time you commit, it will run all of the checks and formatters. Note that when a formatter changes any file, it marks it as a "failure", but a subsequent `git commit` should pass that check.

Use the makefile to run various commands without needing to commit first:

* `make style` - runs the linters and autoformatters.
* `make pre-commit` - runs all pre-commit hooks.
* `make test` - runs pytests.
