#!/usr/bin/env python3
"""Discover, validate, and persist public-data source endpoints by jurisdiction.

The module provides a reusable interface for locating official public-data sources
for a county or jurisdiction across common real-estate and geospatial categories.
It supports a lightweight local registry file so discoveries can be cached and
reused across runs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

SUPPORTED_CATEGORIES = {
    "assessor",
    "tax",
    "recorder",
    "gis",
    "flood",
    "zoning",
    "crime",
    "wetlands",
    "wildfire",
    "open_data",
    "market",
}

DEFAULT_CATEGORY = "assessor"


def normalize_category(category: str | None) -> str:
    """Normalize the requested category to a supported slug."""
    if not category:
        return DEFAULT_CATEGORY
    normalized = re.sub(r"[^a-z0-9]+", "_", category.lower()).strip("_")
    return normalized if normalized in SUPPORTED_CATEGORIES else DEFAULT_CATEGORY


def slugify(value: str) -> str:
    """Create a URL-safe slug from a string."""
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def infer_platform(url: str) -> str:
    """Infer the platform family used by a source URL."""
    lower_url = (url or "").lower()
    if "arcgis" in lower_url:
        return "arcgis"
    if "socrata" in lower_url:
        return "socrata"
    if "wms" in lower_url or "wfs" in lower_url:
        return "wms"
    if "tyler" in lower_url:
        return "tyler"
    if "beacon" in lower_url:
        return "beacon"
    if "schneider" in lower_url:
        return "schneider"
    if "/api/" in lower_url or lower_url.endswith("json") or lower_url.endswith("geojson"):
        return "rest"
    return "html"


def infer_access_method(url: str, platform: str | None = None) -> str:
    """Infer the access method for a source based on its platform."""
    resolved_platform = platform or infer_platform(url)
    access_methods = {
        "arcgis": "arcgis_rest",
        "socrata": "socrata_api",
        "wms": "wms",
        "tyler": "tyler_portal",
        "beacon": "beacon_portal",
        "schneider": "schneider_portal",
        "rest": "rest_api",
        "html": "html_portal",
    }
    return access_methods.get(resolved_platform, "html_portal")


def classify_officiality(url: str, source_name: str, county: str, state: str) -> bool:
    """Classify a source as an official government source when it looks governmental."""
    if not url:
        return False
    lower_url = (url + " " + source_name + " " + county + " " + state).lower()
    official_markers = (
        "gov",
        "county",
        "city",
        "town",
        "state",
        "municipal",
        "assessor",
        "tax",
        "recorder",
        "gis",
        "flood",
        "zoning",
        "wildfire",
        "wetlands",
    )
    return any(marker in lower_url for marker in official_markers)


def load_registry(registry_file: str | Path | None = None) -> dict[str, Any]:
    """Load a local registry JSON file if it exists; otherwise return an empty structure."""
    if not registry_file:
        return {"sources": [], "discoveries": [], "failures": []}

    path = Path(registry_file)
    if not path.exists():
        return {"sources": [], "discoveries": [], "failures": []}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"sources": [], "discoveries": [], "failures": []}


def save_registry(registry_file: str | Path | None, registry: Mapping[str, Any]) -> None:
    """Persist the registry to disk when a file path is supplied."""
    if not registry_file:
        return

    path = Path(registry_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")


def _build_candidate_sources(state: str, county: str, county_fips: str, category: str) -> list[dict[str, Any]]:
    """Build plausible official and alternate source candidates for a jurisdiction."""
    county_slug = slugify(county) or "county"
    state_slug = slugify(state) or "state"
    category_slug = category.lower()
    category_label = category.replace("_", " ").title()

    candidates: list[dict[str, Any]] = []

    official_url = f"https://{county_slug}.county.gov/{category_slug}"
    candidates.append(
        {
            "county_fips": county_fips,
            "category": category,
            "name": f"{county} {category_label} Portal",
            "url": official_url,
            "platform": infer_platform(official_url),
            "access_method": infer_access_method(official_url),
            "official": True,
            "confidence": 0.95,
            "metadata": {"state": state, "county": county, "source_type": "official"},
            "validated": False,
            "validated_at": None,
        }
    )

    alternate_url = f"https://data.{state_slug}.gov/{category_slug}/{county_slug}"
    candidates.append(
        {
            "county_fips": county_fips,
            "category": category,
            "name": f"{state} Open Data {category_label} Hub",
            "url": alternate_url,
            "platform": infer_platform(alternate_url),
            "access_method": infer_access_method(alternate_url),
            "official": False,
            "confidence": 0.72,
            "metadata": {"state": state, "county": county, "source_type": "alternate"},
            "validated": False,
            "validated_at": None,
        }
    )

    if category in {"assessor", "tax", "recorder"}:
        portal_url = f"https://{county_slug}.{state_slug}.gov/{category_slug}"
        candidates.append(
            {
                "county_fips": county_fips,
                "category": category,
                "name": f"{county} {category_label} Office",
                "url": portal_url,
                "platform": infer_platform(portal_url),
                "access_method": infer_access_method(portal_url),
                "official": True,
                "confidence": 0.9,
                "metadata": {"state": state, "county": county, "source_type": "official"},
                "validated": False,
                "validated_at": None,
            }
        )

    return candidates


def query_registry_sources(registry: Mapping[str, Any], county_fips: str, category: str) -> list[dict[str, Any]]:
    """Return cached sources for a county FIPS and category from the registry."""
    sources = registry.get("sources", [])
    if not isinstance(sources, list):
        return []
    return [
        source
        for source in sources
        if isinstance(source, dict)
        and source.get("county_fips") == county_fips
        and source.get("category") == category
    ]


def validate_source(source: Mapping[str, Any], timeout: int = 8) -> dict[str, Any]:
    """Validate a source endpoint and return the validation result."""
    url = str(source.get("url") or "")
    if not url:
        return {"validated": False, "status_code": None, "error": "missing_url"}

    try:
        response = requests.get(url, timeout=timeout, allow_redirects=True)
        status_code = response.status_code
        validated = 200 <= status_code < 400
        return {
            "validated": validated,
            "status_code": status_code,
            "error": None if validated else f"status_{status_code}",
        }
    except requests.RequestException as exc:  # pragma: no cover - network dependent
        return {"validated": False, "status_code": None, "error": str(exc)}


def discover_sources_for_jurisdiction(
    *,
    state: str,
    county: str,
    county_fips: str,
    category: str | None = None,
    registry_file: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Discover and validate sources for a jurisdiction and category."""
    resolved_category = normalize_category(category)
    registry = load_registry(registry_file)

    cached_sources = query_registry_sources(registry, county_fips, resolved_category)
    discovered_sources: list[dict[str, Any]] = []

    for source in cached_sources:
        validation = validate_source(source)
        enriched = dict(source)
        enriched["validated"] = validation["validated"]
        enriched["validation_error"] = validation["error"]
        enriched["validated_at"] = datetime.now(timezone.utc).isoformat()
        enriched["platform"] = source.get("platform") or infer_platform(str(source.get("url") or ""))
        enriched["access_method"] = source.get("access_method") or infer_access_method(
            str(source.get("url") or ""), enriched["platform"]
        )
        discovered_sources.append(enriched)

    if not discovered_sources or not any(source.get("validated") for source in discovered_sources):
        for candidate in _build_candidate_sources(state, county, county_fips, resolved_category):
            if not any(existing.get("url") == candidate["url"] for existing in discovered_sources):
                discovered_sources.append(candidate)

    discovered_sources.sort(
        key=lambda item: (
            0 if item.get("official") else 1,
            -float(item.get("confidence", 0.0)),
            str(item.get("url", "")),
        )
    )
    return discovered_sources


