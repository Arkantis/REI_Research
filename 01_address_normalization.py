# plugins/address_normalizer.py

import re
import requests

STATE_ABBREVIATIONS = {...}  # same dict
STREET_SUFFIXES = {...}      # same dict

def collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()

def split_street_parts(street: str) -> tuple[str, str]:
    cleaned = collapse_whitespace(street)
    tokens = cleaned.split()
    if not tokens:
        return "", ""
    first = tokens[0].upper()
    if re.fullmatch(r"\d{1,6}[A-Z]?", first):
        return tokens[0], " ".join(tokens[1:])
    return "", cleaned

def normalize_street_name(name: str) -> str:
    name = collapse_whitespace(name).upper()
    tokens = name.split()
    normalized = []
    for token in tokens:
        clean = re.sub(r"[^A-Z0-9]", "", token)
        normalized.append(STREET_SUFFIXES.get(clean, clean))
    return " ".join(t.title() if not t.isdigit() else t for t in normalized)

def normalize_street(street: str) -> str:
    num, name = split_street_parts(street)
    if num and name:
        return f"{num} {normalize_street_name(name)}"
    if num:
        return num
    return normalize_street_name(name)

def normalize_state(state: str) -> str:
    s = collapse_whitespace(state).upper()
    return STATE_ABBREVIATIONS.get(s, s[:2])

def normalize_zip(zip_code: str) -> str:
    m = re.search(r"(\d{5})(?:-\d{4})?", zip_code)
    return m.group(1) if m else ""

def normalize_city(city: str) -> str:
    return collapse_whitespace(city).title()

def parse_address(address: str) -> dict:
    # condensed version of your parsing logic
    if not address or not collapse_whitespace(address):
        return {"street": "", "city": "", "state": "", "zip": ""}

    raw = collapse_whitespace(address)
    street, city, state, zip_code = "", "", "", ""

    if "," in raw:
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        street = parts[0]
        if len(parts) >= 2:
            city = parts[1]
        if len(parts) >= 3:
            state_zip = parts[2]
            m_state = re.search(r"\b([A-Za-z]{2})\b", state_zip)
            m_zip = re.search(r"(\d{5})(?:-\d{4})?", state_zip)
            if m_state:
                state = m_state.group(1)
            if m_zip:
                zip_code = m_zip.group(1)
    else:
        # fallback parsing
        m_zip = re.search(r"(\d{5})(?:-\d{4})?", raw)
        if m_zip:
            zip_code = m_zip.group(1)
            pre = raw[:m_zip.start()].strip()
            m_state = re.search(r"\b([A-Za-z]{2})\b", pre)
            if m_state:
                state = m_state.group(1)
                city = pre[m_state.start():].strip()
                street = pre[:m_state.start()].strip()
            else:
                street = pre

    num, name = split_street_parts(street)
    return {
        "street": normalize_street(street),
        "street_number": num,
        "street_name": normalize_street_name(name),
        "city": normalize_city(city),
        "state": normalize_state(state),
        "zip": normalize_zip(zip_code),
    }

def build_normalized_address(original: str) -> dict:
    parsed = parse_address(original)
    normalized = f"{parsed['street']}, {parsed['city']}, {parsed['state']} {parsed['zip']}".strip()
    return {
        "original_address": original.strip(),
        "normalized_address": normalized,
        **parsed,
        "county": "",
        "county_fips": "",
        "latitude": 0.0,
        "longitude": 0.0,
    }

def _request_json(url: str, params=None) -> dict:
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def extract_county(payload: dict) -> dict:
    matches = payload.get("result", {}).get("addressMatches", [])
    if not matches:
        return {}
    m = matches[0]
    coords = m.get("coordinates", {})
    geos = m.get("geographies", {})
    county, fips = "", ""
    for values in geos.values():
        for g in values:
            if g.get("NAME", "").lower().endswith(" county"):
                county = g.get("NAME", "")
                fips = g.get("GEOID", "")
                break
    return {
        "county": county,
        "county_fips": fips,
        "latitude": float(coords.get("y", 0.0)),
        "longitude": float(coords.get("x", 0.0)),
    }

def geocode(address: dict) -> dict:
    if not address["street"] or not address["city"] or not address["state"]:
        return {}
    params = {
        "street": address["street"],
        "city": address["city"],
        "state": address["state"],
        "benchmark": "Public_AR_Current",
        "vintage": "Current_Current",
        "format": "json",
    }
    if address["zip"]:
        params["zip"] = address["zip"]
    url = "https://geocoding.geo.census.gov/geocoder/geographies/address"
    return extract_county(_request_json(url, params))

def enrich(address: dict) -> dict:
    geo = geocode(address)
    if geo.get("county"):
        address.update(geo)
        return address
    return address

def get_normalized_address(input_address: str) -> dict:
    """PLUGIN ENTRYPOINT"""
    addr = build_normalized_address(input_address)
    return enrich(addr)
