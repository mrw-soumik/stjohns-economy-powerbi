"""Unit tests for the ETL functions, using small synthetic WDS payloads."""

from __future__ import annotations

import pandas as pd
import pytest

from stjohns_econ.build import build_dim_date, check_model, tidy_observations, validate_series_info
from stjohns_econ.fetch import trim_cube_metadata
from stjohns_econ.wds import WdsClient

CODES = {
    "uom": {17: "2002=100", 249: "Persons", 239: "Percent"},
    "scalar": {0: "units", 3: "thousands"},
    "frequency": {6: "Monthly", 12: "Annual"},
    "status": {0: "", 1: "..", 7: "E"},
    "symbol": {0: "", 1: "p", 3: "r"},
}


@pytest.fixture()
def series():
    return pd.DataFrame([
        {"VectorId": 1, "ProductId": 18100004, "TableId": "18-10-0004-01", "Coordinate": "4.2.0.0.0.0.0.0.0.0",
         "GeographyCode": "SJ", "IndicatorCode": "CPI_ALL", "GeographyKey": 1, "IndicatorKey": 1},
        {"VectorId": 2, "ProductId": 17100148, "TableId": "17-10-0148-01", "Coordinate": "4.1.1.0.0.0.0.0.0.0",
         "GeographyCode": "SJ", "IndicatorCode": "POP", "GeographyKey": 1, "IndicatorKey": 16},
    ])


@pytest.fixture()
def indicators():
    return pd.DataFrame([
        {"IndicatorCode": "CPI_ALL", "Frequency": "Monthly", "ExpectedUom": "2002=100", "ExpectedScalar": "units", "ReferenceDay": ""},
        {"IndicatorCode": "POP", "Frequency": "Annual", "ExpectedUom": "Persons", "ExpectedScalar": "units", "ReferenceDay": "07-01"},
    ])


def point(ref, value, decimals=1, status=0, symbol=0, release="2026-09-14T08:30"):
    return {"refPer": ref, "value": value, "decimals": decimals, "statusCode": status,
            "symbolCode": symbol, "releaseTime": release}


def test_tidy_drops_points_without_value_and_reports_them(series, indicators):
    data = [{"vectorId": 1, "vectorDataPoint": [point("2026-07-01", 165.0), point("2026-08-01", None, status=1)]}]
    obs, notes = tidy_observations(series, indicators, data, CODES, start="2016-01-01")
    assert obs["Date"].tolist() == ["2026-07-01"]
    assert notes == ["v1: dropped 1 data point(s) without a value"]


def test_tidy_keys_annual_population_to_july_first(series, indicators):
    data = [{"vectorId": 2, "vectorDataPoint": [point("2025-01-01", 243478, decimals=0)]}]
    obs, _ = tidy_observations(series, indicators, data, CODES, start="2016-01-01")
    assert obs.loc[0, "Date"] == "2025-07-01"
    assert obs.loc[0, "Value"] == 243478


def test_tidy_rounds_to_published_decimals_and_maps_flags(series, indicators):
    data = [{"vectorId": 1, "vectorDataPoint": [point("2026-08-01", 164.29999999, status=7, symbol=3)]}]
    obs, _ = tidy_observations(series, indicators, data, CODES, start="2016-01-01")
    row = obs.iloc[0]
    assert row["Value"] == 164.3
    assert (row["Status"], row["Symbol"], row["ReleaseDate"]) == ("E", "r", "2026-09-14")


def test_tidy_ignores_periods_before_start(series, indicators):
    data = [{"vectorId": 1, "vectorDataPoint": [point("2015-12-01", 127.0), point("2016-01-01", 128.9)]}]
    obs, _ = tidy_observations(series, indicators, data, CODES, start="2016-01-01")
    assert obs["Date"].tolist() == ["2016-01-01"]


