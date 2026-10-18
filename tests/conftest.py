"""Shared fixtures: the committed processed CSVs, catalogue and fetch manifest."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from stjohns_econ.catalogue import load_indicators, load_series
from stjohns_econ.paths import PROCESSED_DIR, RAW_DIR

TABLES = ["FactObservation", "DimDate", "DimGeography", "DimIndicator", "DimSeries"]


def read_processed(name: str) -> pd.DataFrame:
    # Read as text so that tests see exactly what Power Query will see.
    return pd.read_csv(PROCESSED_DIR / f"{name}.csv", dtype=str, keep_default_na=False)


@pytest.fixture(scope="session")
def tables() -> dict[str, pd.DataFrame]:
    return {name: read_processed(name) for name in TABLES}


@pytest.fixture(scope="session")
def fact(tables) -> pd.DataFrame:
    df = tables["FactObservation"].copy()
    df["Value"] = df["Value"].astype(float)
    for col in ("GeographyKey", "IndicatorKey", "SeriesKey"):
        df[col] = df[col].astype(int)
    return df


@pytest.fixture(scope="session")
def fact_labelled(fact, tables) -> pd.DataFrame:
    ind = tables["DimIndicator"][["IndicatorKey", "IndicatorCode", "Frequency", "Unit", "ReferenceDay"]].copy()
    ind["IndicatorKey"] = ind["IndicatorKey"].astype(int)
    geo = tables["DimGeography"][["GeographyKey", "GeographyCode"]].copy()
    geo["GeographyKey"] = geo["GeographyKey"].astype(int)
    return fact.merge(ind, on="IndicatorKey").merge(geo, on="GeographyKey")


@pytest.fixture(scope="session")
def catalogue() -> pd.DataFrame:
    return load_series()


@pytest.fixture(scope="session")
def indicator_config() -> pd.DataFrame:
    return load_indicators()


@pytest.fixture(scope="session")
def manifest() -> dict:
    with open(RAW_DIR / "manifest.json", encoding="utf-8") as f:
        return json.load(f)
