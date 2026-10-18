# Convenience targets. Each one is a thin wrapper around a documented command.
PY := .venv/bin/python

.PHONY: setup fetch build test insights diagrams refresh

setup:            ## create the virtual environment and install pinned dependencies
	python3 -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt

fetch:            ## download the catalogued series from Statistics Canada (about 6 requests)
	$(PY) -m stjohns_econ fetch

build:            ## validate the raw snapshot and rebuild data/processed/*.csv
	$(PY) -m stjohns_econ build

test:             ## run the data-quality and unit tests
	$(PY) -m pytest

insights:         ## recompute the headline findings (docs/findings.md and README block)
	$(PY) -m stjohns_econ insights

diagrams:         ## regenerate the SVG model diagram and wireframes
	$(PY) -m stjohns_econ diagrams

refresh: fetch build test insights   ## full monthly refresh
