#!/usr/bin/env python3
"""Normalize U.S. property addresses and enrich them with county and location data.

The script accepts either a single address string or an input file path. It supports
plain text addresses, CSV files, Excel workbooks, and ZIP archives containing those files.

Examples:
    python research/01_address_normalization.py "4202 Marc Ave., Edinburg, TX 78539"
    python research/01_address_normalization.py --pretty
    python research/01_address_normalization.py ./sample_addresses.csv --output ./normalized.json
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Iterable

import requests

try:
    import pandas as pd
except ImportError:  # pragma: no cover - optional dependency, handled gracefully
    pd = None


STATE_ABBREVIATIONS: dict[str, str] = {
    "AL": "AL",
    "ALABAMA": "AL",
    "AK": "AK",
    "ALASKA": "AK",
    "AZ": "AZ",
    "ARIZONA": "AZ",
    "AR": "AR",
    "ARKANSAS": "AR",
    "CA": "CA",
    "CALIFORNIA": "CA",
    "CO": "CO",
    "COLORADO": "CO",
    "CT": "CT",
    "CONNECTICUT": "CT",
    "DE": "DE",
    "DELAWARE": "DE",
    "FL": "FL",
    "FLORIDA": "FL",
    "GA": "GA",
    "GEORGIA": "GA",
    "HI": "HI",
    "HAWAII": "HI",
    "ID": "ID",
    "IDAHO": "ID",
    "IL": "IL",
    "ILLINOIS": "IL",
    "IN": "IN",
    "INDIANA": "IN",
    "IA": "IA",
    "IOWA": "IA",
    "KS": "KS",
    "KANSAS": "KS",
    "KY": "KY",
    "KENTUCKY": "KY",
    "LA": "LA",
    "LOUISIANA": "LA",
    "ME": "ME",
    "MAINE": "ME",
    "MD": "MD",
    "MARYLAND": "MD",
    "MA": "MA",
    "MASSACHUSETTS": "MA",
    "MI": "MI",
    "MICHIGAN": "MI",
    "MN": "MN",
    "MINNESOTA": "MN",
    "MS": "MS",
    "MISSISSIPPI": "MS",
    "MO": "MO",
    "MISSOURI": "MO",
    "MT": "MT",
    "MONTANA": "MT",
    "NE": "NE",
    "NEBRASKA": "NE",
    "NV": "NV",
    "NEVADA": "NV",
    "NH": "NH",
    "NEW HAMPSHIRE": "NH",
    "NJ": "NJ",
    "NEW JERSEY": "NJ",
    "NM": "NM",
    "NEW MEXICO": "NM",
    "NY": "NY",
    "NEW YORK": "NY",
    "NC": "NC",
    "NORTH CAROLINA": "NC",
    "ND": "ND",
    "NORTH DAKOTA": "ND",
    "OH": "OH",
    "OHIO": "OH",
    "OK": "OK",
    "OKLAHOMA": "OK",
    "OR": "OR",
    "OREGON": "OR",
    "PA": "PA",
    "PENNSYLVANIA": "PA",
    "RI": "RI",
    "RHODE ISLAND": "RI",
    "SC": "SC",
    "SOUTH CAROLINA": "SC",
    "SD": "SD",
    "SOUTH DAKOTA": "SD",
    "TN": "TN",
    "TENNESSEE": "TN",
    "TX": "TX",
    "TEXAS": "TX",
    "UT": "UT",
    "UTAH": "UT",
    "VT": "VT",
    "VERMONT": "VT",
    "VA": "VA",
    "VIRGINIA": "VA",
    "WA": "WA",
    "WASHINGTON": "WA",
    "WV": "WV",
    "WEST VIRGINIA": "WV",
    "WI": "WI",
    "WISCONSIN": "WI",
    "WY": "WY",
    "WYOMING": "WY",
    "DC": "DC",
    "DISTRICT OF COLUMBIA": "DC",
}

STREET_SUFFIXES: dict[str, str] = {
    "ST": "ST",
    "STREET": "ST",
    "RD": "RD",
    "ROAD": "RD",
    "AVE": "AVE",
    "AVENUE": "AVE",
    "BLVD": "BLVD",
    "BOULEVARD": "BLVD",
    "PKWY": "PKWY",
    "PARKWAY": "PKWY",
    "DR": "DR",
    "DRIVE": "DR",
    "LN": "LN",
    "LANE": "LN",
    "CT": "CT",
    "COURT": "CT",
    "CIR": "CIR",
    "CIRCLE": "CIR",
    "TRAIL": "TRL",
    "TRL": "TRL",
    "PL": "PL",
    "PLACE": "PL",
    "WAY": "WAY",
    "TER": "TER",
    "TERRACE": "TER",
    "HWY": "HWY",
    "HIGHWAY": "HWY",
    "EXPY": "EXPY",
    "EXPRESSWAY": "EXPY",
    "PIKE": "PIKE",
    "PIKE": "PIKE",
}


def collapse_whitespace(text: str) -> str:
    """Collapse repeated whitespace and strip surrounding spaces."""
    return re.sub(r"\s+", " ", text).strip()


def split_street_parts(street: str) -> tuple[str, str]:
    """Split a street into a street number and a street name."""
    cleaned = collapse_whitespace(street)
    if not cleaned:
        return "", ""

    tokens = cleaned.split()
    if not tokens:
        return "", ""

    first_token = tokens[0].upper()
    if re.fullmatch(r"\d{1,6}[A-Z]?", first_token):
        return tokens[0], " ".join(tokens[1:])

    return "", cleaned


def normalize_street_name(street_name: str) -> str:
    """Normalize a street name component using common U.S. abbreviations."""
    street_name = collapse_whitespace(street_name).upper()
    tokens = street_name.split()
    if not tokens:
        return ""

    normalized_tokens: list[str] = []
    for token in tokens:
        token_clean = re.sub(r"[^A-Z0-9]", "", token)
        if token_clean in STREET_SUFFIXES:
            normalized_tokens.append(STREET_SUFFIXES[token_clean])
        else:
            normalized_tokens.append(token_clean)

    if not normalized_tokens:
        return ""

    result_tokens = [token if token.isdigit() else token.title() for token in normalized_tokens]
    return " ".join(result_tokens)


def normalize_street(street: str) -> str:
    """Normalize a street component using common U.S. abbreviations."""
    street_number, street_name = split_street_parts(street)
    if street_number and street_name:
        return f"{street_number} {normalize_street_name(street_name)}".strip()
    if street_number:
        return street_number
    return normalize_street_name(street_name)


def normalize_state(state: str) -> str:
    """Normalize a U.S. state name or abbreviation to a two-letter code."""
    normalized = collapse_whitespace(state).upper()
    return STATE_ABBREVIATIONS.get(normalized, normalized[:2].upper())


def normalize_zip(zip_code: str) -> str:
    """Normalize a ZIP code to the 5-digit form when possible."""
    match = re.search(r"(\d{5})(?:-\d{4})?", zip_code)
    if match:
        return match.group(1)
    return ""


def normalize_city(city: str) -> str:
    """Normalize a city name by trimming whitespace and preserving title case."""
    return collapse_whitespace(city).title()


def parse_address(address: str) -> dict[str, str]:
    """Parse a single address string into street, city, state, and ZIP pieces."""
    if not address or not collapse_whitespace(address):
        return {"street": "", "city": "", "state": "", "zip": ""}

    raw = collapse_whitespace(address)
    if "," in raw:
        parts = [part.strip() for part in raw.split(",") if part.strip()]
        if len(parts) >= 3:
            street = parts[0]
            city = parts[1]
            state_zip = parts[2]
        elif len(parts) == 2:
            street = parts[0]
            city = ""
            state_zip = parts[1]
        else:
            street = parts[0]
            city = ""
            state_zip = ""
    else:
        parts = raw.split()
        if not parts:
            return {"street": "", "city": "", "state": "", "zip": ""}
        zip_match = re.search(r"(\d{5})(?:-\d{4})?", raw)
        if zip_match:
            zip_value = zip_match.group(1)
            pre_zip = raw[: zip_match.start(1)].strip()
            state_match = re.search(r"\b([A-Za-z]{2})\b", pre_zip)
            if state_match:
                state = state_match.group(1)
                street_city = pre_zip[: state_match.start(1)].strip()
                city_tokens = street_city.split()
                city = city_tokens[-1] if city_tokens else ""
                street = " ".join(city_tokens[:-1]) if len(city_tokens) > 1 else ""
            else:
                street = pre_zip
                city = ""
                state = ""
            return {
                "street": normalize_street(street),
                "city": normalize_city(city),
                "state": normalize_state(state),
                "zip": normalize_zip(zip_value),
            }

        street = raw
        city = ""
        state_zip = ""
        parts = [part for part in raw.split() if part]
        if len(parts) >= 2:
            street = " ".join(parts[:-1])
            city = parts[-1]
        else:
            street = raw
            city = ""

    state = ""
    zip_value = ""
    state_zip_match = re.search(r"\b([A-Za-z]{2})\b", state_zip)
    zip_match = re.search(r"(\d{5})(?:-\d{4})?", state_zip)

    if zip_match:
        zip_value = zip_match.group(1)
        state_zip = state_zip[: zip_match.start(1)].strip()
    if state_zip_match:
        state = state_zip_match.group(1)
        state_zip = state_zip[: state_zip_match.start(1)].strip()

    if not city and state_zip:
        city = state_zip

    street_number, street_name = split_street_parts(street)
    return {
        "street": normalize_street(street),
        "street_number": street_number,
        "street_name": normalize_street_name(street_name),
        "city": normalize_city(city),
        "state": normalize_state(state),
        "zip": normalize_zip(zip_value),
    }


def build_normalized_address(original_address: str) -> dict[str, Any]:
    """Create a canonical address object for the given input string."""
    parsed = parse_address(original_address)
    normalized_address = ", ".join(
        part
        for part in [
            parsed["street"],
            f"{parsed['city']}, {parsed['state']} {parsed['zip']}".strip(),
        ]
        if part
    )

    address = {
        "original_address": original_address.strip(),
        "normalized_address": normalized_address,
        "street": parsed["street"],
        "street_number": parsed.get("street_number", ""),
        "street_name": parsed.get("street_name", ""),
        "city": parsed["city"],
        "state": parsed["state"],
        "zip": parsed["zip"],
        "county": "",
        "county_fips": "",
        "latitude": 0.0,
        "longitude": 0.0,
    }
    return address


def _request_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Perform a GET request and return JSON when available."""
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def extract_county_from_census_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract county data from a Census geocoder payload."""
    matches = payload.get("result", {}).get("addressMatches", [])
    if not matches:
        return {}

    match = matches[0]
    coordinates = match.get("coordinates", {})
    geographies = match.get("geographies", {})

    county = ""
    county_fips = ""
    for geography_values in geographies.values():
        if not isinstance(geography_values, list):
            continue
        for geography in geography_values:
            if geography.get("NAME", "").lower().endswith(" county") or geography.get("COUNTY"):
                county = geography.get("NAME", "")
                county_fips = geography.get("GEOID", "")
                break
        if county:
            break

    return {
        "county": county,
        "county_fips": county_fips,
        "latitude": float(coordinates.get("y", 0.0)),
        "longitude": float(coordinates.get("x", 0.0)),
    }


def geocode_with_census(address: dict[str, str]) -> dict[str, Any]:
    """Use the U.S. Census geocoder for address geocoding."""
    if not address.get("street") or not address.get("city") or not address.get("state"):
        return {}

    params = {
        "street": address["street"],
        "city": address["city"],
        "state": address["state"],
        "benchmark": "Public_AR_Current",
        "vintage": "Current_Current",
        "format": "json",
    }
    if address.get("zip"):
        params["zip"] = address["zip"]

    url = "https://geocoding.geo.census.gov/geocoder/geographies/address"
    data = _request_json(url, params=params)
    result = extract_county_from_census_payload(data)
    if not result.get("county"):
        return {}
    return result


def reverse_geocode_with_census(lat: float, lon: float) -> dict[str, Any]:
    """Use the U.S. Census geocoder for reverse geocoding."""
    url = "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
    params = {
        "x": lon,
        "y": lat,
        "benchmark": "Public_AR_Current",
        "vintage": "Current_Current",
        "format": "json",
        "layers": "county",
    }
    try:
        data = _request_json(url, params=params)
    except (requests.RequestException, ValueError):
        return {}
    result = data.get("result", {})
    if not result:
        return {}
    geographies = result.get("geographies", [])
    if not geographies:
        return {}
    geography = geographies[0]
    return {
        "county": geography.get("NAME", ""),
        "county_fips": geography.get("GEOID", ""),
        "latitude": lat,
        "longitude": lon,
    }


def zip_lookup(zip_code: str) -> dict[str, Any]:
    """Use the ZIP API to retrieve city/state information for a ZIP code."""
    if not zip_code:
        return {}
    url = f"https://api.zippopotam.us/us/{zip_code}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return {}

    places = data.get("places", [])
    if not places:
        return {}
    place = places[0]
    return {
        "city": place.get("place name", ""),
        "state": place.get("state abbreviation", ""),
    }


def zip_to_county(zip_code: str) -> dict[str, Any]:
    """Use the U.S. Census geocoder to resolve county information from ZIP code alone."""
    if not zip_code:
        return {}
    url = "https://geocoding.geo.census.gov/geocoder/geographies/zip"
    params = {
        "zip": zip_code,
        "benchmark": "Public_AR_Current",
        "vintage": "Current_Current",
        "format": "json",
    }
    try:
        data = _request_json(url, params=params)
    except (requests.RequestException, ValueError):
        return {}

    matches = data.get("result", {}).get("addressMatches", [])
    if not matches:
        return {}

    geographies = matches[0].get("geographies", {})
    for geography_values in geographies.values():
        if not isinstance(geography_values, list):
            continue
        for geography in geography_values:
            if geography.get("NAME", "").lower().endswith(" county") or geography.get("COUNTY"):
                return {
                    "county": geography.get("NAME", ""),
                    "county_fips": geography.get("GEOID", ""),
                }
    return {}


def enrich_address(address: dict[str, Any]) -> dict[str, Any]:
    """Enrich the normalized address with county and coordinates using a fallback chain."""
    parsed = {
        "street": address["street"],
        "city": address["city"],
        "state": address["state"],
        "zip": address["zip"],
    }

    geocode_result: dict[str, Any] = {}
    try:
        geocode_result = geocode_with_census(parsed)
    except (requests.RequestException, ValueError):
        geocode_result = {}

    if geocode_result and (geocode_result.get("county") or geocode_result.get("county_fips")):
        address["county"] = geocode_result.get("county", "")
        address["county_fips"] = geocode_result.get("county_fips", "")
        address["latitude"] = geocode_result.get("latitude", 0.0)
        address["longitude"] = geocode_result.get("longitude", 0.0)
        return address

    if geocode_result.get("latitude") and geocode_result.get("longitude"):
        reverse_result = reverse_geocode_with_census(float(geocode_result["latitude"]), float(geocode_result["longitude"]))
        if reverse_result:
            address["county"] = reverse_result.get("county", "")
            address["county_fips"] = reverse_result.get("county_fips", "")
            address["latitude"] = geocode_result.get("latitude", 0.0)
            address["longitude"] = geocode_result.get("longitude", 0.0)
            return address

    if address.get("zip"):
        zip_result = zip_lookup(address["zip"])
        county_result = zip_to_county(address["zip"])
        if zip_result:
            if not address.get("city") and zip_result.get("city"):
                address["city"] = zip_result["city"]
            if not address.get("state") and zip_result.get("state"):
                address["state"] = zip_result["state"]
            if county_result:
                address["county"] = county_result.get("county", "")
                address["county_fips"] = county_result.get("county_fips", "")
            address["normalized_address"] = ", ".join(
                part for part in [address["street"], f"{address['city']}, {address['state']} {address['zip']}".strip()] if part
            )
            return address

    return address


def read_address_rows(path: str) -> list[dict[str, Any]]:
    """Read address rows from CSV, Excel, or ZIP files."""
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    if resolved.is_dir():
        rows: list[dict[str, Any]] = []
        for child in sorted(resolved.iterdir()):
            if child.is_file():
                rows.extend(read_address_rows(str(child)))
        return rows

    suffix = resolved.suffix.lower()
    if suffix == ".csv":
        with resolved.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            return [{"original_address": row.get(address_col(reader.fieldnames), "")} for row in reader]

    if suffix in {".xlsx", ".xls"}:
        if pd is None:
            raise RuntimeError("pandas is required to read Excel files. Install requirements first.")
        frame = pd.read_excel(resolved)
        rows: list[dict[str, Any]] = []
        for _, row in frame.iterrows():
            address_value = None
            for column in frame.columns:
                if "address" in str(column).lower() or "street" in str(column).lower() or "property" in str(column).lower():
                    address_value = row[column]
                    if isinstance(address_value, str) and address_value.strip():
                        break
            if address_value is None:
                address_value = frame.iloc[0, 0]
            rows.append({"original_address": str(address_value or "")})
        return rows

    if suffix == ".zip":
        with zipfile.ZipFile(resolved) as archive:
            inner_files = [name for name in archive.namelist() if not name.endswith("/")]
            if not inner_files:
                return []
            rows: list[dict[str, Any]] = []
            for inner_name in inner_files:
                with archive.open(inner_name) as handle:
                    if inner_name.lower().endswith(".csv"):
                        data = handle.read().decode("utf-8-sig")
                        reader = csv.DictReader(data.splitlines())
                        for row in reader:
                            rows.append({"original_address": row.get(address_col(reader.fieldnames), "")})
                    elif inner_name.lower().endswith((".xlsx", ".xls")):
                        if pd is None:
                            raise RuntimeError("pandas is required to read Excel files inside ZIP archives.")
                        frame = pd.read_excel(handle)
                        for _, row in frame.iterrows():
                            address_value = None
                            for column in frame.columns:
                                if "address" in str(column).lower() or "street" in str(column).lower() or "property" in str(column).lower():
                                    address_value = row[column]
                                    if isinstance(address_value, str) and address_value.strip():
                                        break
                            if address_value is None:
                                address_value = frame.iloc[0, 0]
                            rows.append({"original_address": str(address_value or "")})
            return rows

    raise ValueError(f"Unsupported input file type: {resolved}")


def address_col(fieldnames: Iterable[str] | None) -> str:
    """Infer the most likely address column from CSV headers."""
    if not fieldnames:
        return ""
    normalized_names = [str(name).lower() for name in fieldnames]
    for index, name in enumerate(normalized_names):
        if "address" in name or "street" in name or "property" in name or "location" in name:
            return fieldnames[index]
    return next(iter(fieldnames))


def normalize_input(source: str) -> list[dict[str, Any]]:
    """Normalize a single input address string or a file-based batch input."""
    if source and os.path.exists(source):
        rows = read_address_rows(source)
        results: list[dict[str, Any]] = []
        for row in rows:
            original_address = str(row.get("original_address", "") or "")
            if original_address:
                address = build_normalized_address(original_address)
                results.append(enrich_address(address))
        return results

    single_address = build_normalized_address(source)
    return [enrich_address(single_address)]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Normalize U.S. addresses and enrich them with county and coordinates.")
    parser.add_argument("input", nargs="?", help="An address string or a path to a .csv, .xlsx, .xls, or .zip file")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    parser.add_argument("--output", help="Optional path to save the JSON output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    args = parse_args(argv)

    if args.input:
        source = args.input
    else:
        print("Enter an address or a file path (CSV, Excel, ZIP): ", end="", flush=True)
        source = sys.stdin.readline().strip()

    if not source:
        print(json.dumps({"error": "No input supplied"}, indent=2))
        return 1

    try:
        results = normalize_input(source)
    except Exception as exc:  # pragma: no cover - defensive top-level handler
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1

    output = results if len(results) > 1 else results[0]
    serialized = json.dumps(output, indent=2 if args.pretty else None)

    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(serialized + "\n", encoding="utf-8")
        print(f"Saved output to {output_path}")
    else:
        print(serialized)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
