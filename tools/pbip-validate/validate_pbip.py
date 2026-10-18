#!/usr/bin/env python3
"""Offline validator for Power BI Projects (PBIP) saved in PBIR format.

Two layers:

1. SCHEMA  - every JSON file (.json, .pbir, .pbism, .pbip, .platform) that declares a
             "$schema" under https://developer.microsoft.com/json-schemas/ is validated
             against THAT exact schema version, resolved from a local copy of the
             needed files from github.com/microsoft/json-schemas (no network access). Cross-file $refs
             (e.g. visualContainer -> visualConfiguration/schema-embedded.json ->
             semanticQuery) are resolved through a referencing.Registry that maps every
             https://developer.microsoft.com/json-schemas/<path> URL (and each schema's
             own $id, which differs for the *-embedded files) to the downloaded file.

2. CONVENTIONS - checks that the schemas do not enforce but Power BI Desktop relies on
             (folder layout, name regex, pageOrder/activePageName, byPath targets,
             resource files, field references against the TMDL/TMSL model, expression
             wrappers for formatting values, Literal encodings, BOM, ...). Each finding
             carries a code so it can be filtered. Use --schema-only to skip this layer.

Usage:
  python -I tools/pbip-validate/validate_pbip.py [--schemas DIR] [--strict]
                                              [--schema-only] [--quiet] PATH [PATH ...]

  PATH may be a PBIP root folder, a *.Report or *.SemanticModel folder, or a single file.
  Exit code: 0 = no errors (and no warnings with --strict), 1 = findings, 2 = usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    from jsonschema import Draft7Validator
    from jsonschema.exceptions import best_match
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT7
except ImportError:  # pragma: no cover
    sys.exit("jsonschema (>=4.18) is required: python -m pip install jsonschema")

SCHEMA_PREFIX = "https://developer.microsoft.com/json-schemas/"
JSON_SUFFIXES = (".json", ".pbir", ".pbism", ".pbip")
NAME_RE = re.compile(r"^[\w-]+$")  # Learn: "one or more word characters ... or hyphens"
GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
LITERAL_RES = [
    re.compile(r"^(true|false|null)$"),
    re.compile(r"^-?\d+L$"),                                   # Int64
    re.compile(r"^-?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?D$"),      # Double
    re.compile(r"^-?(\d+\.?\d*|\.\d+)M$"),                     # Decimal
    re.compile(r"^datetime'[^']*'$"),                          # DateTime
    re.compile(r"^'(?:[^']|'')*'$"),                           # String (single quotes, '' escape)
]

# Which schema family each well-known PBIR/PBIP file must declare.
EXPECTED_FAMILY = {
    "visual.json": "fabric/item/report/definition/visualContainer/",
    "mobile.json": "fabric/item/report/definition/visualContainerMobileState/",
    "page.json": "fabric/item/report/definition/page/",
    "pages.json": "fabric/item/report/definition/pagesMetadata/",
    "version.json": "fabric/item/report/definition/versionMetadata/",
    "bookmarks.json": "fabric/item/report/definition/bookmarksMetadata/",
    "reportExtensions.json": "fabric/item/report/definition/reportExtension/",
    "definition.pbism": "fabric/item/semanticModel/definitionProperties/",
    ".platform": "fabric/gitIntegration/platformProperties/",
}

# visualType values seen in Microsoft-owned PBIR samples / docs (non-exhaustive).
CORE_VISUALS = {
    "actionButton", "advancedSlicerVisual", "aiNarratives", "areaChart", "azureMap", "barChart",
    "basicShape", "bookmarkNavigator", "card", "cardVisual", "clusteredBarChart",
    "clusteredColumnChart", "columnChart", "decompositionTreeVisual", "donutChart", "filledMap",
    "funnel", "gauge", "hundredPercentStackedAreaChart", "hundredPercentStackedBarChart",
    "hundredPercentStackedColumnChart", "image", "keyDriversVisual", "kpi", "lineChart",
    "lineClusteredColumnComboChart", "lineStackedColumnComboChart", "listSlicer", "map",
    "multiRowCard", "pageNavigator", "pieChart", "pivotTable", "pythonVisual", "qnaVisual",
    "ribbonChart", "scatterChart", "scriptVisual", "shape", "shapeMap", "slicer",
    "stackedAreaChart", "tableEx", "textbox", "textSlicer", "treemap", "waterfallChart",
}


class Findings:
    def __init__(self) -> None:
        self.items: list[tuple[str, str, str, str]] = []  # (severity, code, path, message)

    def add(self, sev: str, code: str, path, msg: str) -> None:
        self.items.append((sev, code, str(path), msg))

    def count(self, sev: str) -> int:
        return sum(1 for s, *_ in self.items if s == sev)


# --------------------------------------------------------------------------- schemas
def build_registry(schemas_root: Path):
    """Map every downloaded schema to its public URL (and its $id when different)."""
    fabric = schemas_root / "fabric"
    if not fabric.is_dir():
        sys.exit(f"schema folder not found: {fabric} (clone microsoft/json-schemas first)")
    pairs = []
    by_url: dict[str, dict] = {}
    for p in sorted(fabric.rglob("*.json")):
        try:
            contents = json.loads(p.read_text(encoding="utf-8-sig"))
        except (ValueError, UnicodeDecodeError):
            continue
        if not isinstance(contents, dict):
            continue
        url = SCHEMA_PREFIX + p.relative_to(schemas_root).as_posix()
        res = Resource.from_contents(contents, default_specification=DRAFT7)
        pairs.append((url, res))
        by_url[url] = contents
        sid = contents.get("$id")
        if isinstance(sid, str) and sid.startswith("http") and sid != url:
            # e.g. visualConfiguration/2.8.0/schema-embedded.json has $id ".../schema.embedded.json"
            pairs.append((sid, res))
            by_url.setdefault(sid, contents)
    return Registry().with_resources(pairs), by_url


class SchemaValidator:
    def __init__(self, schemas_root: Path):
        self.registry, self.by_url = build_registry(schemas_root)
        self._cache: dict[str, Draft7Validator] = {}

    def get(self, url: str):
        if url not in self.by_url:
            return None
        if url not in self._cache:
            self._cache[url] = Draft7Validator(self.by_url[url], registry=self.registry)
        return self._cache[url]


def fmt_path(parts) -> str:
    out = "$"
    for p in parts:
        out += f"[{p}]" if isinstance(p, int) else f".{p}"
    return out


def describe(err) -> str:
    msg = err.message
    if err.context:  # anyOf/oneOf: surface the most relevant sub-error
        sub = best_match(err.context)
        msg += f"  [closest: {fmt_path(list(err.absolute_path) + list(sub.relative_path))}: {sub.message}]"
    return msg[:600]


# --------------------------------------------------------------------------- JSON loading
def load_json(path: Path, f: Findings):
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        f.add("WARN", "BOM", path, "UTF-8 BOM present; Learn: save PBIP files as UTF-8 without BOM")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        f.add("ERROR", "ENCODING", path, f"not valid UTF-8: {e}")
        return None
    dupes = []

    def hook(pairs):
        seen = set()
        for k, _ in pairs:
            if k in seen:
                dupes.append(k)
            seen.add(k)
        return dict(pairs)

    def bad_const(c):
        raise ValueError(f"non-standard JSON constant {c}")

    try:
        doc = json.loads(text, object_pairs_hook=hook, parse_constant=bad_const)
    except ValueError as e:
        f.add("ERROR", "JSON_PARSE", path, f"invalid JSON (comments/trailing commas are not allowed): {e}")
        return None
    if dupes:
        f.add("WARN", "DUPLICATE_KEY", path, f"duplicate keys: {sorted(set(dupes))}")
    return doc


def expected_family(path: Path) -> str | None:
    n = path.name
    if n.endswith(".bookmark.json"):
        return "fabric/item/report/definition/bookmark/"
    if n.endswith(".pbip"):
        return "fabric/pbip/pbipProperties/"
    if n.endswith(".pbir"):
        return "fabric/item/report/definitionProperties/"
    if n == "report.json" and path.parent.name == "definition":
        return "fabric/item/report/definition/report/"
    if n == "version.json" and path.parent.name != "definition":
        return None
    return EXPECTED_FAMILY.get(n)


def is_core_definition_file(path: Path) -> bool:
    return expected_family(path) is not None and ".pbi" not in path.parts


def validate_schema(path: Path, doc, sv: SchemaValidator, f: Findings) -> None:
    fam = expected_family(path)
    sch = doc.get("$schema") if isinstance(doc, dict) else None
    if not isinstance(sch, str):
        if fam and path.suffix in (".pbip", ".pbir", ".pbism"):
            f.add("WARN", "NO_SCHEMA", path, "missing \"$schema\" (older Desktop builds omitted it here; current ones write it)")
        elif fam:
            f.add("ERROR", "NO_SCHEMA", path, "missing \"$schema\"; every PBIR JSON file must declare one")
        return
    if not sch.startswith(SCHEMA_PREFIX):
        f.add("WARN" if not fam else "ERROR", "FOREIGN_SCHEMA", path, f"$schema is not a Microsoft Fabric schema URL: {sch}")
        return
    if fam and not sch.startswith(SCHEMA_PREFIX + fam):
        f.add("ERROR", "WRONG_SCHEMA_FAMILY", path, f"{path.name} must declare a {fam}* schema, found {sch}")
    v = sv.get(sch)
    if v is None:
        sev = "ERROR" if is_core_definition_file(path) else "WARN"
        f.add(sev, "SCHEMA_UNKNOWN", path,
              f"$schema not found in the local json-schemas clone (typo, or a version not yet published): {sch}")
        return
    for err in sorted(v.iter_errors(doc), key=lambda e: [str(x) for x in e.absolute_path]):
        f.add("ERROR", "SCHEMA", path, f"{fmt_path(err.absolute_path)}: {describe(err)}")


# --------------------------------------------------------------------------- semantic model names
def _tmdl_name(tok: str) -> str:
    tok = tok.strip()
    if tok.startswith("'") and tok.endswith("'") and len(tok) >= 2:
        return tok[1:-1].replace("''", "'")
    return tok


TMDL_DECL = re.compile(r"^(\t*)(table|column|measure|hierarchy|level|calculationItem)\s+('(?:[^']|'')*'|[^\s=]+)")


def load_model_names(sm_dir: Path):
    """Return {table_lower: {"name":..., "columns": set_lower, "measures": set_lower,
    "hierarchies": set_lower}} from TMDL (definition/**/*.tmdl) or TMSL (model.bim)."""
    tables: dict[str, dict] = {}

    def table(name: str):
        return tables.setdefault(name.lower(), {"name": name, "columns": set(), "measures": set(), "hierarchies": set()})

    tmdl_dir = sm_dir / "definition"
    if tmdl_dir.is_dir():
        for p in sorted(tmdl_dir.rglob("*.tmdl")):
            cur = None
            for line in p.read_text(encoding="utf-8-sig", errors="replace").splitlines():
                m = TMDL_DECL.match(line)
                if not m:
                    continue
                depth, kind, tok = len(m.group(1)), m.group(2), _tmdl_name(m.group(3))
                if kind == "table" and depth == 0:
                    cur = table(tok)
                elif cur is not None and depth == 1 and kind == "column":
                    cur["columns"].add(tok.lower())
                elif cur is not None and depth == 1 and kind == "measure":
                    cur["measures"].add(tok.lower())
                elif cur is not None and depth == 1 and kind == "hierarchy":
                    cur["hierarchies"].add(tok.lower())
        return tables or None
    bim = sm_dir / "model.bim"
    if bim.is_file():
        try:
            model = json.loads(bim.read_text(encoding="utf-8-sig")).get("model", {})
        except ValueError:
            return None
        for t in model.get("tables", []):
            tt = table(t.get("name", ""))
            tt["columns"].update(c.get("name", "").lower() for c in t.get("columns", []))
            tt["measures"].update(m.get("name", "").lower() for m in t.get("measures", []))
            tt["hierarchies"].update(h.get("name", "").lower() for h in t.get("hierarchies", []))
        return tables or None
    return None


def add_report_extensions(tables, rep_def: Path) -> None:
    p = rep_def / "reportExtensions.json"
    if not (tables is not None and p.is_file()):
        return
    try:
        doc = json.loads(p.read_text(encoding="utf-8-sig"))
    except ValueError:
        return
    for ent in doc.get("entities", []) or []:
        t = tables.setdefault(ent.get("name", "").lower(),
                              {"name": ent.get("name", ""), "columns": set(), "measures": set(), "hierarchies": set()})
        t["measures"].update((m.get("name") or "").lower() for m in ent.get("measures", []) or [])


def check_field_refs(doc, path: Path, tables, f: Findings) -> None:
    """Walk semantic-query expressions and check Entity/Property against the model."""

    def entity_of(expr, aliases):
        sr = (expr or {}).get("SourceRef") if isinstance(expr, dict) else None
        if not isinstance(sr, dict):
            return None
        if "Entity" in sr:
            return sr["Entity"]
        if "Source" in sr:
            return aliases.get(sr["Source"], None)
        return None

    def check(kind, ent, prop, where):
        # Projections that do not resolve render a blank/broken visual (json-schemas issue #572);
        # stale refs elsewhere (sortDefinition, filters, formatting) were seen in working demo repos.
        sev = "ERROR" if ".queryState." in where else "WARN"
        t = tables.get(str(ent).lower())
        if t is None:
            f.add(sev, "FIELD_TABLE", path, f"{where}: table '{ent}' not found in semantic model")
            return
        bucket = {"Column": "columns", "Measure": "measures", "Hierarchy": "hierarchies"}[kind]
        pool = t[bucket] | (t["columns"] if kind == "Measure" else set()) | (t["measures"] if kind == "Column" else set())
        if str(prop).lower() not in pool:
            f.add(sev, "FIELD_PROPERTY", path,
                  f"{where}: {kind.lower()} '{ent}'[{prop}] not found in semantic model")
        elif str(prop).lower() not in t[bucket]:
            f.add("WARN", "FIELD_KIND", path,
                  f"{where}: '{ent}'[{prop}] is referenced as {kind} but the model defines it as the other kind")

    def walk(o, aliases, ptr):
        if isinstance(o, dict):
            frm = o.get("From")
            if isinstance(frm, list) and all(isinstance(x, dict) for x in frm):
                aliases = dict(aliases)
                for x in frm:
                    if "Name" in x and "Entity" in x:
                        aliases[x["Name"]] = x["Entity"]
            for kind in ("Column", "Measure", "Hierarchy"):
                node = o.get(kind)
                if isinstance(node, dict) and "Expression" in node:
                    prop = node.get("Hierarchy" if kind == "Hierarchy" else "Property")
                    ent = entity_of(node.get("Expression"), aliases)
                    if ent is not None and prop is not None:
                        check(kind, ent, prop, ptr + "." + kind)
            pvs = o.get("PropertyVariationSource")
            if isinstance(pvs, dict):
                ent = entity_of(pvs.get("Expression"), aliases)
                if ent is not None and pvs.get("Property"):
                    check("Column", ent, pvs["Property"], ptr + ".PropertyVariationSource")
            for k, v in o.items():
                walk(v, aliases, f"{ptr}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, aliases, f"{ptr}[{i}]")

    walk(doc, {}, "$")


# --------------------------------------------------------------------------- formatting values
def check_formatting(objs, path: Path, where: str, f: Findings) -> None:
    if not isinstance(objs, dict):
        return
    for oname, entries in objs.items():
        if not isinstance(entries, list):
            continue
        for i, e in enumerate(entries):
            props = e.get("properties") if isinstance(e, dict) else None
            for pname, pval in (props or {}).items():
                if pname == "paragraphs" and isinstance(pval, list):
                    continue
                if not isinstance(pval, dict):
                    f.add("WARN", "RAW_FORMAT_VALUE", path,
                          f"{where}.{oname}[{i}].properties.{pname} is a raw {type(pval).__name__}; Desktop writes "
                          "expression wrappers, e.g. {\"expr\":{\"Literal\":{\"Value\":\"true\"}}}")


def check_literals(o, path: Path, f: Findings, ptr="$") -> None:
    if isinstance(o, dict):
        lit = o.get("Literal")
        if isinstance(lit, dict) and "Value" in lit:
            v = lit["Value"]
            if not isinstance(v, str) or not any(r.match(v) for r in LITERAL_RES):
                f.add("WARN", "LITERAL_FORMAT", path,
                      f"{ptr}.Literal.Value {v!r} is not a recognised encoding "
                      "(true/false/null, 12L, 1.5D, 2M, datetime'...', 'text')")
        for k, v in o.items():
            check_literals(v, path, f, f"{ptr}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            check_literals(v, path, f, f"{ptr}[{i}]")


# --------------------------------------------------------------------------- item checks
def resolve_rel(base: Path, rel: str) -> Path:
    return (base / rel).resolve()


def check_pbip_file(path: Path, doc, f: Findings) -> None:
    for i, art in enumerate(doc.get("artifacts", []) or []):
        rp = ((art or {}).get("report") or {}).get("path")
        if not rp:
            continue
        if "\\" in rp or os.path.isabs(rp):
            f.add("ERROR", "PBIP_PATH", path, f"artifacts[{i}].report.path must be relative with '/' separators: {rp}")
        target = resolve_rel(path.parent, rp.replace("\\", "/"))
        if not (target / "definition.pbir").is_file():
            f.add("ERROR", "PBIP_TARGET", path, f"artifacts[{i}].report.path '{rp}' has no definition.pbir")


def check_platform(path: Path, doc, f: Findings) -> None:
    md, cfg = doc.get("metadata") or {}, doc.get("config") or {}
    if "version" in doc:
        f.add("WARN", "PLATFORM_VERSION", path,
              "top-level 'version' found; Desktop/Fabric write it only as config.version (the Learn sample is outdated)")
    lid = cfg.get("logicalId")
    if isinstance(lid, str) and not GUID_RE.match(lid):
        f.add("WARN", "PLATFORM_LOGICALID", path, f"config.logicalId should be a GUID: {lid}")
    want = {".Report": "Report", ".SemanticModel": "SemanticModel"}.get(path.parent.suffix)
    if want and md.get("type") != want:
        f.add("WARN", "PLATFORM_TYPE", path, f"metadata.type is {md.get('type')!r}; folder suffix implies {want!r}")


def check_semantic_model(sm: Path, f: Findings) -> None:
    pbism = sm / "definition.pbism"
    if not pbism.is_file():
        f.add("ERROR", "SM_PBISM", sm, "semantic model folder has no definition.pbism")
        return
    has_tmdl = (sm / "definition").is_dir()
    has_bim = (sm / "model.bim").is_file()
    if not (has_tmdl or has_bim):
        f.add("ERROR", "SM_DEFINITION", sm, "needs definition/ (TMDL) or model.bim (TMSL)")
    if has_tmdl and has_bim:
        f.add("WARN", "SM_BOTH", sm, "both definition/ and model.bim present; keep exactly one format")
    if has_tmdl:
        for req in ("database.tmdl", "model.tmdl"):
            if not (sm / "definition" / req).is_file():
                f.add("ERROR", "SM_TMDL_FILE", sm, f"definition/{req} missing")
        try:
            ver = json.loads(pbism.read_text(encoding="utf-8-sig")).get("version", "0")
            if float(ver) < 4.0:
                f.add("ERROR", "SM_PBISM_VERSION", pbism, f"version {ver} only supports model.bim; use >= 4.0 for TMDL")
        except (ValueError, TypeError):
            pass


def check_report(rep: Path, docs: dict, f: Findings, check_fields: bool):
    """Check one *.Report folder; returns the byPath semantic model folder it checked (or None)."""
    pbir = rep / "definition.pbir"
    if not pbir.is_file():
        f.add("ERROR", "REPORT_PBIR", rep, "report folder has no definition.pbir")
        return None
    pd = docs.get(pbir) or {}
    ref = pd.get("datasetReference") or {}
    by_path, by_conn = ref.get("byPath"), ref.get("byConnection")
    tables = None
    sm_checked = None
    if bool(by_path) == bool(by_conn):
        f.add("ERROR", "PBIR_REF", pbir, "datasetReference needs exactly one of byPath / byConnection")
    if by_path:
        rp = by_path.get("path", "")
        if "\\" in rp or os.path.isabs(rp):
            f.add("ERROR", "PBIR_BYPATH", pbir, f"byPath.path must be relative with '/' separators: {rp}")
        sm = resolve_rel(rep, rp.replace("\\", "/"))
        if not (sm / "definition.pbism").is_file():
            f.add("ERROR", "PBIR_BYPATH", pbir, f"byPath '{rp}' does not point at a folder containing definition.pbism")
        else:
            check_semantic_model(sm, f)
            sm_checked = sm
            if check_fields:
                tables = load_model_names(sm)
    _check_report_body(rep, pd, tables, by_path, docs, f, check_fields)
    return sm_checked


def _check_report_body(rep: Path, pd: dict, tables, by_path, docs: dict, f: Findings, check_fields: bool):
    pbir = rep / "definition.pbir"
    defn = rep / "definition"
    try:
        pbir_ver = float(pd.get("version", "0"))
    except (TypeError, ValueError):
        pbir_ver = 0.0
    if not defn.is_dir():
        if (rep / "report.json").is_file():
            f.add("INFO", "PBIR_LEGACY", rep, "PBIR-Legacy report.json format (not PBIR)")
        else:
            f.add("ERROR", "REPORT_DEFINITION", rep, "neither definition/ (PBIR) nor report.json (PBIR-Legacy) present")
        return
    if pbir_ver < 4.0:
        f.add("ERROR", "PBIR_VERSION", pbir, "definition.pbir version must be >= 4.0 for the PBIR definition/ folder")
    if (rep / "report.json").is_file():
        f.add("ERROR", "PBIR_BOTH", rep, "both report.json (PBIR-Legacy) and definition/ (PBIR) present; they are mutually exclusive")
    for req in ("version.json", "report.json"):
        if not (defn / req).is_file():
            f.add("ERROR", "PBIR_REQUIRED", defn, f"definition/{req} is required")
    pages_dir = defn / "pages"
    if not pages_dir.is_dir():
        f.add("ERROR", "PBIR_REQUIRED", defn, "definition/pages/ is required")
        return
    if tables is not None:
        add_report_extensions(tables, defn)

    # ---- report.json resources / theme
    rj = docs.get(defn / "report.json")
    if isinstance(rj, dict):
        check_report_resources(rep, defn / "report.json", rj, f)
        check_formatting(rj.get("objects"), defn / "report.json", "$.objects", f)

    # ---- pages
    page_names: dict[str, Path] = {}
    for pdir in sorted(p for p in pages_dir.iterdir() if p.is_dir()):
        pj = pdir / "page.json"
        if not NAME_RE.match(pdir.name):
            f.add("ERROR", "NAME_REGEX", pdir, "folder name must match ^[\\w-]+$ or Desktop ignores it")
        if not pj.is_file():
            f.add("ERROR", "PAGE_JSON", pdir, "page folder has no page.json")
            continue
        page = docs.get(pj)
        if not isinstance(page, dict):
            continue
        name = page.get("name", "")
        if not NAME_RE.match(str(name)):
            f.add("ERROR", "NAME_REGEX", pj, f"page name {name!r} must match ^[\\w-]+$ or Desktop ignores the page")
        if name in page_names:
            f.add("ERROR", "DUP_NAME", pj, f"page name {name!r} duplicated (also {page_names[name]})")
        page_names[name] = pj
        if name != pdir.name:
            f.add("INFO", "FOLDER_NAME", pj, f"folder '{pdir.name}' differs from name '{name}' (allowed; Desktop keeps folder names)")
        if page.get("displayOption") != "DeprecatedDynamic":
            for k in ("width", "height"):
                if not isinstance(page.get(k), (int, float)):
                    f.add("ERROR", "PAGE_SIZE", pj, f"'{k}' is required unless displayOption is DeprecatedDynamic")
        check_formatting(page.get("objects"), pj, "$.objects", f)
        check_page_visuals(pdir, page, docs, f)

    # ---- pages.json
    pjson = pages_dir / "pages.json"
    meta = docs.get(pjson)
    if isinstance(meta, dict):
        order = meta.get("pageOrder") or []
        for n in order:
            if n not in page_names:
                f.add("WARN", "PAGE_ORDER", pjson, f"pageOrder entry {n!r} has no page.json with that name (ignored by Desktop)")
        for n in page_names:
            if order and n not in order:
                f.add("INFO", "PAGE_ORDER", pjson, f"page {n!r} not in pageOrder (appended, ordered by displayName)")
        for key in ("activePageName", "landingPageName"):
            if meta.get(key) and meta[key] not in page_names:
                f.add("WARN", "ACTIVE_PAGE", pjson, f"{key} {meta[key]!r} is not a page name (non-blocking; Desktop resets it)")
    elif not pjson.is_file():
        f.add("INFO", "PAGES_JSON", pages_dir, "pages.json absent (optional; pages ordered by displayName)")
    if not page_names:
        f.add("ERROR", "NO_PAGES", pages_dir, "report has no valid pages")

    # ---- bookmarks
    bdir = defn / "bookmarks"
    if bdir.is_dir():
        names = {}
        for bp in sorted(bdir.glob("*.bookmark.json")):
            b = docs.get(bp)
            if isinstance(b, dict):
                nm = b.get("name", "")
                if not NAME_RE.match(str(nm)):
                    f.add("ERROR", "NAME_REGEX", bp, f"bookmark name {nm!r} must match ^[\\w-]+$")
                if nm in names:
                    f.add("ERROR", "DUP_NAME", bp, f"bookmark name {nm!r} duplicated")
                names[nm] = bp
        bm = docs.get(bdir / "bookmarks.json")
        if isinstance(bm, dict):
            def refs(items):
                for it in items or []:
                    if isinstance(it, dict):
                        if "name" in it and "children" not in it:
                            yield it["name"]
                        yield from (c for c in it.get("children", []) if isinstance(c, str))
            for r in refs(bm.get("items")):
                if r not in names:
                    f.add("WARN", "BOOKMARK_REF", bdir / "bookmarks.json", f"bookmark {r!r} listed but no {r}.bookmark.json found")

    # ---- field references
    if tables is not None:
        for p, d in docs.items():
            if defn in p.parents and isinstance(d, dict):
                check_field_refs(d, p, tables, f)
    elif check_fields and by_path:
        f.add("INFO", "FIELDS_SKIPPED", rep, "no tables found in the TMDL/model.bim; field references not checked")


def check_report_resources(rep: Path, rj_path: Path, rj: dict, f: Findings) -> None:
    pk_items = defaultdict(set)
    listed_files = set()
    for pkg in rj.get("resourcePackages", []) or []:
        ptype, pname = pkg.get("type"), pkg.get("name")
        for it in pkg.get("items", []) or []:
            pk_items[ptype].add(it.get("name"))
            if ptype not in ("SharedResources", "RegisteredResources"):
                continue
            target = rep / "StaticResources" / (pname or ptype) / (it.get("path") or "")
            listed_files.add(target.resolve())
            if target.is_file():
                continue
            if ptype == "RegisteredResources":
                f.add("ERROR", "RESOURCE_MISSING", rj_path, f"RegisteredResources item '{it.get('path')}' missing at {target}")
            elif it.get("type") == "BaseTheme":
                f.add("WARN", "BASETHEME_FILE", rj_path,
                      f"base theme file {target.relative_to(rep)} absent. Desktop can resolve bundled base themes "
                      "(Microsoft samples ship without it) but include a Desktop-saved copy for portability")
            else:
                f.add("WARN", "RESOURCE_MISSING", rj_path, f"SharedResources item '{it.get('path')}' missing at {target}")
    tc = rj.get("themeCollection") or {}
    if "baseTheme" not in tc:
        f.add("WARN", "NO_BASETHEME", rj_path, "themeCollection has no baseTheme (every Desktop-saved report has one)")
    for key in ("baseTheme", "customTheme"):
        t = tc.get(key)
        if isinstance(t, dict) and t.get("name") not in pk_items.get(t.get("type"), set()):
            f.add("WARN", "THEME_PACKAGE", rj_path,
                  f"themeCollection.{key} {t.get('name')!r} has no item in the {t.get('type')} resource package")
    reg = rep / "StaticResources" / "RegisteredResources"
    if reg.is_dir():
        for p in reg.iterdir():
            if p.is_file() and p.resolve() not in listed_files:
                f.add("INFO", "RESOURCE_UNLISTED", p, "file in RegisteredResources not listed in report.json resourcePackages")


def check_page_visuals(pdir: Path, page: dict, docs: dict, f: Findings) -> None:
    vdir = pdir / "visuals"
    if not vdir.is_dir():
        return
    names, groups, parents = {}, set(), []
    pw, ph = page.get("width"), page.get("height")
    for vd in sorted(p for p in vdir.iterdir() if p.is_dir()):
        vj = vd / "visual.json"
        if not NAME_RE.match(vd.name):
            f.add("ERROR", "NAME_REGEX", vd, "folder name must match ^[\\w-]+$ or Desktop ignores it")
        if not vj.is_file():
            f.add("ERROR", "VISUAL_JSON", vd, "visual folder has no visual.json")
            continue
        v = docs.get(vj)
        if not isinstance(v, dict):
            continue
        nm = v.get("name", "")
        if not NAME_RE.match(str(nm)):
            f.add("ERROR", "NAME_REGEX", vj, f"visual name {nm!r} must match ^[\\w-]+$")
        if nm in names:
            f.add("ERROR", "DUP_NAME", vj, f"visual name {nm!r} duplicated on page (also {names[nm]})")
        names[nm] = vj
        if "visualGroup" in v:
            groups.add(nm)
        if v.get("parentGroupName"):
            parents.append((vj, v["parentGroupName"]))
        pos = v.get("position") or {}
        try:
            if min(pos.get("x", 0), pos.get("y", 0)) < 0:
                f.add("WARN", "POSITION", vj, "negative x/y")
            if isinstance(pw, (int, float)) and pos.get("x", 0) + pos.get("width", 0) > pw + 0.5:
                f.add("WARN", "POSITION", vj, f"x+width {pos.get('x', 0) + pos.get('width', 0):.1f} exceeds page width {pw}")
            if isinstance(ph, (int, float)) and pos.get("y", 0) + pos.get("height", 0) > ph + 0.5:
                f.add("WARN", "POSITION", vj, f"y+height {pos.get('y', 0) + pos.get('height', 0):.1f} exceeds page height {ph}")
        except TypeError:
            pass
        vis = v.get("visual") or {}
        vt = vis.get("visualType")
        if vt and vt not in CORE_VISUALS and not re.search(r"[0-9A-F]{8,}|\d{10,}", vt):
            f.add("INFO", "VISUAL_TYPE", vj, f"visualType {vt!r} not in the core list; check spelling/case or custom-visual registration")
        for role, st in ((vis.get("query") or {}).get("queryState") or {}).items():
            seen = set()  # Desktop itself repeats a queryRef across roles (e.g. Y and Tooltips)
            for pr in (st or {}).get("projections", []) or []:
                q = pr.get("queryRef")
                if q in seen:  # seen in Desktop-saved Microsoft samples too, so informational only
                    f.add("INFO", "QUERYREF_DUP", vj, f"queryRef {q!r} repeated within role {role!r}")
                seen.add(q)
        check_formatting(vis.get("objects"), vj, "$.visual.objects", f)
        check_formatting(vis.get("visualContainerObjects"), vj, "$.visual.visualContainerObjects", f)
        fnames = set()
        for flt in (v.get("filterConfig") or {}).get("filters", []) or []:
            if flt.get("name") in fnames:
                f.add("WARN", "FILTER_DUP", vj, f"filter name {flt.get('name')!r} duplicated")
            fnames.add(flt.get("name"))
    for vj, parent in parents:
        if parent not in groups:
            f.add("ERROR", "PARENT_GROUP", vj, f"parentGroupName {parent!r} is not a visualGroup container on this page")


# --------------------------------------------------------------------------- driver
def iter_files(root: Path):
    if root.is_file():
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules")]
        for fn in filenames:
            if fn.endswith(JSON_SUFFIXES) or fn == ".platform":
                yield Path(dirpath) / fn


def main(argv=None) -> int:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description="Validate PBIP/PBIR folders offline against Microsoft Fabric JSON schemas.")
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--schemas", type=Path, default=here / "schemas",
                    help="folder that contains the 'fabric/' schema tree (default: the copy next to this script)")
    ap.add_argument("--schema-only", action="store_true", help="skip Desktop convention checks")
    ap.add_argument("--no-fields", action="store_true", help="skip field-reference checks against TMDL")
    ap.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    ap.add_argument("--quiet", action="store_true", help="hide INFO findings")
    args = ap.parse_args(argv)

    sv = SchemaValidator(args.schemas)
    f = Findings()
    docs: dict[Path, object] = {}
    n_schema = 0
    for root in args.paths:
        if not root.exists():
            print(f"path not found: {root}", file=sys.stderr)
            return 2
        for p in iter_files(root.resolve()):
            if "StaticResources" in p.parts and p.suffix == ".json":
                continue  # theme/image payloads carry no Fabric $schema
            d = load_json(p, f)
            if d is None:
                continue
            docs[p] = d
            if isinstance(d, dict):
                if isinstance(d.get("$schema"), str):
                    n_schema += 1
                validate_schema(p, d, sv, f)
                if not args.schema_only:
                    check_literals(d, p, f)
                    if p.suffix == ".pbip":
                        check_pbip_file(p, d, f)
                    elif p.name == ".platform":
                        check_platform(p, d, f)

    if not args.schema_only:
        reports = sorted({p.parent for p in docs if p.name == "definition.pbir"})
        # also catch report folders that lack definition.pbir
        for p in docs:
            if p.name == "report.json" and p.parent.name == "definition" and p.parent.parent not in reports:
                reports.append(p.parent.parent)
        checked_models: set[Path] = set()
        for rep in reports:
            sm = check_report(rep, docs, f, check_fields=not args.no_fields)
            if sm is not None:
                checked_models.add(sm)
        for sm in sorted({p.parent for p in docs if p.name == "definition.pbism"} - checked_models):
            check_semantic_model(sm, f)

    order = {"ERROR": 0, "WARN": 1, "INFO": 2}
    for sev, code, path, msg in sorted(f.items, key=lambda x: (order[x[0]], x[2], x[1])):
        if sev == "INFO" and args.quiet:
            continue
        print(f"{sev:5} {code:18} {path}\n      {msg}")
    print(f"\nfiles parsed: {len(docs)}  with $schema: {n_schema}  "
          f"errors: {f.count('ERROR')}  warnings: {f.count('WARN')}  info: {f.count('INFO')}")
    bad = f.count("ERROR") or (args.strict and f.count("WARN"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
