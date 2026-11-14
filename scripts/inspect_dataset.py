#!/usr/bin/env python3
"""Read-only inspection of a DomDose dataset 1.0 file.

Stdlib only. The input dataset is never modified and no package is installed.
Emits a JSON aggregate report plus a short ASCII console summary.

Structural checks approximate JSON Schema 2020-12 for the keywords actually
used by dataset.schema.json (type, enum, required, properties,
additionalProperties, items, anyOf, local $ref) and a permissive format check
(date / date-time). When the jsonschema package is importable, real Draft
2020-12 validation is used instead and both results are reported. Absence of
jsonschema is reported, never repaired by installing it.

Usage:
  .venv/Scripts/python.exe scripts/inspect_dataset.py \
      --dataset <dataset.json> --schema <dataset.schema.json> \
      --out .local/dataset-inspection.json
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

TZ10 = timezone(timedelta(hours=10))
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CARD_RE = re.compile(r"/(\d+)\.html(?:[?#].*)?$")
SIX_RANGE_RE = re.compile(r"(\d{6})\D{1,4}(\d{6})")
CONTRACT_DUR_TOL = 0.005
DUR_TOL = 1e-9

SCHEMA_KEYWORDS_SUPPORTED = [
    "type", "enum", "required", "properties", "additionalProperties",
    "items", "anyOf", "$ref",
]
SCHEMA_KEYWORDS_APPROXIMATED = ["format (date, date-time)"]
SCHEMA_KEYWORDS_IGNORED = ["description", "title"]


# loading
# ============================================================================

_DUP_KEYS = Counter()


def _pairs_hook(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            _DUP_KEYS[key] += 1
        out[key] = value
    return out


_NONFINITE = []


def _parse_constant(token):
    _NONFINITE.append(token)
    raise ValueError("non-finite JSON number token: %s" % token)


def load_json(path):
    with open(path, "rb") as handle:
        raw = handle.read()
    text = raw.decode("utf-8")
    data = json.loads(
        text, object_pairs_hook=_pairs_hook, parse_constant=_parse_constant
    )
    return data, raw


# structural (approximate JSON Schema) validation
# ============================================================================

class Validator:
    def __init__(self, schema):
        self.schema = schema
        self.defs = schema.get("$defs", {})
        self.errors = []
        self.codes = Counter()
        self.total = 0
        self.cap = 300

    def _record(self, path, code):
        self.total += 1
        self.codes[code] += 1
        if len(self.errors) < self.cap:
            self.errors.append({"path": path, "code": code})

    @staticmethod
    def _type_ok(value, name):
        if name == "object":
            return isinstance(value, dict)
        if name == "array":
            return isinstance(value, list)
        if name == "string":
            return isinstance(value, str)
        if name == "boolean":
            return isinstance(value, bool)
        if name == "null":
            return value is None
        if name == "integer":
            if isinstance(value, bool):
                return False
            if isinstance(value, int):
                return True
            return isinstance(value, float) and value.is_integer()
        if name == "number":
            if isinstance(value, bool):
                return False
            return isinstance(value, (int, float))
        return False

    @staticmethod
    def _format_ok(value, fmt):
        if value is None or not isinstance(value, str):
            return True
        if fmt == "date":
            if not DATE_RE.match(value):
                return False
            try:
                date.fromisoformat(value)
            except ValueError:
                return False
            return True
        if fmt == "date-time":
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return False
            return parsed.tzinfo is not None
        return True

    def check(self, value, sub, path):
        if "$ref" in sub:
            ref = sub["$ref"]
            if ref.startswith("#/$defs/"):
                sub = self.defs[ref.split("/")[-1]]
            else:
                return
        if "anyOf" in sub:
            matched = False
            for branch in sub["anyOf"]:
                trial = Validator(self.schema)
                trial.check(value, branch, path)
                if trial.total == 0:
                    matched = True
                    break
            if not matched:
                self._record(path, "anyOf")
            return
        if "type" in sub and not self._type_ok(value, sub["type"]):
            self._record(path, "type:%s" % sub["type"])
            return
        if "enum" in sub and value not in list(sub["enum"]):
            self._record(path, "enum")
        if "format" in sub and not self._format_ok(value, sub["format"]):
            self._record(path, "format:%s" % sub["format"])
        if isinstance(value, dict):
            for name in sub.get("required", []):
                if name not in value:
                    self._record(path, "required:%s" % name)
            props = sub.get("properties", {})
            if sub.get("additionalProperties") is False:
                for key in value:
                    if key not in props:
                        self._record(path, "extra-key")
            for key, child in value.items():
                if key in props:
                    self.check(child, props[key], path + "/" + key)
        elif isinstance(value, list) and "items" in sub:
            for index, item in enumerate(value):
                self.check(item, sub["items"], "%s/%d" % (path, index))


def structural_report(data, schema):
    validator = Validator(schema)
    validator.check(data, schema, "")
    return {
        "method": "stdlib approximation of JSON Schema 2020-12",
        "keywords_supported": SCHEMA_KEYWORDS_SUPPORTED,
        "keywords_approximated": SCHEMA_KEYWORDS_APPROXIMATED,
        "keywords_ignored": SCHEMA_KEYWORDS_IGNORED,
        "total_violations": validator.total,
        "violations_by_code": dict(sorted(validator.codes.items())),
        "sample_violations": validator.errors[:50],
    }


def jsonschema_report(data, schema):
    available = importlib.util.find_spec("jsonschema") is not None
    if not available:
        return {
            "available": False,
            "note": "jsonschema is not installed in this interpreter; not installed by this script",
        }
    import jsonschema

    format_checker = jsonschema.FormatChecker()
    validator = jsonschema.Draft202012Validator(schema, format_checker=format_checker)
    errors = sorted(validator.iter_errors(data), key=lambda err: list(err.path))
    samples = []
    for err in errors[:50]:
        samples.append(
            {
                "path": "/" + "/".join(str(part) for part in err.path),
                "validator": err.validator,
            }
        )
    return {
        "available": True,
        "draft": "2020-12",
        "format_checker": True,
        "total_errors": len(errors),
        "sample_errors": samples,
    }


# helpers
# ============================================================================

def parse_dt(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def iso(value):
    return None if value is None else value.isoformat()


def norm_address(value):
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip().casefold()


def delta_histogram(counter):
    return {str(key): counter[key] for key in sorted(counter)}

# main inspection
# ============================================================================

def inspect(dataset_path, schema_path):
    schema = json.loads(open(schema_path, "rb").read().decode("utf-8"))
    data, raw = load_json(dataset_path)

    enums = {
        "district": schema["$defs"]["district"]["enum"],
        "outage_type": schema["$defs"]["outage_type"]["enum"],
        "service_kind": schema["$defs"]["service_kind"]["enum"],
    }
    ev_schema = schema["properties"]["events"]["items"]["properties"]
    enums["kind"] = ev_schema["kind"]["enum"]
    enums["scope"] = ev_schema["scope"]["enum"]
    enums["duration_basis"] = ev_schema["duration_basis"]["enum"]
    enums["match"] = ev_schema["houses"]["items"]["properties"]["match"]["enum"]
    district_keys = list(
        schema["properties"]["meta"]["properties"]["city_houses"]
        ["properties"]["by_district"]["required"]
    )
    service_categories = list(
        schema["properties"]["houses"]["items"]["properties"]["services"]
        ["properties"].keys()
    )

    meta = data.get("meta") or {}
    houses = data.get("houses") or []
    events = data.get("events") or []
    sources = meta.get("sources") or []

    now = datetime.now(TZ10)
    stat = os.stat(dataset_path)
    mtime = datetime.fromtimestamp(stat.st_mtime, TZ10)

    report = {
        "tool": "scripts/inspect_dataset.py",
        "mode": "read-only stdlib inspection; aggregates only",
        "input": {
            "file": os.path.basename(dataset_path),
            "size_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "mtime_local_plus10": iso(mtime),
            "utf8_bom": raw[:3] == b"\xef\xbb\xbf",
        },
        "processed_at": iso(now),
        "json": {
            "top_level_keys": sorted(data.keys()),
            "duplicate_object_keys": dict(sorted(_DUP_KEYS.items())),
            "duplicate_object_key_count": sum(_DUP_KEYS.values()),
            "nonfinite_tokens": list(_NONFINITE),
            "houses_count": len(houses),
            "events_count": len(events),
            "sources_count": len(sources),
        },
        "schema_validation": {
            "stdlib": structural_report(data, schema),
            "jsonschema": jsonschema_report(data, schema),
        },
        "enums_from_schema": enums,
    }

    # meta
    period = meta.get("period") or {}
    period_from = (
        parse_dt(period["from"] + "T00:00:00+10:00") if period.get("from") else None
    )
    period_to = (
        parse_dt(period["to"] + "T00:00:00+10:00") if period.get("to") else None
    )
    generated_at = parse_dt(meta.get("generated_at"))
    city_houses = meta.get("city_houses") or {}
    by_district = city_houses.get("by_district") or {}

    report["meta"] = {
        "schema_version": meta.get("schema_version"),
        "city": meta.get("city"),
        "timezone": meta.get("timezone"),
        "period": {"from": period.get("from"), "to": period.get("to")},
        "period_days_inclusive": (
            (period_to.date() - period_from.date()).days + 1
            if period_from and period_to else None
        ),
        "heating_season_start": meta.get("heating_season_start"),
        "heating_season_start_is_null": meta.get("heating_season_start") is None,
        "generated_at": meta.get("generated_at"),
        "generated_at_offset_hours": (
            generated_at.utcoffset().total_seconds() / 3600 if generated_at else None
        ),
        "generated_at_vs_local_now_seconds": (
            (now - generated_at).total_seconds() if generated_at else None
        ),
        "generated_at_vs_file_mtime_seconds": (
            (mtime - generated_at).total_seconds() if generated_at else None
        ),
        "city_houses": {
            "total": city_houses.get("total"),
            "total_is_null": city_houses.get("total") is None,
            "by_district": by_district,
            "by_district_null_count": sum(
                1 for key in district_keys if by_district.get(key) is None
            ),
            "source_url_is_null": city_houses.get("source_url") is None,
        },
        "sources": [
            {
                "id": source.get("id"),
                "types": source.get("types"),
                "covered_from": source.get("covered_from"),
                "covered_to": source.get("covered_to"),
                "covered_from_is_null": source.get("covered_from") is None,
                "covered_to_is_null": source.get("covered_to") is None,
            }
            for source in sources
        ],
        "limitations_count": len(meta.get("limitations") or []),
        "limitation_int_tokens": [
            [int(token) for token in re.findall(r"\d+", text)]
            for text in (meta.get("limitations") or [])
        ],
    }
    claimed_ranges = [
        [int(lo), int(hi)]
        for lo, hi in SIX_RANGE_RE.findall(" ".join(meta.get("limitations") or []))
    ]
    report["meta"]["limitation_six_digit_ranges"] = claimed_ranges

    # events: distributions and counters
    type_counts = Counter()
    kind_counts = Counter()
    scope_counts = Counter()
    force_counts = Counter()
    district_counts = Counter()
    basis_counts = Counter()
    unknown_org = Counter()

    offsets = Counter()
    parse_failures = []
    starts = []
    starts_outside_period = []
    starts_after_generated = []
    ends_before_start = []
    negative_durations = []

    duration_checks = {
        "compared": 0,
        "exact_within_tol": 0,
        "off_by_rounding_2dp": 0,
        "gross_mismatch": 0,
        "max_abs_diff": 0.0,
        "samples": [],
    }
    basis_matrix = Counter()
    durations_by_basis = defaultdict(list)
    dur_unknown_events = 0

    event_ids = Counter()
    events_by_house_link = 0
    link_match_counts = Counter()
    link_house_missing = 0
    link_duplicate_in_event = 0
    links_total = 0
    links_per_house = defaultdict(lambda: Counter())
    linked_events_per_house = defaultdict(set)
    house_types_per_house = defaultdict(Counter)
    house_raw_duration_by_basis = defaultdict(lambda: defaultdict(float))
    house_duration_unknown_links = Counter()
    house_n_known_links = Counter()
    house_n_unknown_links = Counter()

    source_ref_missing = 0
    source_ref_dupe_in_event = 0
    source_ids_used = Counter()
    empty_sources = 0
    published_null = 0
    card_ids = set()
    url_parse_miss = 0
    source_id_set = {source.get("id") for source in sources}

    addresses_empty = 0
    districts_empty = 0
    houses_affected_null = 0
    houses_affected_zero = 0
    houses_affected_negative = 0
    end_planned_null = 0
    end_actual_null = 0
    cause_null = 0
    organization_null = 0
    notes_null = 0

    counter_mismatch = Counter()
    counter_mismatch_events = 0
    scope_address_conflicts = Counter()
    addresses_more_than_counter = 0

    exact_fp = Counter()
    tight_fp = Counter()
    addr_fp = Counter()
    address_dupe_in_event = 0

    house_by_id = {house.get("id"): house for house in houses}
    house_address_norm = {
        house.get("id"): norm_address(house.get("address")) for house in houses
    }

    link_addr_missing = 0
    event_address_present_but_no_link = 0
    link_samples = []
    addr_without_link_samples = []

    by_id = {event.get("id"): event for event in events}

    for index, event in enumerate(events):
        ev_id = event.get("id")
        event_ids[ev_id] += 1
        type_counts[event.get("type")] += 1
        kind_counts[event.get("kind")] += 1
        scope_counts[event.get("scope")] += 1
        force_counts[bool(event.get("force_majeure"))] += 1
        basis_counts[event.get("duration_basis")] += 1
        unknown_org[event.get("organization") is None] += 1
        for district in event.get("districts") or []:
            district_counts[district] += 1

        start_raw = event.get("start")
        start = parse_dt(start_raw)
        end_planned = parse_dt(event.get("end_planned"))
        end_actual = parse_dt(event.get("end_actual"))
        if start_raw is not None and start is None:
            parse_failures.append({"index": index, "field": "start"})
        for field, value in (("end_planned", event.get("end_planned")),
                             ("end_actual", event.get("end_actual"))):
            if value is not None and parse_dt(value) is None:
                parse_failures.append({"index": index, "field": field})

        if start is not None:
            starts.append(start)
            offsets[start.utcoffset().total_seconds() / 3600] += 1
            if period_from and period_to:
                if not (period_from.date() <= start.date() <= period_to.date()):
                    starts_outside_period.append(ev_id)
            if generated_at and start > generated_at:
                starts_after_generated.append(ev_id)
        for parsed in (end_planned, end_actual):
            if parsed is not None:
                offsets[parsed.utcoffset().total_seconds() / 3600] += 1
            if parsed is not None and start is not None and parsed < start:
                ends_before_start.append(ev_id)

        duration = event.get("duration_hours")
        basis = event.get("duration_basis")
        basis_matrix[(basis, event.get("end_actual") is not None,
                      event.get("end_planned") is not None)] += 1
        if duration is None:
            dur_unknown_events += 1
        else:
            if duration < 0:
                negative_durations.append(ev_id)
            durations_by_basis[basis].append(float(duration))
        reference_end = end_actual if basis == "actual" else end_planned
        if (basis != "unknown" and start is not None
                and reference_end is not None and duration is not None):
            computed = (reference_end - start).total_seconds() / 3600.0
            diff = abs(computed - float(duration))
            duration_checks["compared"] += 1
            duration_checks["max_abs_diff"] = max(duration_checks["max_abs_diff"], diff)
            label = None
            if diff <= DUR_TOL:
                duration_checks["exact_within_tol"] += 1
            elif diff <= CONTRACT_DUR_TOL and abs(round(computed, 2) - float(duration)) <= 1e-12:
                duration_checks["off_by_rounding_2dp"] += 1
                label = "rounded_2dp"
            else:
                duration_checks["gross_mismatch"] += 1
                label = "gross"
            if label and len(duration_checks["samples"]) < 6:
                duration_checks["samples"].append(
                    {
                        "event_id": ev_id,
                        "basis": basis,
                        "stored": float(duration),
                        "computed": round(computed, 6),
                        "abs_diff": round(diff, 9),
                        "class": label,
                    }
                )

        if event.get("end_planned") is None:
            end_planned_null += 1
        if event.get("end_actual") is None:
            end_actual_null += 1
        if event.get("cause") is None:
            cause_null += 1
        if event.get("organization") is None:
            organization_null += 1
        if event.get("notes") is None:
            notes_null += 1

        addresses = event.get("addresses") or []
        raw_addresses = event.get("addresses_raw")
        if not addresses:
            addresses_empty += 1
        if not (event.get("districts") or []):
            districts_empty += 1
        address_norms = {norm_address(item) for item in addresses}
        if len(address_norms) != len(addresses):
            address_dupe_in_event += 1

        affected = event.get("houses_affected")
        if affected is None:
            houses_affected_null += 1
        else:
            if affected == 0:
                houses_affected_zero += 1
            if affected < 0:
                houses_affected_negative += 1
            delta = len(addresses) - affected
            counter_mismatch[delta] += 1
            if delta != 0:
                counter_mismatch_events += 1
            if delta > 0:
                addresses_more_than_counter += 1

        scope = event.get("scope")
        if scope in ("district", "city") and addresses:
            scope_address_conflicts["%s_with_addresses" % scope] += 1
        if scope == "house" and len(addresses) > 1:
            scope_address_conflicts["house_with_many_addresses"] += 1

        event_sources = event.get("sources") or []
        if not event_sources:
            empty_sources += 1
        seen_source_ids = set()
        for source_ref in event_sources:
            source_id = source_ref.get("source_id")
            source_ids_used[source_id] += 1
            if source_id not in source_id_set:
                source_ref_missing += 1
            if source_id in seen_source_ids:
                source_ref_dupe_in_event += 1
            seen_source_ids.add(source_id)
            if source_ref.get("published_at") is None:
                published_null += 1
            url = source_ref.get("url") or ""
            match = CARD_RE.search(url)
            if match:
                card_ids.add(int(match.group(1)))
            else:
                url_parse_miss += 1

        start_key = start_raw if isinstance(start_raw, str) else ""
        end_planned_key = event.get("end_planned") or ""
        end_actual_key = event.get("end_actual") or ""
        raw_key = raw_addresses if isinstance(raw_addresses, str) else ""
        exact_fp[(event.get("type"), event.get("kind"), start_key,
                  end_planned_key, end_actual_key, raw_key)] += 1
        tight_fp[(event.get("type"), start_key, end_planned_key, end_actual_key)] += 1
        addr_fp[(event.get("type"), raw_key)] += 1

        links = event.get("houses") or []
        if links:
            events_by_house_link += 1
        seen_houses = set()
        for link in links:
            links_total += 1
            house_id = link.get("house_id")
            match_kind = link.get("match")
            link_match_counts[match_kind] += 1
            if house_id not in house_by_id:
                link_house_missing += 1
            if house_id in seen_houses:
                link_duplicate_in_event += 1
            seen_houses.add(house_id)
            if house_id in house_by_id:
                links_per_house[house_id]["total"] += 1
                if match_kind in ("exact", "range", "street"):
                    links_per_house[house_id][match_kind] += 1
                linked_events_per_house[house_id].add(ev_id)
                house_types_per_house[house_id][event.get("type")] += 1
                if duration is not None:
                    house_raw_duration_by_basis[house_id][basis] += float(duration)
                else:
                    house_duration_unknown_links[house_id] += 1
                if affected is None:
                    house_n_unknown_links[house_id] += 1
                else:
                    house_n_known_links[house_id] += 1
                if match_kind == "exact" and house_address_norm[house_id] not in address_norms:
                    link_addr_missing += 1
                    if len(link_samples) < 5:
                        link_samples.append(
                            {"event_id": ev_id, "house_id": house_id,
                             "issue": "exact_link_address_not_in_addresses"}
                        )
        for house_id, address_norm in house_address_norm.items():
            if not address_norm:
                continue
            if address_norm in address_norms and house_id not in seen_houses:
                event_address_present_but_no_link += 1
                if len(addr_without_link_samples) < 5:
                    addr_without_link_samples.append(
                        {"event_id": ev_id, "house_id": house_id}
                    )

    report["events"] = {
        "count": len(events),
        "unique_ids": len(event_ids),
        "duplicate_ids": {str(key): value for key, value in event_ids.items() if value > 1},
        "by_type": dict(sorted(type_counts.items())),
        "by_kind": dict(sorted(kind_counts.items())),
        "by_scope": dict(sorted(scope_counts.items())),
        "force_majeure": {"true": force_counts.get(True, 0),
                          "false": force_counts.get(False, 0)},
        "by_district": dict(sorted(district_counts.items())),
        "by_duration_basis": dict(sorted(basis_counts.items())),
        "events_without_end_planned": end_planned_null,
        "events_without_end_actual": end_actual_null,
        "events_without_duration": dur_unknown_events,
        "events_without_cause": cause_null,
        "events_without_organization": organization_null,
        "events_without_notes": notes_null,
        "events_without_addresses": addresses_empty,
        "events_without_districts": districts_empty,
        "events_with_houses_affected_null": houses_affected_null,
        "events_with_houses_affected_zero": houses_affected_zero,
        "events_with_houses_affected_negative": houses_affected_negative,
        "events_with_negative_duration": len(negative_durations),
        "events_with_end_before_start": len(ends_before_start),
        "events_starting_outside_period": len(starts_outside_period),
        "events_starting_after_generated_at": len(starts_after_generated),
        "date_time_offsets_hours": dict(sorted(offsets.items())),
        "date_time_parse_failures": parse_failures[:10],
        "start_min": iso(min(starts)) if starts else None,
        "start_max": iso(max(starts)) if starts else None,
        "starts_outside_period_sample": starts_outside_period[:5],
        "starts_after_generated_sample": starts_after_generated[:5],
    }

    report["durations"] = {
        "tolerance_hours": DUR_TOL,
        "contract_tolerance_hours": CONTRACT_DUR_TOL,
        "compared": duration_checks["compared"],
        "matching_within_tolerance": duration_checks["exact_within_tol"],
        "off_by_2dp_rounding": duration_checks["off_by_rounding_2dp"],
        "gross_mismatch": duration_checks["gross_mismatch"],
        "max_abs_diff_hours": round(duration_checks["max_abs_diff"], 9),
        "samples": duration_checks["samples"],
        "basis_vs_endpoints": {
            "%s|end_actual=%s|end_planned=%s" % key: value
            for key, value in sorted(basis_matrix.items(), key=lambda item: str(item[0]))
        },
        "stored_duration_by_basis": {
            basis: {
                "count": len(values),
                "min": round(min(values), 6) if values else None,
                "max": round(max(values), 6) if values else None,
            }
            for basis, values in sorted(durations_by_basis.items())
        },
    }

    compared_events = sum(counter_mismatch.values())
    report["addresses_vs_counter"] = {
        "events_compared": compared_events,
        "events_with_mismatch": counter_mismatch_events,
        "delta_histogram": delta_histogram(counter_mismatch),
        "events_addresses_more_than_counter": addresses_more_than_counter,
        "scope_conflicts": dict(sorted(scope_address_conflicts.items())),
        "kind_note": "delta = len(addresses) - houses_affected",
    }

    report["house_links"] = {
        "events_with_links": events_by_house_link,
        "links_total": links_total,
        "links_by_match": dict(sorted(link_match_counts.items())),
        "links_to_unknown_house": link_house_missing,
        "duplicate_house_refs_in_event": link_duplicate_in_event,
        "exact_link_address_not_in_addresses": link_addr_missing,
        "address_present_without_link": event_address_present_but_no_link,
        "link_issue_samples": link_samples[:5] + addr_without_link_samples[:5],
        "duplicate_address_strings_in_event": address_dupe_in_event,
    }

    report["source_refs"] = {
        "sources_declared": len(sources),
        "events_without_sources": empty_sources,
        "source_refs_total": sum(source_ids_used.values()),
        "source_refs_to_unknown_source": source_ref_missing,
        "duplicate_source_refs_in_event": source_ref_dupe_in_event,
        "source_ids_used": dict(sorted(source_ids_used.items())),
        "published_at_null_refs": published_null,
        "published_at_null_share": (
            round(published_null / sum(source_ids_used.values()), 6)
            if sum(source_ids_used.values()) else None
        ),
        "card_ids_unique": len(card_ids),
        "card_id_min": min(card_ids) if card_ids else None,
        "card_id_max": max(card_ids) if card_ids else None,
        "card_id_span_width": (max(card_ids) - min(card_ids) + 1) if card_ids else None,
        "card_id_missing_in_span": (
            (max(card_ids) - min(card_ids) + 1 - len(card_ids)) if card_ids else None
        ),
        "card_id_share_of_span": (
            round(len(card_ids) / (max(card_ids) - min(card_ids) + 1), 6)
            if card_ids else None
        ),
        "url_without_card_id": url_parse_miss,
    }
    if claimed_ranges and card_ids:
        lo = min(span[0] for span in claimed_ranges)
        hi = max(span[1] for span in claimed_ranges)
        inside = {card for card in card_ids if lo <= card <= hi}
        report["source_refs"]["claimed_card_range"] = [lo, hi]
        report["source_refs"]["claimed_range_width"] = hi - lo + 1
        report["source_refs"]["card_ids_inside_claimed_range"] = len(inside)
        report["source_refs"]["claimed_range_missing"] = hi - lo + 1 - len(inside)

    report["duplicate_fingerprints"] = [
        fingerprint_summary(exact_fp, "exact", by_id),
        fingerprint_summary(tight_fp, "tight", by_id),
        fingerprint_summary(addr_fp, "addresses_raw+type", by_id),
    ]

    overlap_pairs = 0
    overlap_samples = []
    groups = defaultdict(list)
    for event in events:
        if not isinstance(event.get("addresses_raw"), str):
            continue
        groups[(event.get("type"), event.get("addresses_raw"))].append(event)
    for group in groups.values():
        if len(group) < 2 or len(group) > 40:
            continue
        windows = []
        for event in group:
            start = parse_dt(event.get("start"))
            end = parse_dt(event.get("end_actual")) or parse_dt(event.get("end_planned"))
            if start is None or end is None or end < start:
                continue
            windows.append((start, end, event.get("id")))
        for i in range(len(windows)):
            for j in range(i + 1, len(windows)):
                first, second = windows[i], windows[j]
                if max(first[0], second[0]) < min(first[1], second[1]):
                    overlap_pairs += 1
                    if len(overlap_samples) < 5:
                        overlap_samples.append([first[2], second[2]])
    report["potential_continuations"] = {
        "method": (
            "same (type, addresses_raw) group, overlapping [start, end) windows, "
            "group size 2..40"
        ),
        "overlapping_pairs": overlap_pairs,
        "groups_scanned": sum(1 for group in groups.values() if 2 <= len(group) <= 40),
        "sample_pairs": overlap_samples,
        "note": "counts only; nothing merged, no data repaired",
    }

    day_counts = Counter()
    first_day_min_start = None
    last_day_max_start = None
    for event in events:
        start = parse_dt(event.get("start"))
        if start is None:
            continue
        day_counts[start.date()] += 1
        if period_from and start.date() == period_from.date():
            if first_day_min_start is None or start < first_day_min_start:
                first_day_min_start = start
        if period_to and start.date() == period_to.date():
            if last_day_max_start is None or start > last_day_max_start:
                last_day_max_start = start

    period_days = report["meta"]["period_days_inclusive"]
    per_type_span = {}
    for outage_type in enums["outage_type"]:
        typed = [parse_dt(event.get("start")) for event in events
                 if event.get("type") == outage_type]
        typed = [value for value in typed if value is not None]
        per_type_span[outage_type] = {
            "count": type_counts.get(outage_type, 0),
            "first_start": iso(min(typed)) if typed else None,
            "last_start": iso(max(typed)) if typed else None,
            "distinct_days": len({value.date() for value in typed}),
        }

    report["coverage"] = {
        "period_days": period_days,
        "days_with_events": len(day_counts),
        "days_without_events": (
            period_days - len(day_counts) if period_days is not None else None
        ),
        "first_period_day_min_start": iso(first_day_min_start),
        "first_period_day_events": (
            day_counts.get(period_from.date(), 0) if period_from else None
        ),
        "last_period_day_events": (
            day_counts.get(period_to.date(), 0) if period_to else None
        ),
        "last_period_day_max_start": iso(last_day_max_start),
        "per_type": per_type_span,
        "declared_source_spans_equal_period": (
            all(source.get("covered_from") == period.get("from")
                and source.get("covered_to") == period.get("to")
                for source in sources) if sources else None
        ),
        "sources_with_null_span": sum(
            1 for source in sources
            if source.get("covered_from") is None or source.get("covered_to") is None
        ),
        "note": "declared source spans are not evidence of continuous coverage",
    }
    house_props = list(schema["properties"]["houses"]["items"]["properties"].keys())
    passport_fields = [
        name for name in house_props
        if name not in ("id", "address", "district", "services", "is_control",
                        "passport_source_url")
    ]

    district_house_counts = Counter()
    service_state = {category: Counter() for category in service_categories}
    passport_null_counts = Counter()
    per_house = []
    service_agreement = Counter()

    for house in houses:
        house_id = house.get("id")
        services = house.get("services") or {}
        district_house_counts[house.get("district")] += 1
        null_fields = sum(1 for field in passport_fields if house.get(field) is None)
        passport_null_counts[null_fields] += 1
        for category in service_state:
            service_state[category][services.get(category)] += 1
        for category in service_categories:
            central = services.get(category) == "central"
            has_event = house_types_per_house[house_id].get(category, 0) > 0
            service_agreement[(category, central, has_event)] += 1
        per_house.append({
            "house_id": house_id,
            "district": house.get("district"),
            "is_control": house.get("is_control"),
            "passport_null_fields_of": [null_fields, len(passport_fields)],
            "passport_source_url_null": house.get("passport_source_url") is None,
            "services": services,
            "linked_events": len(linked_events_per_house[house_id]),
            "links": links_per_house[house_id]["total"],
            "links_exact": links_per_house[house_id]["exact"],
            "links_range": links_per_house[house_id]["range"],
            "links_street": links_per_house[house_id]["street"],
            "event_types": dict(sorted(house_types_per_house[house_id].items())),
            "raw_additive_hours_by_basis": {
                basis: round(value, 6)
                for basis, value in sorted(house_raw_duration_by_basis[house_id].items())
            },
            "links_with_unknown_duration": house_duration_unknown_links[house_id],
            "links_with_known_affected": house_n_known_links[house_id],
            "links_with_unknown_affected": house_n_unknown_links[house_id],
        })

    report["houses"] = {
        "count": len(houses),
        "unique_ids": len(house_by_id),
        "by_district": dict(sorted(district_house_counts.items())),
        "is_control_true": sum(1 for house in houses if house.get("is_control") is True),
        "is_control_false": sum(1 for house in houses if house.get("is_control") is False),
        "houses_with_zero_links": sum(
            1 for house in houses if links_per_house[house.get("id")]["total"] == 0
        ),
        "service_state_counts": {
            category: dict(sorted(states.items()))
            for category, states in service_state.items()
        },
        "passport_null_fields_histogram": delta_histogram(passport_null_counts),
        "passport_source_url_null": sum(
            1 for house in houses if house.get("passport_source_url") is None
        ),
        "service_central_vs_event_presence": {
            "%s|central=%s|has_event=%s" % key: value
            for key, value in sorted(service_agreement.items(), key=lambda item: str(item[0]))
        },
        "per_house": per_house,
        "note": "raw_additive_hours is an unclipped sum of stored durations, not a rating input",
    }

    kind_counts_local = kind_counts
    exact_links = link_match_counts.get("exact", 0)
    ambiguous_links = link_match_counts.get("range", 0) + link_match_counts.get("street", 0)
    report["method_feasibility"] = {
        "city_total_houses": city_houses.get("total"),
        "city_baselines_available": city_houses.get("total") is not None,
        "heating_season_available": meta.get("heating_season_start") is not None,
        "service_states_fully_known_houses": sum(
            1 for house in houses
            if all((house.get("services") or {}).get(category)
                   in ("central", "individual", "none")
                   for category in service_categories)
        ),
        "houses_with_any_unknown_service": sum(
            1 for house in houses
            if any((house.get("services") or {}).get(category) == "unknown"
                   for category in service_categories)
        ),
        "control_houses": sum(1 for house in houses if house.get("is_control") is True),
        "exact_links": exact_links,
        "ambiguous_links": ambiguous_links,
        "events_with_known_weight": (kind_counts_local.get("emergency", 0)
                                     + kind_counts_local.get("planned", 0)),
        "events_with_unknown_weight": kind_counts_local.get("unknown", 0),
        "events_with_unknown_houses_affected": houses_affected_null,
        "events_with_unknown_duration": dur_unknown_events,
        "events_with_all_three_ingredients_known": sum(
            1 for event in events
            if event.get("kind") in ("emergency", "planned")
            and event.get("houses_affected") is not None
            and event.get("duration_hours") is not None
        ),
        "note": "no scores, ratios or proxy values computed; availability counts only",
    }

    midnight_starts = 0
    midnight_by_type = Counter()
    delta_bands = Counter()
    negative_delta_samples = []
    large_positive_samples = []
    for event in events:
        start = parse_dt(event.get("start"))
        if start is not None and (start.hour, start.minute, start.second) == (0, 0, 0):
            midnight_starts += 1
            midnight_by_type[event.get("type")] += 1
        affected = event.get("houses_affected")
        if affected is None:
            continue
        delta = len(event.get("addresses") or []) - affected
        if delta == 0:
            delta_bands["zero"] += 1
        elif 0 < delta <= 9:
            delta_bands["1..9"] += 1
        elif delta >= 10:
            delta_bands["10+"] += 1
        else:
            delta_bands["negative"] += 1
        if delta < 0 and len(negative_delta_samples) < 10:
            negative_delta_samples.append({
                "event_id": event.get("id"),
                "scope": event.get("scope"),
                "houses_affected": affected,
                "addresses_parsed": len(event.get("addresses") or []),
            })
        if delta >= 10 and len(large_positive_samples) < 10:
            large_positive_samples.append({
                "event_id": event.get("id"),
                "scope": event.get("scope"),
                "houses_affected": affected,
                "addresses_parsed": len(event.get("addresses") or []),
            })
    report["extra_checks"] = {
        "starts_at_midnight_0000": midnight_starts,
        "starts_at_midnight_by_type": dict(sorted(midnight_by_type.items())),
        "start_midnight_share": (round(midnight_starts / len(events), 6) if events else None),
        "delta_bands_vs_meta_claim": dict(sorted(delta_bands.items())),
        "negative_delta_samples": negative_delta_samples,
        "large_positive_delta_samples": large_positive_samples,
        "links_with_unknown_duration_total": sum(house_duration_unknown_links.values()),
        "links_with_unknown_affected_total": sum(house_n_unknown_links.values()),
        "events_scoped_house_single_address": sum(
            1 for event in events
            if event.get("scope") == "house" and len(event.get("addresses") or []) == 1
        ),
        "events_scoped_group": sum(1 for event in events if event.get("scope") == "group"),
        "houses_with_any_unknown_weight_link": sum(
            1 for house in houses
            if any(event.get("kind") == "unknown"
                   for event in events
                   for link in (event.get("houses") or [])
                   if link.get("house_id") == house.get("id"))
        ),
        "houses_with_any_planned_link": sum(
            1 for house in houses
            if any(event.get("kind") == "planned"
                   for event in events
                   for link in (event.get("houses") or [])
                   if link.get("house_id") == house.get("id"))
        ),
        "sample_house_links_by_event_kind": {
            kind: sum(1 for event in events for _ in (event.get("houses") or [])
                      if event.get("kind") == kind)
            for kind in enums["kind"]
        },
        "sample_house_links_by_basis": {
            basis: sum(1 for event in events for _ in (event.get("houses") or [])
                       if event.get("duration_basis") == basis)
            for basis in enums["duration_basis"]
        },
    }
    return report


def fp_of(event, label):
    start_key = event.get("start") if isinstance(event.get("start"), str) else ""
    raw_key = (event.get("addresses_raw")
               if isinstance(event.get("addresses_raw"), str) else "")
    if label == "exact":
        return (event.get("type"), event.get("kind"), start_key,
                event.get("end_planned") or "", event.get("end_actual") or "", raw_key)
    if label == "tight":
        return (event.get("type"), start_key,
                event.get("end_planned") or "", event.get("end_actual") or "")
    return (event.get("type"), raw_key)


def fingerprint_summary(counter, label, by_id, sample_limit=8):
    groups = [key for key, count in counter.items() if count > 1]
    sizes = sorted((counter[key] for key in groups), reverse=True)
    samples = []
    for key in groups[:sample_limit]:
        ids = [ev_id for ev_id, event in by_id.items() if fp_of(event, label) == key]
        samples.append(sorted(str(ev_id) for ev_id in ids))
    return {
        "fingerprint": label,
        "duplicate_groups": len(groups),
        "events_in_duplicate_groups": sum(sizes),
        "max_group_size": sizes[0] if sizes else 0,
        "group_size_histogram": delta_histogram(Counter(sizes)),
        "sample_groups_event_ids": samples,
        "note": "counts only; no merging performed",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="read-only dataset inspection")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    report = inspect(args.dataset, args.schema)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text + "\n")

    structural = report["schema_validation"]["stdlib"]
    jsonschema_result = report["schema_validation"]["jsonschema"]
    print("dataset: houses=%d events=%d sources=%d sha256=%s"
          % (report["json"]["houses_count"], report["json"]["events_count"],
             report["json"]["sources_count"], report["input"]["sha256"][:16]))
    print("json: duplicate_keys=%d nonfinite=%d bom=%s"
          % (report["json"]["duplicate_object_key_count"],
             len(report["json"]["nonfinite_tokens"]), report["input"]["utf8_bom"]))
    print("schema-stdlib: violations=%d codes=%s"
          % (structural["total_violations"], structural["violations_by_code"]))
    print("schema-jsonschema: available=%s errors=%s"
          % (jsonschema_result["available"], jsonschema_result.get("total_errors")))
    print("events: types=%s kinds=%s scopes=%s"
          % (report["events"]["by_type"], report["events"]["by_kind"],
             report["events"]["by_scope"]))
    print("unknowns: no_end_planned=%d no_end_actual=%d no_duration=%d no_affected=%d "
          "no_addresses=%d no_org=%d no_cause=%d"
          % (report["events"]["events_without_end_planned"],
             report["events"]["events_without_end_actual"],
             report["events"]["events_without_duration"],
             report["events"]["events_with_houses_affected_null"],
             report["events"]["events_without_addresses"],
             report["events"]["events_without_organization"],
             report["events"]["events_without_cause"]))
    durations = report["durations"]
    print("durations: compared=%d ok=%d rounded2dp=%d gross=%d max_diff=%s"
          % (durations["compared"], durations["matching_within_tolerance"],
             durations["off_by_2dp_rounding"], durations["gross_mismatch"],
             durations["max_abs_diff_hours"]))
    print("house-links: links=%d events=%d match=%s unknown_house=%d"
          % (report["house_links"]["links_total"], report["house_links"]["events_with_links"],
             report["house_links"]["links_by_match"],
             report["house_links"]["links_to_unknown_house"]))
    print("sources: refs=%d unknown_ref=%d cards=%d span=%s missing=%s published_null=%d"
          % (report["source_refs"]["source_refs_total"],
             report["source_refs"]["source_refs_to_unknown_source"],
             report["source_refs"]["card_ids_unique"],
             report["source_refs"]["card_id_span_width"],
             report["source_refs"]["card_id_missing_in_span"],
             report["source_refs"]["published_at_null_refs"]))
    print("counter-vs-addresses: events_with_mismatch=%d delta_hist=%s"
          % (report["addresses_vs_counter"]["events_with_mismatch"],
             report["addresses_vs_counter"]["delta_histogram"]))
    print("duplicates: %s"
          % [(item["fingerprint"], item["duplicate_groups"],
              item["events_in_duplicate_groups"])
             for item in report["duplicate_fingerprints"]])
    print("continuations: overlapping_pairs=%d"
          % report["potential_continuations"]["overlapping_pairs"])
    print("coverage: days_with=%s days_without=%s per_type=%s"
          % (report["coverage"]["days_with_events"],
             report["coverage"]["days_without_events"],
             {key: value["count"] for key, value in report["coverage"]["per_type"].items()}))
    print("houses: count=%d control=%d zero_links=%d passport_all_null=%s"
          % (report["houses"]["count"], report["houses"]["is_control_true"],
             report["houses"]["houses_with_zero_links"],
             report["houses"]["passport_null_fields_histogram"].get("7")))
    print("feasibility: baselines=%s heating=%s exact_links=%d ambiguous_links=%d "
          "all3_known=%d unknown_weight=%d"
          % (report["method_feasibility"]["city_baselines_available"],
             report["method_feasibility"]["heating_season_available"],
             report["method_feasibility"]["exact_links"],
             report["method_feasibility"]["ambiguous_links"],
             report["method_feasibility"]["events_with_all_three_ingredients_known"],
             report["method_feasibility"]["events_with_unknown_weight"]))
    if args.out:
        print("report: %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())