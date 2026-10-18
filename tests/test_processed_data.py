"""Data-quality tests on the committed star schema in data/processed/.

These run against the exact CSV files that Power Query loads, so a failing test
means the published model would be wrong.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

PRIMARY_KEYS = {
    "DimDate": "Date",
    "DimGeography": "GeographyKey",
    "DimIndicator": "IndicatorKey",
    "DimSeries": "SeriesKey",
}

# Columns that may legitimately be empty, by table. Anything else must be filled.
ALLOWED_EMPTY = {
    "FactObservation": {"Status", "Symbol"},
    "DimIndicator": {"StdErrCode", "StdErrYoYCode", "ReferenceDay"},
    "DimSeries": set(),
    "DimDate": set(),
    "DimGeography": set(),
}

# Statistics Canada status and symbol flags we expect to see, with meaning.
EXPECTED_STATUS = {"": "normal", "E": "use with caution"}
EXPECTED_SYMBOL = {"": "none", "p": "preliminary", "r": "revised"}


def months_between(a: dt.date, b: dt.date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


# ---------------------------------------------------------------- keys and grain

def test_fact_grain_is_unique(fact):
    dupes = fact[fact.duplicated(["Date", "GeographyKey", "IndicatorKey"], keep=False)]
    assert dupes.empty, f"duplicate fact rows:\n{dupes.head()}"
    assert not fact.duplicated(["SeriesKey", "Date"]).any()


@pytest.mark.parametrize("table,key", PRIMARY_KEYS.items())
def test_dimension_keys_are_unique_and_filled(tables, table, key):
    col = tables[table][key]
    assert (col != "").all(), f"{table}.{key} has empty keys"
    assert not col.duplicated().any(), f"{table}.{key} has duplicate keys"


@pytest.mark.parametrize("table,key", PRIMARY_KEYS.items())
def test_fact_foreign_keys_resolve(tables, table, key):
    orphans = set(tables["FactObservation"][key]) - set(tables[table][key])
    assert not orphans, f"FactObservation.{key} values missing from {table}: {sorted(orphans)[:5]}"


def test_each_series_maps_to_one_geography_and_indicator(fact, catalogue):
    pairs = fact.groupby("SeriesKey")[["GeographyKey", "IndicatorKey"]].nunique()
    assert (pairs == 1).all().all()
    expected = catalogue.set_index("VectorId")[["GeographyKey", "IndicatorKey"]].astype(int)
    actual = fact.drop_duplicates("SeriesKey").set_index("SeriesKey")[["GeographyKey", "IndicatorKey"]]
    pd.testing.assert_frame_equal(actual.sort_index(), expected.sort_index(), check_names=False)


# ---------------------------------------------------------------- nulls

@pytest.mark.parametrize("table", list(ALLOWED_EMPTY))
def test_no_unexpected_nulls(tables, table):
    df = tables[table]
    must_fill = [c for c in df.columns if c not in ALLOWED_EMPTY[table]]
    empty = {c: int((df[c] == "").sum()) for c in must_fill if (df[c] == "").any()}
    assert not empty, f"{table} has empty values in required columns: {empty}"


def test_fact_values_are_numeric(tables):
    values = pd.to_numeric(tables["FactObservation"]["Value"], errors="coerce")
    assert values.notna().all()


def test_status_and_symbol_flags_are_known(fact):
    assert set(fact["Status"]) <= set(EXPECTED_STATUS), set(fact["Status"])
    assert set(fact["Symbol"]) <= set(EXPECTED_SYMBOL), set(fact["Symbol"])


def test_caution_flag_is_limited_to_new_housing_land_index(fact_labelled):
    flagged = set(fact_labelled.loc[fact_labelled["Status"] == "E", "IndicatorCode"])
    assert flagged <= {"NHPI_LAND"}, f"unexpected 'use with caution' flags on {flagged}"


# ---------------------------------------------------------------- coverage

def test_every_catalogued_series_is_present(fact, catalogue):
    assert set(fact["SeriesKey"]) == set(catalogue["VectorId"])


def test_documented_gaps_only(fact_labelled):
    """St. John's has no published food or energy CPI; every other pair exists."""
    present = set(zip(fact_labelled["GeographyCode"], fact_labelled["IndicatorCode"]))
    indicators = set(fact_labelled["IndicatorCode"])
    expected_missing = {("SJ", "CPI_FOOD"), ("SJ", "CPI_ENERGY")}
    for geo in ("SJ", "CA", "NL"):
        for ind in indicators:
            if (geo, ind) in expected_missing:
                assert (geo, ind) not in present
            else:
                assert (geo, ind) in present, f"missing {geo} {ind}"


def test_series_start_on_or_before_expected_first_date(fact_labelled, indicator_config):
    expected = indicator_config.set_index("IndicatorCode")["ExpectedFirstDate"]
    first = fact_labelled.groupby(["IndicatorCode", "GeographyCode"])["Date"].min()
    late = {k: v for k, v in first.items() if v > expected[k[0]]}
    assert not late, f"series starting later than expected: {late}"


def test_series_are_current_at_snapshot_time(fact_labelled, manifest):
    fetched = dt.date.fromisoformat(manifest["fetched_at_utc"][:10])
    last = fact_labelled.groupby(["IndicatorCode", "GeographyCode", "Frequency"])["Date"].max()
    stale = {}
    for (ind, geo, freq), d in last.items():
        lag = months_between(dt.date.fromisoformat(d), fetched)
        limit = 4 if freq == "Monthly" else 27
        if lag > limit:
            stale[(ind, geo)] = d
    assert not stale, f"series older than expected at fetch time {fetched}: {stale}"


