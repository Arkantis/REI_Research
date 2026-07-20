# plugins/public_records.py
"""
Plugin: Public Records Retrieval
Purpose: Retrieve and normalize authoritative public property records
         using verified sources from the source-registry plugin.

This is a condensed, pipeline-ready version of your original script.
All CLI, file I/O, argparse, dynamic module loading, and JSON handling
have been removed. The plugin exposes a single entrypoint:
    get_public_records(payload, category, registry_output)
"""

from datetime import datetime, timezone
from typing import Any, Mapping

import requests

# Import your plugin version of the source registry
from plugins.source_registry import get_sources_for_jurisdiction


# ------------------------------------------------------------
# Coercion helpers
# ------------------------------------------------------------

def coerce_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def coerce_number(value: Any) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        cleaned = value.replace(",", "").replace("$", "").strip()
        if cleaned:
            try:
                return float(cleaned)
            except ValueError:
                return None
    return None


# ------------------------------------------------------------
# Normalization of raw public-record payloads
# ------------------------------------------------------------

def normalize_public_record_payload(raw_payload: Mapping[str, Any], source: Mapping[str, Any] | None = None) -> dict[str, Any]:
    source_name = source.get("name") if source else None
    source_url = source.get("url") if source else None
    confidence = source.get("confidence") if source else None

    owner_values = raw_payload.get("owners") or []
    if not owner_values:
        owner_values = [raw_payload.get("owner") or raw_payload.get("owners")]

    normalized = {
        "parcel_apn": coerce_string(raw_payload.get("parcel") or raw_payload.get("apn") or raw_payload.get("parcel_id")),
        "situs_address": coerce_string(raw_payload.get("situs_address") or raw_payload.get("address") or raw_payload.get("site_address")),
        "legal_description": coerce_string(raw_payload.get("legal_description") or raw_payload.get("description")),
        "property_type": coerce_string(raw_payload.get("property_type") or raw_payload.get("use_code")),
        "owners": [coerce_string(owner) for owner in owner_values if coerce_string(owner)],
        "bedrooms": coerce_number(raw_payload.get("bedrooms")),
        "bathrooms": coerce_number(raw_payload.get("bathrooms")),
        "living_area": coerce_number(raw_payload.get("living_area") or raw_payload.get("sq_ft")),
        "lot_size": coerce_number(raw_payload.get("lot_size") or raw_payload.get("lot_area")),
        "year_built": coerce_number(raw_payload.get("year_built")),
        "improvements_features": raw_payload.get("improvements_features") or raw_payload.get("features") or [],
        "assessed_value": coerce_number(raw_payload.get("assessed_value") or raw_payload.get("assessed")),
        "taxable_value": coerce_number(raw_payload.get("taxable_value") or raw_payload.get("taxable")),
        "tax_history": raw_payload.get("tax_history") or [],
        "annual_taxes": coerce_number(raw_payload.get("annual_taxes") or raw_payload.get("tax_amount")),
        "exemptions": raw_payload.get("exemptions") or [],
        "tax_delinquency": raw_payload.get("tax_delinquency") or [],
        "ownership_transfers": raw_payload.get("ownership_transfers") or [],
        "recorded_deeds": raw_payload.get("recorded_deeds") or [],
        "mortgages": raw_payload.get("mortgages") or raw_payload.get("deeds_of_trust") or [],
        "releases": raw_payload.get("releases") or [],
        "liens_judgments": raw_payload.get("liens_judgments") or [],
        "trust_llc_probate_indicators": raw_payload.get("trust_llc_probate_indicators") or [],
        "source_attribution": {
            "source_name": source_name,
            "source_url": source_url,
            "confidence": confidence,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "confidence": confidence,
        "missing_fields": [],
    }

    expected_fields = [
        "parcel_apn", "situs_address", "legal_description", "property_type",
        "owners", "bedrooms", "bathrooms", "living_area", "lot_size",
        "year_built", "improvements_features", "assessed_value", "taxable_value",
        "tax_history", "annual_taxes", "exemptions", "tax_delinquency",
        "ownership_transfers", "recorded_deeds", "mortgages", "releases",
        "liens_judgments", "trust_llc_probate_indicators",
    ]

    for field in expected_fields:
        value = normalized.get(field)
        if value in (None, "", [], {}):
            normalized["missing_fields"].append(field)

    return normalized


# ------------------------------------------------------------
# Main plugin entrypoint
# ------------------------------------------------------------

def get_public_records(payload: Mapping[str, Any], category: str = "assessor", registry_output: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """
    Plugin entrypoint.
    Retrieves and normalizes public records using verified sources.

    Inputs:
        payload: normalized address payload
        category: assessor/tax/recorder/etc.
        registry_output: optional output from source_registry plugin

    Returns:
        {
            "state": ...,
            "county": ...,
            "county_fips": ...,
            "category": ...,
            "records": [...],
            "primary_record": {...},
            "retrieved_at": ...,
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

    if not sources:
        return {
            "state": str(payload.get("state") or ""),
            "county": str(payload.get("county") or ""),
            "county_fips": str(payload.get("county_fips") or ""),
            "category": category,
            "records": [],
            "primary_record": {},
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "missing_data": True,
        }

    # Build normalized records (placeholder raw payloads until real API integration)
    records = []
    for source in sources:
        raw_payload = {
            "parcel": payload.get("parcel_apn"),
            "situs_address": payload.get("normalized_address") or payload.get("street"),
            "owners": [payload.get("owner") or payload.get("owners")],
            "bedrooms": None,
            "bathrooms": None,
            "living_area": None,
            "assessed_value": None,
            "tax_history": [],
        }
        normalized = normalize_public_record_payload(raw_payload, source=source)
        records.append(normalized)

    return {
        "state": str(payload.get("state") or ""),
        "county": str(payload.get("county") or ""),
        "county_fips": str(payload.get("county_fips") or ""),
        "category": category,
        "records": records,
        "primary_record": records[0] if records else {},
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "missing_data": not bool(records),
    }
