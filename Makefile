.DEFAULT_GOAL := all
UPGRADE_ARGS ?= --upgrade
isort = isort opennem tests
black = black opennem tests
ruff = ruff opennem tests
pyupgrade = pyupgrade --exit-zero-even-if-changed --py311-plus opennem/**/*.py tests/**/*.py
pyright = pyright -v $(poetry env info -p) opennem

.PHONY: test
test:
	pytest tests -v

.PHONY: format
format:
	$(pyupgrade)
	$(isort)
	$(black)
	$(ruff) --fix --exit-zero

.PHONY: pyright
pyright:
	$(pyright)

.PHONY: install
install:
	pip install -r ./requirements.txt

.PHONY: build
build:
	pip install wheel
	python setup.py sdist bdist_wheel

.PHONY: bump-dev
bump-dev:
	bumpver update --tag-num

.PHONY: requirements
requirements:
	poetry export --format requirements.txt -E postgres --without-hashes > requirements.txt
	poetry export --with dev --format requirements.txt --without-hashes > requirements_dev.txt
	git add requirements.txt requirements_dev.txt

pyclean:
	find . -type f -name '*.py[co]' -delete -o -type d -name __pycache__ -delete

cleandist:
	rm -rf build

codecov:
	pytest --cov=./opennem

release: format requirements bump-dev
