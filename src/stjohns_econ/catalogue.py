"""Load and cross-check the configuration catalogues in config/."""

from __future__ import annotations

import pandas as pd

from .paths import CONFIG_DIR


def _read(name: str) -> pd.DataFrame:
    # Read everything as text first so codes such as "07-01" are never coerced.
    return pd.read_csv(CONFIG_DIR / name, dtype=str, keep_default_na=False)


def load_geographies() -> pd.DataFrame:
    df = _read("geographies.csv")
    for col in ("GeographyKey", "SortOrder"):
        df[col] = df[col].astype(int)
    return df


def load_indicators() -> pd.DataFrame:
    df = _read("indicators.csv")
    for col in ("IndicatorKey", "Decimals", "SortOrder"):
        df[col] = df[col].astype(int)
    return df


def load_series() -> pd.DataFrame:
    """Series catalogue joined to geography and indicator keys.

    Raises ValueError if the catalogue references unknown codes or repeats a
    vector or a (geography, indicator) pair.
    """
    series = _read("series.csv")
    series["VectorId"] = series["VectorId"].astype(int)
    series["ProductId"] = series["ProductId"].astype(int)
    geos = load_geographies()
    inds = load_indicators()

    problems = []
    unknown_geo = set(series["GeographyCode"]) - set(geos["GeographyCode"])
    unknown_ind = set(series["IndicatorCode"]) - set(inds["IndicatorCode"])
    if unknown_geo:
        problems.append(f"unknown geography codes: {sorted(unknown_geo)}")
    if unknown_ind:
        problems.append(f"unknown indicator codes: {sorted(unknown_ind)}")
    if series["VectorId"].duplicated().any():
        problems.append("duplicate vector IDs in config/series.csv")
    if series.duplicated(["GeographyCode", "IndicatorCode"]).any():
        problems.append("duplicate (GeographyCode, IndicatorCode) pairs in config/series.csv")
    for _, row in series.iterrows():
        expected_pid = int(row["TableId"].replace("-", "")[:8])
        if expected_pid != row["ProductId"]:
            problems.append(f"v{row['VectorId']}: TableId {row['TableId']} does not match ProductId {row['ProductId']}")
    if problems:
        raise ValueError("Invalid series catalogue: " + "; ".join(problems))

    series = series.merge(geos[["GeographyCode", "GeographyKey"]], on="GeographyCode", how="left")
    series = series.merge(inds[["IndicatorCode", "IndicatorKey"]], on="IndicatorCode", how="left")
    return series
