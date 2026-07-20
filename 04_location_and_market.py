# plugins/location_market.py
"""
Plugin: Location & Market Context
Purpose: Retrieve FEMA flood data and lightweight location/market context
         using verified sources from the source-registry plugin.

This is a condensed, pipeline-ready version of your original script.
All CLI, file I/O, argparse, dynamic module loading, and JSON handling
have been removed. The plugin exposes a single entrypoint:
    get_location_and_market(payload, category, registry_output)
"""

from datetime import datetime, timezone
from typing import Any, Mapping
import requests

from plugins.source_registry import get_sources_for_jurisdiction


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def normalize_result(value: Any, *, source: Mapping[str, Any] | None = None, source_name: str | None = None) -> dict[str, Any]:
    return {
        "value": value,
        "source": source_name or (source.get("name") if source else None),
        "source_url": source.get("url") if source else None,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


# ------------------------------------------------------------
# FEMA NFHL Flood Data
# ------------------------------------------------------------

def parse_fema_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    features = payload.get("features") or []
    if not features:
        return {}
    attrs = features[0].get("attributes") or {}
    return {
        "flood_zone": attrs.get("FLD_ZONE") or attrs.get("fld_zone"),
        "floodway": attrs.get("ZONE_SUBTY") or attrs.get("zone_subty") or attrs.get("ZONE_SUBTY_1"),
        "flood_panel": attrs.get("PANEL") or attrs.get("panel"),
        "flood_map_effective_date": attrs.get("SOURCE_DATA_DATE") or attrs.get("source_data_date"),
    }


def fetch_fema_flood_data(lat: float | None, lon: float | None) -> dict[str, Any]:
    if lat is None or lon is None:
        return {}
    url = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/0/query"
    params = {
        "where": "1=1",
        "geometryType": "esriGeometryPoint",
        "geometry": f"{lon},{lat}",
        "inSR": "4326",
        "outSR": "4326",
        "f": "json",
    }
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        return parse_fema_payload(r.json())
    except Exception:
        return {}


# ------------------------------------------------------------
# Main plugin entrypoint
# ------------------------------------------------------------

def get_location_and_market(payload: Mapping[str, Any], category: str = "gis", registry_output: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """
    Plugin entrypoint.
    Retrieves FEMA flood data and lightweight location/market context.

    Inputs:
        payload: normalized address payload
        category: typically "gis"
        registry_output: optional output from source_registry plugin

    Returns:
        {
            "location_risks": {...},
            "market_snapshot": {...},
            "nearby_sales": [...],
            "sources": [...],
            "retrieved_at": ...,
            "confidence": float,
            "missing_data": bool,
        }
    """

    # Prefer registry-provided discoveries
    sources = []
    if registry_output:
        discoveries = registry_output.get("discoveries") or []
        if isinstance(discoveries, list):
            sources = [s for s in discoveries if isinstance(s, dict)]

    # If no registry sources, ask the plugin directly
    if not sources:
        sources_info = get_sources_for_jurisdiction(payload, category)
        sources = sources_info.get("discoveries", [])

    now = datetime.now(timezone.utc).isoformat()

    # FEMA flood data
    lat = payload.get("latitude")
    lon = payload.get("longitude")
    fema = fetch_fema_flood_data(float(lat) if lat is not None else None,
                                 float(lon) if lon is not None else None)

    flood_zone_value = fema.get("flood_zone")
    floodway_value = fema.get("floodway")
    flood_panel_value = fema.get("flood_panel")
    flood_date_value = fema.get("flood_map_effective_date")

    location_risks = {
        "flood_zone": normalize_result(flood_zone_value, source_name="FEMA NFHL") if flood_zone_value else None,
        "floodway": normalize_result(floodway_value, source_name="FEMA NFHL") if floodway_value else None,
        "flood_panel": normalize_result(flood_panel_value, source_name="FEMA NFHL") if flood_panel_value else None,
        "flood_map_effective_date": normalize_result(flood_date_value, source_name="FEMA NFHL") if flood_date_value else None,
        "wetlands_proximity": None,
        "wildfire_exposure": None,
        "zoning": None,
        "protected_area": None,
        "crime_indicator": None,
    }

    market_snapshot = {
        "assessed_value": None,
        "automated_value": None,
        "recent_sales": None,
        "recent_activity": None,
        "active_listing_context": None,
    }

    nearby_sales = []

    # Infer additional risk indicators from source metadata
    for source in sources:
        name = source.get("name", "")
        url = source.get("url", "")

        if "wetland" in name.lower() or "wetland" in url.lower():
            location_risks["wetlands_proximity"] = normalize_result("unknown", source=source, source_name=name)

        if "wildfire" in name.lower() or "wildfire" in url.lower():
            location_risks["wildfire_exposure"] = normalize_result("unknown", source=source, source_name=name)

        if "zoning" in name.lower() or "zoning" in url.lower():
            location_risks["zoning"] = normalize_result("unknown", source=source, source_name=name)

        if "crime" in name.lower() or "crime" in url.lower():
            location_risks["crime_indicator"] = normalize_result("unknown", source=source, source_name=name)

        if "sale" in name.lower() or "sale" in url.lower():
            nearby_sales.append(normalize_result("unknown", source=source, source_name=name))

    result = {
        "location_risks": location_risks,
        "market_snapshot": market_snapshot,
        "nearby_sales": nearby_sales,
        "sources": [
            {
                "name": s.get("name"),
                "url": s.get("url"),
                "category": s.get("category"),
                "platform": s.get("platform"),
                "access_method": s.get("access_method"),
                "official": s.get("official"),
                "confidence": s.get("confidence"),
                "retrieved_at": now,
            }
            for s in sources
        ],
        "retrieved_at": now,
        "confidence": 0.5 if sources else 0.0,
        "missing_data": not bool(sources),
    }

    return result