def process_address_payload(
    payload: Mapping[str, Any],
    *,
    category: str | None = None,
    registry_file: str | Path | None = None,
) -> dict[str, Any]:
    """Process an address payload and return structured source registry output."""
    state = str(payload.get("state") or "")
    county = str(payload.get("county") or "")
    county_fips = str(payload.get("county_fips") or "")
    resolved_category = normalize_category(category)

    registry = load_registry(registry_file)
    existing_sources = discover_sources_for_jurisdiction(
        state=state,
        county=county,
        county_fips=county_fips,
        category=resolved_category,
        registry_file=registry_file,
    )

    primary = next((source for source in existing_sources if source.get("official")), None)
    alternates = [source for source in existing_sources if source is not primary]

    discoveries: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for source in existing_sources:
        if source.get("validated"):
            discoveries.append(source)
        else:
            failures.append(
                {
                    "name": source.get("name") or source.get("url"),
                    "url": source.get("url"),
                    "category": source.get("category"),
                    "platform": source.get("platform"),
                    "access_method": source.get("access_method"),
                    "official": source.get("official"),
                    "confidence": source.get("confidence"),
                    "validation_error": source.get("validation_error"),
                }
            )

    registry.setdefault("sources", [])
    registry.setdefault("discoveries", [])
    registry.setdefault("failures", [])

    for source in existing_sources:
        if not any(existing.get("url") == source.get("url") for existing in registry["sources"]):
            registry["sources"].append(source)

    registry["discoveries"] = discoveries
    registry["failures"] = failures
    registry["last_updated"] = datetime.now(timezone.utc).isoformat()
    save_registry(registry_file, registry)

    return {
        "state": state,
        "county": county,
        "county_fips": county_fips,
        "category": resolved_category,
        "primary": primary or {},
        "alternates": alternates,
        "discoveries": discoveries,
        "failures": failures,
        "registry_file": str(registry_file) if registry_file else None,
    }


def _read_input_json(input_value: str | None) -> dict[str, Any]:
    """Read structured JSON from a file path or an inline JSON string."""
    if not input_value:
        return {}

    candidate = Path(input_value)
    if candidate.exists():
        return json.loads(candidate.read_text(encoding="utf-8"))

    return json.loads(input_value)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Discover public-data sources for a jurisdiction")
    parser.add_argument("input", nargs="?", help="JSON file or inline JSON payload")
    parser.add_argument("--category", default=DEFAULT_CATEGORY, help="Source category")
    parser.add_argument("--registry-file", help="Optional registry JSON file")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print the JSON output")
    args = parser.parse_args(argv)

    payload = _read_input_json(args.input) if args.input else {}
    result = process_address_payload(payload, category=args.category, registry_file=args.registry_file)

    if args.pretty:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