def test_validate_series_info_accepts_matching_metadata(series, indicators):
    info = [
        {"vectorId": 1, "productId": 18100004, "coordinate": "4.2.0.0.0.0.0.0.0.0", "frequencyCode": 6,
         "memberUomCode": 17, "scalarFactorCode": 0, "terminated": 0},
        {"vectorId": 2, "productId": 17100148, "coordinate": "4.1.1.0.0.0.0.0.0.0", "frequencyCode": 12,
         "memberUomCode": 249, "scalarFactorCode": 0, "terminated": 0},
    ]
    assert validate_series_info(series, indicators, info, CODES) == []


def test_validate_series_info_flags_unit_coordinate_and_missing_vectors(series, indicators):
    info = [{"vectorId": 1, "productId": 18100004, "coordinate": "4.3.0.0.0.0.0.0.0.0", "frequencyCode": 6,
             "memberUomCode": 239, "scalarFactorCode": 3, "terminated": 1}]
    problems = validate_series_info(series, indicators, info, CODES)
    text = " | ".join(problems)
    assert "coordinate" in text and "unit 'Percent'" in text and "scalar 'thousands'" in text
    assert "terminated" in text and "v2: no series metadata returned" in text


def test_build_dim_date_covers_full_years():
    dim = build_dim_date(pd.Series(["2016-01-01", "2017-07-01"]))
    assert dim["Date"].iloc[0] == "2016-01-01" and dim["Date"].iloc[-1] == "2017-12-31"
    assert len(dim) == 366 + 365
    jul = dim[dim["Date"] == "2017-07-15"].iloc[0]
    assert (jul["MonthStart"], jul["MonthLabel"], jul["MonthIndex"], jul["YearQuarter"]) == ("2017-07-01", "Jul 2017", 18, "2017 Q3")


def test_check_model_reports_orphans_and_duplicates():
    fact = pd.DataFrame({"Date": ["2026-01-01", "2026-01-01"], "GeographyKey": [1, 1], "IndicatorKey": [1, 1],
                         "SeriesKey": [10, 10], "Value": [1.0, 2.0], "ReleaseDate": ["2026-02-01"] * 2})
    tables = {
        "FactObservation": fact,
        "DimDate": pd.DataFrame({"Date": ["2026-01-01"]}),
        "DimGeography": pd.DataFrame({"GeographyKey": [2]}),
        "DimIndicator": pd.DataFrame({"IndicatorKey": [1]}),
        "DimSeries": pd.DataFrame({"SeriesKey": [10]}),
    }
    problems = check_model(tables)
    assert any("GeographyKey" in p for p in problems)
    assert any("duplicate" in p for p in problems)


def test_trim_cube_metadata_keeps_only_used_members():
    cube = {"productId": "18100004", "cubeTitleEn": "CPI", "dimension": [
        {"dimensionPositionId": 1, "dimensionNameEn": "Geography",
         "member": [{"memberId": 2, "memberNameEn": "Canada"}, {"memberId": 4, "memberNameEn": "St. John's"},
                    {"memberId": 5, "memberNameEn": "Prince Edward Island"}]},
        {"dimensionPositionId": 2, "dimensionNameEn": "Products",
         "member": [{"memberId": 2, "memberNameEn": "All-items"}, {"memberId": 3, "memberNameEn": "Food"}]},
    ]}
    out = trim_cube_metadata(cube, ["4.2.0.0.0.0.0.0.0.0", "2.2.0.0.0.0.0.0.0.0"])
    geo = [m["memberNameEn"] for m in out["dimension"][0]["member"]]
    prod = [m["memberNameEn"] for m in out["dimension"][1]["member"]]
    assert geo == ["Canada", "St. John's"] and prod == ["All-items"]


def test_data_request_url_quotes_vector_ids(monkeypatch):
    client = WdsClient(min_interval=0)
    seen = {}

    def fake_call(method, url, json_body=None):
        seen["url"] = url
        return [{"status": "SUCCESS", "object": {"vectorId": 1, "vectorDataPoint": []}}]

    monkeypatch.setattr(client, "_call", fake_call)
    client.data_by_reference_period([41692846, 1643278046], "2016-01-01", "2026-10-17")
    assert "vectorIds=%2241692846%22,%221643278046%22" in seen["url"]
    assert seen["url"].endswith("&startRefPeriod=2016-01-01&endReferencePeriod=2026-10-17")