def test_monthly_series_have_no_gaps(fact_labelled):
    gaps = {}
    for (ind, geo), g in fact_labelled[fact_labelled["Frequency"] == "Monthly"].groupby(["IndicatorCode", "GeographyCode"]):
        dates = sorted(dt.date.fromisoformat(d) for d in g["Date"])
        expected = months_between(dates[0], dates[-1]) + 1
        if len(dates) != expected:
            gaps[(ind, geo)] = (len(dates), expected)
    assert not gaps, f"monthly series with gaps (rows, expected): {gaps}"


def test_annual_series_have_no_gaps(fact_labelled):
    for (ind, geo), g in fact_labelled[fact_labelled["Frequency"] == "Annual"].groupby(["IndicatorCode", "GeographyCode"]):
        years = sorted(int(d[:4]) for d in g["Date"])
        assert years == list(range(years[0], years[-1] + 1)), f"{ind} {geo} has missing years"


def test_dates_align_with_frequency(fact_labelled):
    monthly = fact_labelled[fact_labelled["Frequency"] == "Monthly"]
    assert monthly["Date"].str.endswith("-01").all(), "monthly observations must be keyed to the first of the month"
    annual = fact_labelled[fact_labelled["Frequency"] == "Annual"]
    for _, row in annual.iterrows():
        assert row["Date"][5:] == row["ReferenceDay"], f"annual {row['IndicatorCode']} not keyed to {row['ReferenceDay']}"


def test_dim_series_coverage_matches_fact(tables, fact):
    s = tables["DimSeries"].set_index("SeriesKey")
    cov = fact.groupby("SeriesKey").agg(first=("Date", "min"), last=("Date", "max"), n=("Date", "size"))
    for key, row in cov.iterrows():
        rec = s.loc[str(key)]
        assert (rec["FirstDate"], rec["LastDate"], int(rec["ObservationCount"])) == (row["first"], row["last"], row["n"])


# ---------------------------------------------------------------- units

def test_units_consistent_within_each_indicator(tables, indicator_config):
    series = tables["DimSeries"]
    cfg = indicator_config.set_index("IndicatorCode")
    for ind, g in series.groupby("IndicatorCode"):
        assert g["UnitOfMeasure"].nunique() == 1, f"{ind} mixes units: {set(g['UnitOfMeasure'])}"
        assert g["ScalarFactor"].nunique() == 1, f"{ind} mixes scalar factors"
        assert g["Frequency"].nunique() == 1, f"{ind} mixes frequencies"
        assert g["UnitOfMeasure"].iloc[0] == cfg.loc[ind, "ExpectedUom"]
        assert g["ScalarFactor"].iloc[0] == cfg.loc[ind, "ExpectedScalar"]
        assert g["Frequency"].iloc[0] == cfg.loc[ind, "Frequency"]


PLAUSIBLE_RANGES = {
    # unit label in DimIndicator: (minimum, maximum)
    "Index (2002=100)": (80, 300),
    "Index (December 2016=100)": (80, 250),
    "Percent": (0, 100),
    "Percentage points": (0, 10),
    "Persons (thousands)": (0, 30_000),
    "Persons": (100_000, 60_000_000),
    "Dwelling units": (0, 50_000),
}


def test_values_within_plausible_ranges(fact_labelled):
    units = set(fact_labelled["Unit"])
    assert units <= set(PLAUSIBLE_RANGES), f"no range defined for units {units - set(PLAUSIBLE_RANGES)}"
    for unit, (lo, hi) in PLAUSIBLE_RANGES.items():
        vals = fact_labelled.loc[fact_labelled["Unit"] == unit, "Value"]
        assert vals.between(lo, hi).all(), f"{unit} values outside [{lo}, {hi}]: {vals[~vals.between(lo, hi)].head().tolist()}"


def test_unemployment_rate_is_plausible(fact_labelled):
    ur = fact_labelled.loc[fact_labelled["IndicatorCode"] == "LFS_UR", "Value"]
    assert ur.between(2, 25).all()


def test_dwelling_unit_counts_are_whole_numbers(fact_labelled):
    units = fact_labelled.loc[fact_labelled["Unit"] == "Dwelling units", "Value"]
    assert (units == units.round()).all()


def test_building_permit_components_add_up(fact_labelled):
    bp = fact_labelled[fact_labelled["IndicatorCode"].str.startswith("BP_UNITS")]
    wide = bp.pivot_table(index=["GeographyCode", "Date"], columns="IndicatorCode", values="Value")
    diff = wide["BP_UNITS"] - wide["BP_UNITS_SINGLE"] - wide["BP_UNITS_MULTI"]
    assert (diff.abs() < 0.5).all(), "single + multiple dwelling units must equal the total"


# ---------------------------------------------------------------- calendar

def test_dim_date_is_a_contiguous_daily_calendar(tables, fact):
    dates = pd.to_datetime(tables["DimDate"]["Date"])
    assert dates.is_monotonic_increasing
    assert (dates.diff().dropna() == pd.Timedelta(days=1)).all(), "DimDate must have no missing days"
    assert dates.iloc[0].strftime("%m-%d") == "01-01" and dates.iloc[-1].strftime("%m-%d") == "12-31"
    assert set(fact["Date"]) <= set(tables["DimDate"]["Date"])


def test_dim_date_month_columns_are_consistent(tables):
    d = tables["DimDate"]
    assert (d["MonthStart"] == d["Date"].str[:8] + "01").all()
    assert (d["YearMonth"] == d["Date"].str[:7]).all()
    assert (d["MonthSort"].astype(int) == d["Year"].astype(int) * 100 + d["Month"].astype(int)).all()
    assert (d["IsMonthStart"] == (d["Date"].str[8:] == "01").map({True: "True", False: "False"})).all()
