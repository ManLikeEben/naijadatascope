from pathlib import Path
from datetime import datetime, timezone
import json
import logging
import time
import uuid

import duckdb
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]

RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
WAREHOUSE_DIR = ROOT / "data" / "warehouse"

for directory in (RAW_DIR, PROCESSED_DIR, WAREHOUSE_DIR):
    directory.mkdir(parents=True, exist_ok=True)

DB_PATH = WAREHOUSE_DIR / "naijadatascope.duckdb"
BASE_URL = "https://api.worldbank.org/v2"

COUNTRIES = {
    "NGA": "Nigeria",
    "GHA": "Ghana",
    "ZAF": "South Africa",
}

INDICATORS = {
    "NY.GDP.MKTP.CD": "GDP (current US$)",
    "NY.GDP.MKTP.KD.ZG": "GDP growth (annual %)",
    "FP.CPI.TOTL.ZG": "Inflation, consumer prices (annual %)",
    "SP.POP.TOTL": "Population, total",
    "SL.UEM.TOTL.ZS": "Unemployment (% of labour force, ILO modelled estimate)",
}

START_YEAR = 2000
END_YEAR = 2025

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)




def get_indicator_unit(indicator_code):
    """Return a consistent display unit for each supported indicator."""
    units = {
        "NY.GDP.MKTP.CD": "Current US dollars",
        "NY.GDP.MKTP.KD.ZG": "Percent per year",
        "FP.CPI.TOTL.ZG": "Percent per year",
        "SP.POP.TOTL": "People",
        "SL.UEM.TOTL.ZS": "Percent of labour force",
    }
    return units.get(indicator_code, "Not specified")

def request_with_retry(url, **kwargs):
    """Retry temporary network and server failures with backoff."""
    kwargs["timeout"] = (15, 90)
    retryable_statuses = {429, 500, 502, 503, 504}

    for attempt in range(4):
        try:
            response = requests.get(url, **kwargs)

            if response.status_code not in retryable_statuses:
                response.raise_for_status()
                return response

            if attempt == 3:
                response.raise_for_status()

            logging.warning(
                "HTTP %s; retry %s/3 in progress",
                response.status_code,
                attempt + 1,
            )

        except requests.exceptions.RequestException as exc:
            if attempt == 3:
                raise

            logging.warning(
                "Request failed (%s); retry %s/3: %s",
                type(exc).__name__,
                attempt + 1,
                exc,
            )

        time.sleep(2 ** attempt)

    raise RuntimeError(f"Request failed after retries: {url}")


def fetch_indicator(indicator_code, indicator_name):
    """Fetch all available observations for one indicator."""

    url = (
        f"{BASE_URL}/country/"
        f"{';'.join(COUNTRIES.keys())}/indicator/{indicator_code}"
    )

    params = {
        "format": "json",
        "date": f"{START_YEAR}:{END_YEAR}",
        "per_page": 20000,
        "page": 1,
    }

    response = request_with_retry(
        url,
        params=params,
        timeout=45,
        headers={"User-Agent": "NaijaDataScope/1.0"},
    )
    response.raise_for_status()

    payload = response.json()

    if not isinstance(payload, list) or len(payload) < 2:
        raise ValueError(
            f"Unexpected API response for {indicator_code}: {payload}"
        )

    if isinstance(payload[0], dict) and payload[0].get("message"):
        raise ValueError(
            f"World Bank API error for {indicator_code}: {payload[0]['message']}"
        )

    metadata = payload[0]
    all_records = list(payload[1] or [])

    # Follow pagination if the API returns multiple pages.
    total_pages = int(metadata.get("pages", 1))

    for page in range(2, total_pages + 1):
        params["page"] = page

        page_response = request_with_retry(
            url,
            params=params,
            timeout=45,
            headers={"User-Agent": "NaijaDataScope/1.0"},
        )
        page_response.raise_for_status()

        page_payload = page_response.json()

        if (
            not isinstance(page_payload, list)
            or len(page_payload) < 2
            or (
                isinstance(page_payload[0], dict)
                and page_payload[0].get("message")
            )
        ):
            raise ValueError(
                f"Invalid API response on page {page} for {indicator_code}"
            )

        all_records.extend(page_payload[1] or [])

    # Preserve the source responses for traceability.
    raw_path = RAW_DIR / f"world_bank_{indicator_code.replace('.', '_')}.json"

    with raw_path.open("w", encoding="utf-8") as file:
        json.dump(
            {
                "indicator_code": indicator_code,
                "indicator_name": indicator_name,
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "response_metadata": metadata,
                "records": all_records,
            },
            file,
            ensure_ascii=False,
            indent=2,
        )

    rows = []
    fetched_at = datetime.now(timezone.utc).isoformat()

    for record in all_records:
        value = record.get("value")

        # Missing observations remain missing, not fabricated.
        if value is None:
            continue

        rows.append({
            "country_code": record.get("countryiso3code"),
            "country_name": record.get("country", {}).get("value"),
            "indicator_code": indicator_code,
            "indicator_name": indicator_name,
            "year": int(record["date"]),
            "value": float(value),
            "unit": get_indicator_unit(indicator_code),
            "source": "World Bank",
            "source_url": url,
            "fetched_at_utc": fetched_at,
        })

    logging.info(
        "%s: retrieved %s usable observations",
        indicator_code,
        len(rows),
    )

    return rows


