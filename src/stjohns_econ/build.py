"""Build step: validate the raw WDS snapshot and write the star schema as CSV.

Outputs in data/processed/:
  FactObservation.csv  one row per (Date, GeographyKey, IndicatorKey)
  DimDate.csv          daily calendar covering full years of the fact dates
  DimGeography.csv     St. John's (CMA), Canada, Newfoundland and Labrador
  DimIndicator.csv     indicator definitions, units, formats and behaviour flags
  DimSeries.csv        lineage: one row per Statistics Canada vector
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

from .catalogue import load_geographies, load_indicators, load_series
from .paths import PROCESSED_DIR, RAW_DIR, START_DATE

FREQUENCY_CODES = {"Monthly": 6, "Quarterly": 9, "Annual": 12}
CONFIG_ONLY_INDICATOR_COLUMNS = ["ExpectedUom", "ExpectedScalar", "ExpectedFirstDate"]


class BuildError(RuntimeError):
    """Raised when the raw snapshot does not match the catalogue or fails a check."""


def _load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _code_maps(code_sets: dict) -> dict[str, dict]:
    return {
        "uom": {int(u["memberUomCode"]): u["memberUomEn"] for u in code_sets["uom"]},
        "scalar": {int(s["scalarFactorCode"]): s["scalarFactorDescEn"] for s in code_sets["scalar"]},
        "frequency": {int(f["frequencyCode"]): f["frequencyDescEn"] for f in code_sets["frequency"]},
        "status": {int(s["statusCode"]): (s["statusRepresentationEn"] or "") for s in code_sets["status"]},
        "symbol": {int(s["symbolCode"]): (s["symbolRepresentationEn"] or "") for s in code_sets["symbol"]},
    }


def validate_series_info(series: pd.DataFrame, indicators: pd.DataFrame, info: list[dict], codes: dict) -> list[str]:
    """Check every catalogued vector against the metadata the WDS returned."""
    problems: list[str] = []
    by_vector = {int(o["vectorId"]): o for o in info}
    ind = indicators.set_index("IndicatorCode")
    for _, s in series.iterrows():
        v = int(s["VectorId"])
        o = by_vector.get(v)
        if o is None:
            problems.append(f"v{v}: no series metadata returned")
            continue
        expected = ind.loc[s["IndicatorCode"]]
        if int(o["productId"]) != int(s["ProductId"]):
            problems.append(f"v{v}: productId {o['productId']} != catalogue {s['ProductId']}")
        if o["coordinate"] != s["Coordinate"]:
            problems.append(f"v{v}: coordinate {o['coordinate']} != catalogue {s['Coordinate']}")
        if int(o["frequencyCode"]) != FREQUENCY_CODES[expected["Frequency"]]:
            problems.append(f"v{v}: frequency {codes['frequency'].get(int(o['frequencyCode']))} != {expected['Frequency']}")
        uom = codes["uom"].get(int(o["memberUomCode"]))
        if uom != expected["ExpectedUom"]:
            problems.append(f"v{v}: unit '{uom}' != expected '{expected['ExpectedUom']}' for {s['IndicatorCode']}")
        scalar = codes["scalar"].get(int(o["scalarFactorCode"]))
        if scalar != expected["ExpectedScalar"]:
            problems.append(f"v{v}: scalar '{scalar}' != expected '{expected['ExpectedScalar']}'")
        if int(o.get("terminated") or 0) != 0:
            problems.append(f"v{v}: series is terminated at the source")
    return problems


def tidy_observations(series: pd.DataFrame, indicators: pd.DataFrame, data: list[dict], codes: dict,
                      start: str = START_DATE) -> tuple[pd.DataFrame, list[str]]:
    """Flatten WDS data points into one row per vector and reference period.

    Points without a value (suppressed or not available) are dropped and
    reported in the returned notes. Annual population estimates, published by
    Statistics Canada with a January 1 reference period, are keyed to July 1,
    the date the estimate refers to.
    """
    notes: list[str] = []
    ref_day = indicators.set_index("IndicatorCode")["ReferenceDay"].to_dict()
    cat = series.set_index("VectorId")
    rows = []
    for obj in data:
        v = int(obj["vectorId"])
        if v not in cat.index:
            continue
        s = cat.loc[v]
        dropped = 0
        for p in obj["vectorDataPoint"]:
            if p["value"] is None:
                dropped += 1
                continue
            ref = dt.date.fromisoformat(p["refPer"])
            if ref.isoformat() < start:
                continue
            day = ref_day[s["IndicatorCode"]]
            if day:
                month, dom = (int(x) for x in day.split("-"))
                ref = ref.replace(month=month, day=dom)
            decimals = int(p["decimals"])
            rows.append({
                "Date": ref.isoformat(),
                "GeographyKey": int(s["GeographyKey"]),
                "IndicatorKey": int(s["IndicatorKey"]),
                "SeriesKey": v,
                "Value": round(float(p["value"]), decimals),
                "Status": codes["status"].get(int(p["statusCode"]), "?"),
                "Symbol": codes["symbol"].get(int(p["symbolCode"]), "?"),
                "ReleaseDate": p["releaseTime"][:10],
            })
        if dropped:
            notes.append(f"v{v}: dropped {dropped} data point(s) without a value")
    obs = pd.DataFrame(rows)
    return obs.sort_values(["IndicatorKey", "GeographyKey", "Date"]).reset_index(drop=True), notes


def build_dim_date(fact_dates: pd.Series) -> pd.DataFrame:
    first = dt.date(int(fact_dates.min()[:4]), 1, 1)
    last = dt.date(int(fact_dates.max()[:4]), 12, 31)
    days = pd.date_range(first, last, freq="D")
    base_year, base_month = first.year, first.month
    df = pd.DataFrame({"Date": days})
    df["Year"] = df["Date"].dt.year
    df["Quarter"] = df["Date"].dt.quarter
    df["QuarterLabel"] = "Q" + df["Quarter"].astype(str)
    df["YearQuarter"] = df["Year"].astype(str) + " Q" + df["Quarter"].astype(str)
    df["Month"] = df["Date"].dt.month
    df["MonthName"] = df["Date"].dt.strftime("%B")
    df["MonthShort"] = df["Date"].dt.strftime("%b")
    df["MonthStart"] = df["Date"].dt.to_period("M").dt.to_timestamp()
    df["MonthLabel"] = df["MonthShort"] + " " + df["Year"].astype(str)
    df["YearMonth"] = df["Date"].dt.strftime("%Y-%m")
    df["MonthSort"] = df["Year"] * 100 + df["Month"]
    df["MonthIndex"] = (df["Year"] - base_year) * 12 + (df["Month"] - base_month)
    df["IsMonthStart"] = df["Date"].dt.day == 1
    for col in ("Date", "MonthStart"):
        df[col] = df[col].dt.strftime("%Y-%m-%d")
    return df


def build_dim_series(series: pd.DataFrame, info: list[dict], cubes: list[dict], codes: dict,
                     fact: pd.DataFrame, geographies: pd.DataFrame) -> pd.DataFrame:
    info_by_v = {int(o["vectorId"]): o for o in info}
    cube_by_pid = {int(c["productId"]): c for c in cubes}
    coverage = fact.groupby("SeriesKey").agg(
        FirstDate=("Date", "min"), LastDate=("Date", "max"),
        ObservationCount=("Date", "size"), LatestReleaseDate=("ReleaseDate", "max"),
    )
    geo_names = geographies.set_index("GeographyCode")["GeographyName"].to_dict()
    rows = []
    for _, s in series.sort_values(["IndicatorKey", "GeographyKey"]).iterrows():
        v, pid = int(s["VectorId"]), int(s["ProductId"])
        o, cube = info_by_v[v], cube_by_pid[pid]
        geo_member_id = int(s["Coordinate"].split(".")[0])
        geo_dim = next(d for d in cube["dimension"] if d["dimensionPositionId"] == 1)
        geo_member = next(m for m in geo_dim["member"] if m["memberId"] == geo_member_id)
        cov = coverage.loc[v]
        rows.append({
            "SeriesKey": v,
            "VectorLabel": f"v{v}",
            "TableId": s["TableId"],
            "TableTitle": cube["cubeTitleEn"],
            "TableUrl": f"https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid={pid}01",
            "TableDoi": f"https://doi.org/10.25318/{pid}01-eng",
            "Coordinate": s["Coordinate"],
            "SourceSeriesTitle": o["SeriesTitleEn"],
            "SourceGeography": geo_member["memberNameEn"],
            "SourceGeographyCode": geo_member.get("classificationCode") or "",
            "SourceGeographyVintage": geo_member.get("vintage") or "",
            "GeographyCode": s["GeographyCode"],
            "GeographyName": geo_names[s["GeographyCode"]],
            "IndicatorCode": s["IndicatorCode"],
            "UnitOfMeasure": codes["uom"][int(o["memberUomCode"])],
            "ScalarFactor": codes["scalar"][int(o["scalarFactorCode"])],
            "Frequency": codes["frequency"][int(o["frequencyCode"])],
            "FirstDate": cov["FirstDate"],
            "LastDate": cov["LastDate"],
            "ObservationCount": int(cov["ObservationCount"]),
            "LatestReleaseDate": cov["LatestReleaseDate"],
            "TableReleaseDate": (cube.get("releaseTime") or "")[:10],
        })
    return pd.DataFrame(rows)


def check_model(tables: dict[str, pd.DataFrame]) -> list[str]:
    """Fail-fast integrity checks run at the end of every build."""
    problems: list[str] = []
    fact = tables["FactObservation"]
    keys = {"DimDate": "Date", "DimGeography": "GeographyKey", "DimIndicator": "IndicatorKey", "DimSeries": "SeriesKey"}
    for dim, key in keys.items():
        if tables[dim][key].duplicated().any():
            problems.append(f"{dim}.{key} is not unique")
        orphans = set(fact[key]) - set(tables[dim][key])
        if orphans:
            problems.append(f"FactObservation.{key} has {len(orphans)} value(s) missing from {dim}")
    if fact.duplicated(["Date", "GeographyKey", "IndicatorKey"]).any():
        problems.append("FactObservation has duplicate (Date, GeographyKey, IndicatorKey) rows")
    required = ["Date", "GeographyKey", "IndicatorKey", "SeriesKey", "Value", "ReleaseDate"]
    if fact[required].isna().any().any():
        problems.append("FactObservation has nulls in required columns")
    return problems


def write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, encoding="utf-8", lineterminator="\n", float_format="%.10g")


def run_build(raw_dir: Path = RAW_DIR, out_dir: Path = PROCESSED_DIR) -> dict:
    series = load_series()
    indicators = load_indicators()
    geographies = load_geographies()
    info = _load_json(raw_dir / "series_info.json")
    cubes = _load_json(raw_dir / "cube_metadata.json")
    codes = _code_maps(_load_json(raw_dir / "code_sets.json"))
    data = _load_json(raw_dir / "vector_data.json")

    problems = validate_series_info(series, indicators, info, codes)
    if problems:
        raise BuildError("Raw snapshot does not match the catalogue:\n  " + "\n  ".join(problems))

    fact, notes = tidy_observations(series, indicators, data, codes)
    missing = set(series["VectorId"]) - set(fact["SeriesKey"])
    if missing:
        raise BuildError(f"No usable observations for vectors: {sorted(missing)}")

    tables = {
        "FactObservation": fact,
        "DimDate": build_dim_date(fact["Date"]),
        "DimGeography": geographies,
        "DimIndicator": indicators.drop(columns=CONFIG_ONLY_INDICATOR_COLUMNS),
        "DimSeries": build_dim_series(series, info, cubes, codes, fact, geographies),
    }
    problems = check_model(tables)
    if problems:
        raise BuildError("Model checks failed:\n  " + "\n  ".join(problems))

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        write_csv(df, out_dir / f"{name}.csv")
    flagged = fact[fact["Status"] != ""].groupby("IndicatorKey").size()
    if not flagged.empty:
        names = indicators.set_index("IndicatorKey")["IndicatorCode"]
        notes.append("status flags kept on " + ", ".join(f"{names[k]} ({n} rows)" for k, n in flagged.items()))
    return {"rows": {name: len(df) for name, df in tables.items()}, "notes": notes}
