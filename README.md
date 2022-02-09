# Curifactory

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![PyPI version](https://badge.fury.io/py/curifactory.svg)](https://badge.fury.io/py/curifactory)

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

## Documentation

The documentation for the latest version of Curifactory can be found at:
[https://ornl.github.io/curifactory/latest/index.html](https://ornl.github.io/curifactory/latest/index.html).

## Examples

Several small example projects can be found in the `examples` folder.
`examples/notebook-based` includes notebooks demonstrating usage of curifactory
solely in Jupyter. `examples/minimal` shows a basic single-file experiment
script.


## Citation

Please see the following DOI if citing this project:
[10.11578/dc.20220208.1](https://doi.org/10.11578/dc.20220208.1)
