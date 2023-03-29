# https://madewithml.com/courses/mlops/makefile
SHELL = /bin/bash
VERSION := $(shell python -c "import curifactory as cf; print(cf.__version__)")

.PHONY: help
help:
	@echo "Commands:"
	@echo "publish     : build the package and bush to pypi."
	@echo "pre-commit  : run all of the pre-commit checks."
	@echo "apply-docs  : copy current sphinx documentation into version-specific docs/ folder"
	@echo "style       : executes style formatting."
	@echo "clean       : cleans all unnecessary files."
	@echo "test        : runs unit tests."


.PHONY: pre-commit
pre-commit:
	@pre-commit run --all-files

.PHONY: publish
publish:
	@python -m build
	@twine check dist/*
	@twine upload dist/* --skip-existing

.PHONY: apply-docs
apply-docs:
	@rm -rf docs/latest
	@echo "Copying documentation to 'docs/latest'..."
	@cp -r sphinx/build/html docs/latest
	@echo "Copying documentation to docs/$(VERSION)"
	@rm -f docs/$(VERSION)
	@cp -r sphinx/build/html docs/$(VERSION)

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
