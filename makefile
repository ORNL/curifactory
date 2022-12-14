# https://madewithml.com/courses/mlops/makefile
SHELL = /bin/bash

.PHONY: help
help:
	@echo "Commands:"
	@echo "style   : executes style formatting."
	@echo "clean   : cleans all unnecessary files."
	@echo "test    : runs unit tests."

.PHONY: style
style:
	black .
	flake8
	isort .

.PHONY: clean
clean:
	find . -type f -name "*.DS_Store" -ls -delete
	find . | grep -E "(__pycache__|\.pyc|\.pyo)" | xargs rm -rf
	find . | grep -E ".pytest_cache" | xargs rm -rf
	find . | grep -E ".ipynb_checkpoints" | xargs rm -rf

.PHONY: test
test:
	pytest
