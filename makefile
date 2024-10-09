SHELL = /usr/bin/env bash
VERSION = $(shell python -c "import curifactory as cf; print(cf.__version__)")

.PHONY: help
help: ## display all the make commands.
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: pre-commit
pre-commit: ## run all of the pre-commit checks.
	@pre-commit run --all-files

.PHONY: publish
publish: ## build the package and push to pypi.
	@python -m build
	@twine check dist/*
	@twine upload dist/* --skip-existing

.PHONY: apply-docs
apply-docs: ## copy current built sphinx documentation into version-specific docs/folder.
	@rm -rf docs/latest
	@echo "Copying documentation to 'docs/latest'..."
	@cp -r sphinx/build/html docs/latest
	@echo "Copying documentation to docs/$(VERSION)"
	@rm -f docs/$(VERSION)
	@cp -r sphinx/build/html docs/$(VERSION)

.PHONY: style
style: ## run autofixers and linters.
	black .
	flake8
	isort .

.PHONY: clean
clean: ## remove auto-generated cruft files.
	find . -type f -name "*.DS_Store" -ls -delete
	find . | grep -E "(__pycache__|\.pyc|\.pyo)" | xargs rm -rf
	find . | grep -E ".pytest_cache" | xargs rm -rf
	find . | grep -E ".ipynb_checkpoints" | xargs rm -rf


.PHONY: test
test: ## run unit tests.
	pytest


.PHONY: testing-envs
testing-envs: ## generate micromamba environments for multiple python versions.
	micromamba create -n cftest39 python=3.9 -y
	micromamba run -n cftest39 pip install -r requirements.txt

	micromamba create -n cftest310 python=3.10 -y
	micromamba run -n cftest310 pip install -r requirements.txt

	micromamba create -n cftest311 python=3.11 -y
	micromamba run -n cftest311 pip install -r requirements.txt


.PHONY: test-all
test-all: ## run tests in multiple python version environments.
	@echo -e "\n################# PYTHON 3.9 ##################\n"
	micromamba run -n cftest39 pytest

	@echo -e "\n################# PYTHON 3.10 ##################\n"
	micromamba run -n cftest310 pytest

	@echo -e "\n################# PYTHON 3.11 ##################\n"
	micromamba run -n cftest311 pytest


.PHONY: paper-draft
paper-draft: ## build a draft version of the joss paper
	docker run --rm \
		--volume ./paper:/data \
		--user $(id -u):$(id -g) \
		--env JOURNAL=joss \
		openjournals/inara
