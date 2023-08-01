# Curifactory

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![PyPI version](https://badge.fury.io/py/curifactory.svg)](https://badge.fury.io/py/curifactory)
[![Conda Version](https://img.shields.io/conda/vn/conda-forge/curifactory.svg)](https://anaconda.org/conda-forge/curifactory)
[![status](https://joss.theoj.org/papers/e6ace365c4f632391a289ddea5bbfd1c/status.svg)](https://joss.theoj.org/papers/e6ace365c4f632391a289ddea5bbfd1c)
[![tests](https://github.com/ORNL/curifactory/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/ORNL/curifactory/actions/workflows/tests.yml)
[![Python versions](https://img.shields.io/pypi/pyversions/curifactory.svg)](https://github.com/ORNL/curifactory)
[![License](https://img.shields.io/pypi/l/curifactory)](https://github.com/ORNL/curifactory/blob/main/LICENSE)

Curifactory is a library and CLI tool designed to help organize and manage
research experiments in python.

![screenshot flow](https://raw.githubusercontent.com/ORNL/curifactory/main/sphinx/source/images/diagram.png)

Experiment management must fulfill several tasks, including experiment orchestration,
parameterization, caching, reproducibility, reporting, and parallelization.
Existing projects such as MLFlow, MetaFlow, Luigi, and Pachyderm
support these tasks in several different ways and to various degrees.
Curifactory provides a different opinion, with a heavier focus on supporting general
research experiment workflows for individuals or small teams working primarily
in python.

You can read more about these design principles in our paper in the [SciPy 2022
proceedings](https://conference.scipy.org/proceedings/scipy2022/nathan_martindale.html).

## Features

* Adds a CLI layer on top of your codebase, a single entrypoint for running experiments
* Automatic caching of intermediate data and lazy loading of stored objects
* Jupyter notebook output for further exploration of an experiment run
* Docker container output with copy of codebase, conda environment, full experiment run cache, and jupyter run notebook
* HTML report output from each run with graphviz-rendered diagram of experiment
* Easily report plots and values to HTML report
* Configuration files are python scripts, allowing programmatic definition, parameter composition, and parameter inheritance
* Output logs from every run
* Run experiments directly from CLI or other python code, notebooks, etc.


## Installation

```python
pip install curifactory
```

Graphviz is required for certain features and can be installed through conda
via:

```python
conda install python-graphviz
```

### Tab completion

For tab-completion in bash/zsh, install the `argcomplete` package (if using curifactory inside
a conda environment, you'll need to install this in your system python.)

```python
pip install argcomplete
```

To enable, you can either use argcomplete's global hook `activate-global-python-argcomplete`, which
will enable tab complete on all argcomplete-enabled python packages (e.g. pytest), or you can add
`eval "$(register-python-argcomplete experiment)"` to your shell's rc file. Curifactory can add
this line for you automatically with:

```bash
curifactory completion [--bash|--zsh]  # use the shell flag appropriate
```

Once enabled, the `experiment` command will provide tab complete for experiment names, parameter names, and flags.

## Documentation

The documentation for the latest version of Curifactory can be found at:
[https://ornl.github.io/curifactory/latest/index.html](https://ornl.github.io/curifactory/latest/index.html).


## Examples

Several small example can be found in the `examples` folder.
`examples/notebooks` includes walkthroughs demonstrating usage of curifactory
solely in Jupyter.


## Citation

Please see the following DOI if citing this project:
[10.11578/dc.20220208.1](https://doi.org/10.11578/dc.20220208.1)


## Similar Projects

Curifactory is one tool and one opinion among many, other projects that have similar goals and/or approaches:

* [Kedro](https://github.com/kedro-org/kedro)
* [Tango](https://github.com/allenai/tango)
* [Sacred](https://github.com/IDSIA/sacred)
* [MLFlow](https://github.com/mlflow/mlflow)
