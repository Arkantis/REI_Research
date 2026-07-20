# plugins/screening_report.py
"""
Plugin: Screening Report Builder
Purpose: Build a deterministic screening report from public-records
         and location/market plugin outputs.

This is a condensed, pipeline-ready version of your original script.
All CLI, file I/O, argparse, and JSON handling have been removed.
The plugin exposes a single entrypoint:
    get_screening_report(public_records, location_and_market, asking_price)
"""

from datetime import datetime, timezone
from typing import Any, Mapping


# ------------------------------------------------------------
# Coercion helpers
# ------------------------------------------------------------

def _coerce_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").replace("$", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _coerce_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def _flatten_sources(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    sources = []
    for section in ("public_records", "location_and_market"):
        section_value = payload.get(section, {})
        if isinstance(section_value, dict):
            section_sources = section_value.get("sources") or []
            if isinstance(section_sources, list):
                sources.extend([s for s in section_sources if isinstance(s, dict)])
    return sources


# ------------------------------------------------------------
# Main plugin entrypoint
# ------------------------------------------------------------

def get_screening_report(
    public_records: Mapping[str, Any] | None = None,
    location_and_market: Mapping[str, Any] | None = None,
    asking_price: float | None = None,
) -> dict[str, Any]:
    """
    Plugin entrypoint.
    Builds a deterministic screening report from structured inputs.

    Inputs:
        public_records: output from public_records plugin
        location_and_market: output from location_market plugin
        asking_price: optional asking price for valuation comparison

    Returns:
        A full screening report dict with flags, summaries, and recommendation.
    """

    public_records = public_records or {}
    location_and_market = location_and_market or {}

    records = public_records.get("records") or []
    primary_record = records[0] if records and isinstance(records[0], dict) else {}

    ownerships = primary_record.get("owners") or []
    assessed_value = _coerce_number(primary_record.get("assessed_value"))
    annual_taxes = _coerce_number(primary_record.get("annual_taxes"))
    mortgages = primary_record.get("mortgages") or []
    releases = primary_record.get("releases") or []
    liens = primary_record.get("liens_judgments") or []
    tax_delinquency = primary_record.get("tax_delinquency") or []
    ownership_transfer = primary_record.get("ownership_transfers") or []
    missing_fields = primary_record.get("missing_fields") or []

    location_risks = location_and_market.get("location_risks") or {}
    market_snapshot = location_and_market.get("market_snapshot") or {}

    flags = []

    def add_flag(code: str, description: str, severity: str = "warning"):
        flags.append({"code": code, "description": description, "severity": severity})

    # Ownership flags
    if len(ownerships) > 1:
        add_flag("multiple_owners", "Multiple owners were found in public records.")
    if ownership_transfer:
        add_flag("recent_ownership_transfer", "Recent ownership transfer activity was found.")

    # Encumbrance flags
    if mortgages and len(mortgages) > 1:
        add_flag("multiple_mortgages", "Multiple mortgages or deeds of trust were found.")
    if mortgages and not releases:
        add_flag("unreleased_mortgage", "Mortgage or deed of trust records appear unreleased.")
    if liens:
        add_flag("active_liens_or_judgments", "Active liens or judgments were found.")

    # Tax flags
    if tax_delinquency:
        add_flag("tax_delinquency", "Tax delinquency indicators were found.")

    # Location risk flags
    if location_risks.get("flood_zone"):
        add_flag("flood_zone_exposure", "Flood-zone exposure was identified.")
    if location_risks.get("wetlands_proximity"):
        add_flag("wetlands_risk", "Wetlands proximity was identified.")
    if location_risks.get("wildfire_exposure"):
        add_flag("wildfire_risk", "Wildfire exposure was identified.")
    if location_risks.get("protected_area"):
        add_flag("historic_or_protected_area", "Historic or protected-area restrictions were identified.")
    if location_risks.get("zoning"):
        add_flag("zoning_conflict", "Zoning or property-use information may conflict with intended use.")
    if location_risks.get("crime_indicator"):
        add_flag("high_crime_indicator", "A public crime or safety indicator was found.")

    # Missing data
    if missing_fields:
        add_flag("missing_critical_data", "Some critical data fields were missing.", severity="info")

    # Asking price vs assessed value
    if assessed_value and asking_price is not None and asking_price > assessed_value * 1.25:
        add_flag(
            "asking_price_above_public_value",
            "Asking price appears materially above available public valuation.",
            severity="warning",
        )

    # Recommendation
    if not primary_record and not location_and_market:
        recommendation = "deprioritize"
    elif flags:
        recommendation = "manual_review"
    else:
        recommendation = "proceed"

    now = datetime.now(timezone.utc).isoformat()

    report = {
        "executive_summary": {
            "recommendation": recommendation,
            "summary": "Deterministic screening review completed from available public records and location/market context.",
            "confidence": 0.6 if flags else 0.8,
        },
        "property_summary": {
            "parcel_apn": primary_record.get("parcel_apn"),
            "situs_address": primary_record.get("situs_address"),
            "property_type": primary_record.get("property_type"),
            "owners": ownerships,
        },
        "ownership_summary": {
            "owner_count": len(ownerships),
            "owners": ownerships,
            "recent_transfer": bool(ownership_transfer),
        },
        "tax_summary": {
            "assessed_value": assessed_value,
            "annual_taxes": annual_taxes,
            "tax_delinquency": bool(tax_delinquency),
        },
        "encumbrance_summary": {
            "mortgage_count": len(mortgages),
            "release_count": len(releases),
            "liens_or_judgments": bool(liens),
        },
        "location_summary": {
            "flood_zone": location_risks.get("flood_zone"),
            "wetlands_proximity": location_risks.get("wetlands_proximity"),
            "wildfire_exposure": location_risks.get("wildfire_exposure"),
            "protected_area": location_risks.get("protected_area"),
            "zoning": location_risks.get("zoning"),
            "crime_indicator": location_risks.get("crime_indicator"),
        },
        "market_snapshot": {
            "assessed_value": market_snapshot.get("assessed_value"),
            "automated_value": market_snapshot.get("automated_value"),
            "recent_sales": market_snapshot.get("recent_sales"),
            "recent_activity": market_snapshot.get("recent_activity"),
            "active_listing_context": market_snapshot.get("active_listing_context"),
        },
        "source_summary": {
            "sources": _flatten_sources({
                "public_records": public_records,
                "location_and_market": location_and_market,
            }),
        },
        "missing_or_unavailable_data": {
            "missing_fields": missing_fields,
            "missing_data": bool(missing_fields) or not bool(records),
        },
        "risk_flags": flags,
        "retrieved_at": now,
        "confidence": 0.6 if flags else 0.8,
        "missing_data": bool(missing_fields) or not bool(records),
    }

    return report
