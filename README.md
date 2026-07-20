# 🏗 Property Intelligence Plugin Pipeline
## 📌 Overview
This project is a modular, plugin‑based pipeline for analyzing any U.S. property address across all 50 states. It normalizes addresses, discovers official public‑record sources, retrieves property and location data, and generates a deterministic screening report.

The system is designed to be:

### ✔ Modular — each plugin can run independently

### ✔ Composable — plugins can be chained together into a full pipeline

### ✔ Extensible — new plugins can be added without changing the pipeline

### ✔ Database‑friendly — outputs can be saved directly into PostgreSQL

### ✔ Beginner‑friendly — simple Python functions, no complex frameworks


# Plugin Architecture
Your pipeline consists of five plugins, each responsible for one stage of the property intelligence workflow:

# Plugin	Purpose	Input	Output
address_normalizer | Clean & standardize addresses, add county + coordinates | Raw address string | Canonical normalized address object
source_registry | Discover & validate official public‑record sources | Normalized address | Verified source list (primary + alternates)
public_records | Retrieve & normalize property records	Normalized address + sources | Standardized property record objects
location_market | Retrieve FEMA flood data + infer location/market context | Normalized address + sources | Location risks + market snapshot
screening_report | Build deterministic recommendation | Public records + location/market | Final screening report


Each plugin exposes one clean entrypoint function, making them easy to test and reuse.

How the Plugins Work Together
The pipeline flows like this:

Code
Raw Address
    ↓
address_normalizer.get_normalized_address()
    ↓
source_registry.get_sources_for_jurisdiction()
    ↓
public_records.get_public_records()
    ↓
location_market.get_location_and_market()
    ↓
screening_report.get_screening_report()
    ↓
Final JSON report (ready for PostgreSQL)
Every plugin receives structured input and returns structured output.
No plugin writes files, touches the CLI, or depends on external modules.

# 🧪 Can Plugins Run Independently?

Yes — **every plugin can run independently**.

### ✔ Address Normalizer  
Use it alone to clean spreadsheet addresses or prepare DB rows.

### ✔ Source Registry  
Use it alone to test jurisdiction source discovery.

### ✔ Public Records  
Use it alone to validate your property‑record schema.

### ✔ Location & Market  
Use it alone for FEMA flood‑zone checks or GIS enrichment.

### ✔ Screening Report  
Use it alone to generate reports from pre‑existing data.

### ✔ Full Pipeline  
Chain them together for complete property intelligence.

---

# 🚀 How to Use Each Plugin

Below are simple examples showing how to call each plugin.

---

## 1. **Address Normalizer**

```python
from plugins.address_normalizer import get_normalized_address

addr = get_normalized_address("4202 Marc Ave, Edinburg TX 78539")
print(addr)
```

Produces:

- street, city, state, ZIP  
- county + county_fips  
- latitude + longitude  
- normalized address string  

---

## 2. **Source Registry**

```python
from plugins.source_registry import get_sources_for_jurisdiction

sources = get_sources_for_jurisdiction(addr, category="assessor")
print(sources)
```

Produces:

- primary official source  
- alternate sources  
- validation status  
- platform + access method  

---

## 3. **Public Records**

```python
from plugins.public_records import get_public_records

records = get_public_records(addr, category="assessor", registry_output=sources)
print(records)
```

Produces:

- standardized property record fields  
- owners, APN, situs address  
- assessed/taxable values  
- encumbrances (mortgages, liens, releases)  
- tax history  
- missing‑field indicators  

---

## 4. **Location & Market**

```python
from plugins.location_market import get_location_and_market

loc = get_location_and_market(addr, category="gis", registry_output=sources)
print(loc)
```

Produces:

- FEMA flood zone, floodway, panel, effective date  
- wetlands / wildfire / zoning / crime indicators  
- market snapshot (placeholder values)  
- nearby sales (inferred from sources)  

---

## 5. **Screening Report**

```python
from plugins.screening_report import get_screening_report

report = get_screening_report(records, loc, asking_price=250000)
print(report)
```

Produces:

- executive summary  
- property summary  
- ownership summary  
- tax summary  
- encumbrance summary  
- location summary  
- market snapshot  
- source summary  
- missing/unavailable data  
- risk flags  
- deterministic recommendation (`proceed`, `manual_review`, `deprioritize`)  

---

# 🏗 Full Pipeline Example

```python
from plugins.address_normalizer import get_normalized_address
from plugins.source_registry import get_sources_for_jurisdiction
from plugins.public_records import get_public_records
from plugins.location_market import get_location_and_market
from plugins.screening_report import get_screening_report

addr = get_normalized_address("4202 Marc Ave, Edinburg TX 78539")
sources = get_sources_for_jurisdiction(addr, category="assessor")
records = get_public_records(addr, category="assessor", registry_output=sources)
loc = get_location_and_market(addr, category="gis", registry_output=sources)
report = get_screening_report(records, loc)

print(report)
```

This produces a complete property intelligence report ready for PostgreSQL.

---

# 🗄 Database Integration (Optional)

All plugin outputs are **pure Python dictionaries**, making them easy to insert into PostgreSQL using:

- psycopg2  
- asyncpg  
- SQLAlchemy  
- pgvector (if you want embeddings later)  

You can store:

- normalized addresses  
- verified sources  
- public‑record payloads  
- location/market data  
- final screening reports  
- source health  
- discovery history  

Your existing `research_sources` schema fits perfectly into this architecture.

---

# 📦 Project Structure

Recommended layout:

```
project/
    plugins/
        address_normalizer.py
        source_registry.py
        public_records.py
        location_market.py
        screening_report.py
    pipeline/
        run_pipeline.py   (optional orchestrator)
    db/
        models.sql        (optional PostgreSQL schema)
    README.md
```

---

# ⚙ Requirements & Dependencies

### **Python Version**
- Python **3.10+** recommended

### **Python Packages**
Minimal dependencies:

```
requests
```

Optional (only needed if you add spreadsheet ingestion):

```
pandas
openpyxl
```

### **External APIs Used**
- U.S. Census Geocoder  
- FEMA NFHL ArcGIS  
- Zippopotam.us ZIP API  

All are free and public.

### **Database (Optional)**
- PostgreSQL 14+ recommended  
- Any Python PostgreSQL client works  

---

# 🧱 Extending the Pipeline

You can add new plugins easily:

- zoning plugin  
- wetlands plugin  
- wildfire plugin  
- market‑valuation plugin  
- MLS listing plugin  
- deed‑scraper plugin  
- lien‑scraper plugin  

Just follow the same pattern:

1. Write a module in `plugins/`  
2. Expose a single entrypoint function  
3. Accept structured input  
4. Return structured output  

The pipeline will automatically integrate it.

---

# 🎯 Final Notes

This plugin architecture is:

- **scalable**  
- **testable**  
- **token‑efficient**  
- **database‑ready**  
- **future‑proof**  

You now have a professional‑grade property intelligence system that can grow with your needs.

If you want, I can help you build:

- a unified `run_pipeline.py` orchestrator  
- a PostgreSQL writer plugin  
- async execution  
- caching layers  
- source‑health monitoring  
- automated source discovery  

Just tell me what you want next.
