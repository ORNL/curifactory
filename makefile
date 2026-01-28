# https://madewithml.com/courses/mlops/makefile
SHELL=/usr/bin/env bash
VERSION=$(shell python -c "import curifactory; print(curifactory.__version__)")
MAMBA=micromamba
ENV_NAME=curifactory

.PHONY: help
help: ## display all the make commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: setup
setup:  ## make a micromamba development environment and set it up (VARS: MAMBA, ENV_NAME)
	$(MAMBA) env create -n $(ENV_NAME) -f environment.yml -y
	$(MAMBA) run -n $(ENV_NAME) pip install -r requirements.txt
	$(MAMBA) run -n $(ENV_NAME) pre-commit install
	@echo -e "Environment created, activate with:\n\n$(MAMBA) activate $(ENV_NAME)"

.PHONY: pre-commit
pre-commit: ## run all of the pre-commit checks.
	@pre-commit run --all-files

.PHONY: publish
publish: ## build the package and push to pypi
	@python -m build
	@twine check dist/*
	@twine upload dist/* --skip-existing

.PHONY: apply-docs
apply-docs: ## copy current sphinx documentation into version-specific docs/ folder
	@rm -rf docs/latest
	@echo "Copying documentation to 'docs/latest'..."
	@cp -r sphinx/build/html docs/latest
	@echo "Copying documentation to docs/$(VERSION)"
	@rm -f docs/$(VERSION)
	@cp -r sphinx/build/html docs/$(VERSION)

.PHONY: style
style: ## executes style formatting
	black .
	flake8
	isort .

.PHONY: clean
clean: ## cleans all unnecessary files
	find . -type f -name "*.DS_Store" -ls -delete
	find . | grep -E "(__pycache__|\.pyc|\.pyo)" | xargs rm -rf
	find . | grep -E ".pytest_cache" | xargs rm -rf
	find . | grep -E ".ipynb_checkpoints" | xargs rm -rf


.PHONY: test
test: ## runs unit tests
	pytest


.PHONY: testing-envs
testing-envs: ## create envs for running unit tests in python 3.10-3.14
	micromamba create -n cftest310 python=3.10 -y
	micromamba run -n cftest310 pip install -r requirements.txt

	micromamba create -n cftest311 python=3.11 -y
	micromamba run -n cftest311 pip install -r requirements.txt

	micromamba create -n cftest312 python=3.12 -y
	micromamba run -n cftest312 pip install -r requirements.txt

	micromamba create -n cftest313 python=3.13 -y
	micromamba run -n cftest313 pip install -r requirements.txt

	micromamba create -n cftest314 python=3.14 -y
	micromamba run -n cftest314 pip install -r requirements.txt


.PHONY: test-all
test-all: ## runs unit tests in python 3.10-3.14
	@echo -e "\n################# PYTHON 3.9 ##################\n"
	micromamba run -n cftest39 pytest

	@echo -e "\n################# PYTHON 3.10 ##################\n"
	micromamba run -n cftest310 pytest

	@echo -e "\n################# PYTHON 3.11 ##################\n"
	micromamba run -n cftest311 pytest


.PHONY: paper-draft
paper-draft: ## generate JOSS paper draft
	docker run --rm \
		--volume ./paper:/data \
		--user $(id -u):$(id -g) \
		--env JOURNAL=joss \
		openjournals/inara
