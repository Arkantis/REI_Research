# plugins/source_registry.py
"""
Plugin: Source Registry
Purpose: Discover, validate, and return public-data source endpoints
         for a given jurisdiction (state, county, county_fips, category).

This is a condensed, pipeline-ready version of your original script.
All CLI, file I/O, registry persistence, argparse, and JSON loading
have been removed. The plugin now exposes a single entrypoint:
    get_sources_for_jurisdiction(payload, category)
"""

import re
import requests
from datetime import datetime, timezone

SUPPORTED_CATEGORIES = {
    "assessor", "tax", "recorder", "gis", "flood",
    "zoning", "crime", "wetlands", "wildfire",
    "open_data", "market",
}

DEFAULT_CATEGORY = "assessor"


# ------------------------------------------------------------
# Normalization helpers
# ------------------------------------------------------------

def normalize_category(category: str | None) -> str:
    if not category:
        return DEFAULT_CATEGORY
    normalized = re.sub(r"[^a-z0-9]+", "_", category.lower()).strip("_")
    return normalized if normalized in SUPPORTED_CATEGORIES else DEFAULT_CATEGORY


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def infer_platform(url: str) -> str:
    u = (url or "").lower()
    if "arcgis" in u:
        return "arcgis"
    if "socrata" in u:
        return "socrata"
    if "wms" in u or "wfs" in u:
        return "wms"
    if "tyler" in u:
        return "tyler"
    if "beacon" in u:
        return "beacon"
    if "schneider" in u:
        return "schneider"
    if "/api/" in u or u.endswith("json") or u.endswith("geojson"):
        return "rest"
    return "html"


def infer_access_method(url: str, platform: str | None = None) -> str:
    p = platform or infer_platform(url)
    mapping = {
        "arcgis": "arcgis_rest",
        "socrata": "socrata_api",
        "wms": "wms",
        "tyler": "tyler_portal",
        "beacon": "beacon_portal",
        "schneider": "schneider_portal",
        "rest": "rest_api",
        "html": "html_portal",
    }
    return mapping.get(p, "html_portal")


# ------------------------------------------------------------
# Candidate source builder
# ------------------------------------------------------------

def _build_candidate_sources(state: str, county: str, county_fips: str, category: str):
    county_slug = slugify(county) or "county"
    state_slug = slugify(state) or "state"
    category_slug = category.lower()
    category_label = category.replace("_", " ").title()

    candidates = []

    # Official county portal
    official_url = f"https://{county_slug}.county.gov/{category_slug}"
    candidates.append({
        "county_fips": county_fips,
        "category": category,
        "name": f"{county} {category_label} Portal",
        "url": official_url,
        "platform": infer_platform(official_url),
        "access_method": infer_access_method(official_url),
        "official": True,
        "confidence": 0.95,
        "validated": False,
        "validated_at": None,
    })

    # State open-data hub
    alternate_url = f"https://data.{state_slug}.gov/{category_slug}/{county_slug}"
    candidates.append({
        "county_fips": county_fips,
        "category": category,
        "name": f"{state} Open Data {category_label} Hub",
        "url": alternate_url,
        "platform": infer_platform(alternate_url),
        "access_method": infer_access_method(alternate_url),
        "official": False,
        "confidence": 0.72,
        "validated": False,
        "validated_at": None,
    })

    # Additional portal for assessor/tax/recorder
    if category in {"assessor", "tax", "recorder"}:
        portal_url = f"https://{county_slug}.{state_slug}.gov/{category_slug}"
        candidates.append({
            "county_fips": county_fips,
            "category": category,
            "name": f"{county} {category_label} Office",
            "url": portal_url,
            "platform": infer_platform(portal_url),
            "access_method": infer_access_method(portal_url),
            "official": True,
            "confidence": 0.9,
            "validated": False,
            "validated_at": None,
        })

    return candidates


# ------------------------------------------------------------
# Validation
# ------------------------------------------------------------

def validate_source(source: dict, timeout: int = 8) -> dict:
    url = str(source.get("url") or "")
    if not url:
        return {"validated": False, "status_code": None, "error": "missing_url"}

    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True)
        ok = 200 <= r.status_code < 400
        return {
            "validated": ok,
            "status_code": r.status_code,
            "error": None if ok else f"status_{r.status_code}",
        }
    except requests.RequestException as exc:
        return {"validated": False, "status_code": None, "error": str(exc)}


# ------------------------------------------------------------
# Main plugin entrypoint
# ------------------------------------------------------------

def get_sources_for_jurisdiction(payload: dict, category: str | None = None) -> dict:
    """
    Plugin entrypoint.
    Input payload must contain:
        state, county, county_fips
    Returns:
        {
            "state": ...,
            "county": ...,
            "county_fips": ...,
            "category": ...,
            "primary": {...},
            "alternates": [...],
            "discoveries": [...],
            "failures": [...],
        }
    """

    state = str(payload.get("state") or "")
    county = str(payload.get("county") or "")
    county_fips = str(payload.get("county_fips") or "")
    resolved_category = normalize_category(category)

    # Build candidates
    candidates = _build_candidate_sources(state, county, county_fips, resolved_category)

    # Validate each candidate
    validated_items = []
    failures = []

    for src in candidates:
        v = validate_source(src)
        enriched = dict(src)
        enriched["validated"] = v["validated"]
        enriched["validation_error"] = v["error"]
        enriched["validated_at"] = datetime.now(timezone.utc).isoformat()
        enriched["platform"] = src.get("platform") or infer_platform(src["url"])
        enriched["access_method"] = src.get("access_method") or infer_access_method(src["url"], enriched["platform"])

        if enriched["validated"]:
            validated_items.append(enriched)
        else:
            failures.append(enriched)

    # Sort by officiality + confidence
    validated_items.sort(
        key=lambda item: (
            0 if item.get("official") else 1,
            -float(item.get("confidence", 0.0)),
            str(item.get("url", "")),
        )
    )

    primary = validated_items[0] if validated_items else {}
    alternates = validated_items[1:] if len(validated_items) > 1 else []

    return {
        "state": state,
        "county": county,
        "county_fips": county_fips,
        "category": resolved_category,
        "primary": primary,
        "alternates": alternates,
        "discoveries": validated_items,
        "failures": failures,
    }