def run_pipeline():
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()

    logging.info("Starting NaijaDataScope ingestion: %s", run_id)

    all_rows = []

    # Fetch everything before replacing the warehouse table.
    for code, name in INDICATORS.items():
        all_rows.extend(fetch_indicator(code, name))

    if not all_rows:
        raise RuntimeError("No usable observations were returned.")

    df = pd.DataFrame(all_rows)

    df = df.drop_duplicates(
        subset=["country_code", "indicator_code", "year"],
        keep="last",
    )

    df = df.sort_values(
        ["country_code", "indicator_code", "year"]
    ).reset_index(drop=True)

    # Basic data-quality checks.
    required_columns = [
        "country_code",
        "country_name",
        "indicator_code",
        "indicator_name",
        "year",
        "value",
        "source",
        "fetched_at_utc",
    ]

    if df[required_columns].isnull().any().any():
        raise ValueError("Required columns contain missing values.")

    if not df["year"].between(START_YEAR, END_YEAR).all():
        raise ValueError("Unexpected year outside the requested range.")

    if not df["value"].map(lambda x: pd.notna(x) and abs(x) != float("inf")).all():
        raise ValueError("Invalid numeric observation detected.")

    processed_path = PROCESSED_DIR / "economic_indicators.csv"
    df.to_csv(processed_path, index=False)

    # Load the validated dataset into DuckDB.
    with duckdb.connect(str(DB_PATH)) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS ingestion_log (
                run_id VARCHAR,
                source VARCHAR,
                status VARCHAR,
                rows_loaded BIGINT,
                started_at_utc VARCHAR,
                finished_at_utc VARCHAR,
                message VARCHAR
            )
        """)

        con.register("incoming_data", df)

        # Full refresh for this initial version.
        # The raw files remain available for historical traceability.
        con.execute("""
            CREATE OR REPLACE TABLE economic_indicators AS
            SELECT * FROM incoming_data
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS indicator_catalog (
                indicator_code VARCHAR,
                indicator_name VARCHAR,
                description VARCHAR
            )
        """)

        catalog = pd.DataFrame([
            {
                "indicator_code": code,
                "indicator_name": name,
                "description": name,
            }
            for code, name in INDICATORS.items()
        ])

        con.register("incoming_catalog", catalog)

        con.execute("""
            CREATE OR REPLACE TABLE indicator_catalog AS
            SELECT * FROM incoming_catalog
        """)

        finished_at = datetime.now(timezone.utc).isoformat()

        con.execute("""
            INSERT INTO ingestion_log VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            run_id,
            "World Bank Indicators API",
            "SUCCESS",
            len(df),
            started_at,
            finished_at,
            f"Loaded {len(df)} observations for {df['country_code'].nunique()} countries",
        ])

        summary = con.execute("""
            SELECT
                country_name,
                COUNT(*) AS observations,
                COUNT(DISTINCT indicator_code) AS indicators,
                MIN(year) AS first_year,
                MAX(year) AS last_year
            FROM economic_indicators
            GROUP BY country_name
            ORDER BY country_name
        """).df()

    logging.info("Pipeline completed successfully.")
    print("\nDATA INGESTION SUMMARY")
    print(summary.to_string(index=False))
    print(f"\nTotal observations: {len(df):,}")
    print(f"DuckDB warehouse: {DB_PATH}")
    print(f"Processed CSV: {processed_path}")
    print(f"Raw API responses: {RAW_DIR}")


if __name__ == "__main__":
    try:
        run_pipeline()
    except Exception:
        logging.exception("Data ingestion failed.")
        raise

