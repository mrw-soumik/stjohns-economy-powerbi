"""Fetch step: download the catalogued series from the Statistics Canada WDS.

Writes a raw snapshot to data/raw/statcan/:
  series_info.json   series metadata for every catalogued vector
  cube_metadata.json table titles, release times and the dimension members used
  code_sets.json     WDS code sets (units, scalar factors, status and symbol codes)
  vector_data.json   data points for every vector in the requested period range
  manifest.json      when and how the snapshot was taken
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .catalogue import load_series
from .paths import RAW_DIR, START_DATE
from .wds import USER_AGENT, WDS_BASE, WdsClient

CUBE_FIELDS = (
    "productId", "cansimId", "cubeTitleEn", "cubeStartDate", "cubeEndDate", "releaseTime",
    "frequencyCode", "surveyCode", "subjectCode", "archiveStatusEn",
)
CHUNK_SIZE = 25


def _chunked(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def trim_cube_metadata(cube: dict, coordinates: list[str]) -> dict:
    """Keep table-level fields and only the dimension members the catalogue uses."""
    used: dict[int, set[int]] = {}
    for coord in coordinates:
        for position, member in enumerate(coord.split("."), start=1):
            if member != "0":
                used.setdefault(position, set()).add(int(member))
    out = {k: cube.get(k) for k in CUBE_FIELDS}
    out["dimension"] = []
    for dim in cube.get("dimension", []):
        pos = dim["dimensionPositionId"]
        members = [
            {k: m.get(k) for k in ("memberId", "memberNameEn", "classificationCode", "geoLevel", "vintage", "memberUomCode", "terminated")}
            for m in dim["member"] if m["memberId"] in used.get(pos, set())
        ]
        out["dimension"].append({"dimensionPositionId": pos, "dimensionNameEn": dim["dimensionNameEn"], "member": members})
    return out


def trim_code_sets(code_sets: dict, uom_codes: set[int]) -> dict:
    return {
        "scalar": code_sets["scalar"],
        "frequency": code_sets["frequency"],
        "status": code_sets["status"],
        "symbol": code_sets["symbol"],
        "uom": [u for u in code_sets["uom"] if int(u["memberUomCode"]) in uom_codes],
    }


def _write_json(path: Path, obj, indent=None) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent, sort_keys=False)
        f.write("\n")


def run_fetch(start: str = START_DATE, end: str | None = None, raw_dir: Path = RAW_DIR, client: WdsClient | None = None) -> dict:
    series = load_series()
    end = end or dt.date.today().isoformat()
    client = client or WdsClient()
    vector_ids = sorted(series["VectorId"].tolist())
    product_ids = sorted(series["ProductId"].unique().tolist())

    info = sorted(client.series_info(vector_ids), key=lambda o: o["vectorId"])
    cubes = client.cube_metadata(product_ids)
    code_sets = client.code_sets()
    data: list[dict] = []
    for chunk in _chunked(vector_ids, CHUNK_SIZE):
        data.extend(client.data_by_reference_period(chunk, start, end))
    data.sort(key=lambda o: o["vectorId"])

    returned = {o["vectorId"] for o in data}
    missing = set(vector_ids) - returned
    if missing:
        raise RuntimeError(f"WDS returned no data object for vectors: {sorted(missing)}")

    coords_by_pid = series.groupby("ProductId")["Coordinate"].apply(list).to_dict()
    trimmed_cubes = sorted(
        (trim_cube_metadata(c, coords_by_pid[int(c["productId"])]) for c in cubes),
        key=lambda c: int(c["productId"]),
    )
    uom_codes = {int(o["memberUomCode"]) for o in info}

    raw_dir.mkdir(parents=True, exist_ok=True)
    _write_json(raw_dir / "series_info.json", info, indent=1)
    _write_json(raw_dir / "cube_metadata.json", trimmed_cubes, indent=1)
    _write_json(raw_dir / "code_sets.json", trim_code_sets(code_sets, uom_codes), indent=1)
    _write_json(raw_dir / "vector_data.json", data)
    manifest = {
        "fetched_at_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "source": "Statistics Canada Web Data Service",
        "base_url": WDS_BASE,
        "user_agent": USER_AGENT,
        "start_reference_period": start,
        "end_reference_period": end,
        "vector_count": len(vector_ids),
        "data_point_count": sum(len(o["vectorDataPoint"]) for o in data),
        "requests": client.request_log,
    }
    _write_json(raw_dir / "manifest.json", manifest, indent=1)
    return manifest
