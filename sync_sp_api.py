"""
sync_sp_api.py

Run this on a schedule (e.g. 6x/day). Each run:
 1. Checks any pending uploads to see if they've gone live yet.
 2. Pulls the last few days of the Sales & Traffic report and saves it to a
    local SQLite database (conversion.db).

Safe to run repeatedly — all writes are "upsert" (insert or update), so
running this 6 times in one day will not create duplicate rows.
"""

import os
import sqlite3
import time
import json
import gzip
from datetime import date, timedelta

from dotenv import load_dotenv
from sp_api.api import Reports, ListingsItems
from sp_api.base import Marketplaces, ReportType

load_dotenv()  # reads variables from a local .env file

DB_PATH = os.path.join(os.path.dirname(__file__), "conversion.db")

# ── Credentials come from environment variables (see .env.example) ─────────
CREDENTIALS = {
    "refresh_token": os.environ["SP_API_REFRESH_TOKEN"],
    "lwa_app_id": os.environ["SP_API_LWA_APP_ID"],
    "lwa_client_secret": os.environ["SP_API_LWA_CLIENT_SECRET"],
}
MARKETPLACE = getattr(Marketplaces, os.environ.get("SP_API_MARKETPLACE", "US"))
SELLER_ID = os.environ["SP_API_SELLER_ID"]

# How many trailing days of the traffic report to re-pull each run.
# 3 gives a buffer in case Amazon revises a recent day's numbers.
LOOKBACK_DAYS = 3


# ── Database setup ──────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asin TEXT NOT NULL,
            asset_type TEXT NOT NULL,        -- 'image' or 'aplus'
            submitted_at TEXT NOT NULL,
            live_at TEXT,                    -- NULL until confirmed live
            notes TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_metrics (
            asin TEXT NOT NULL,
            date TEXT NOT NULL,
            sessions INTEGER,
            page_views INTEGER,
            units_ordered INTEGER,
            conversion_rate REAL,
            PRIMARY KEY (asin, date)
        )
    """)
    conn.commit()
    return conn


# ── Step 1: check pending uploads ───────────────────────────────────────────
def check_pending_uploads(conn):
    pending = conn.execute(
        "SELECT id, asin, asset_type FROM uploads WHERE live_at IS NULL"
    ).fetchall()

    if not pending:
        print("No pending uploads to check.")
        return

    listings_api = ListingsItems(credentials=CREDENTIALS, marketplace=MARKETPLACE)

    for upload_id, asin, asset_type in pending:
        try:
            item = listings_api.get_listings_item(
                sellerId=SELLER_ID,
                asin=asin,
                marketplaceIds=[MARKETPLACE.marketplace_id],
                includedData=["images"],
            )
            # NOTE: A+ content status requires the separate A+ Content API
            # (aplus-content). This checks basic listing/image status as a
            # starting point — extend this block once you wire up A+ checks.
            if item.payload:
                conn.execute(
                    "UPDATE uploads SET live_at = ? WHERE id = ?",
                    (date.today().isoformat(), upload_id),
                )
                print(f"Marked upload {upload_id} ({asin}) as live.")
        except Exception as e:
            print(f"Could not check ASIN {asin}: {e}")

    conn.commit()


# ── Step 2: pull the Sales & Traffic report ─────────────────────────────────
def pull_sales_and_traffic(conn):
    reports_api = Reports(credentials=CREDENTIALS, marketplace=MARKETPLACE)

    start = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    end = (date.today() - timedelta(days=1)).isoformat()  # yesterday

    print(f"Requesting Sales & Traffic report for {start} to {end}...")
    create_resp = reports_api.create_report(
        reportType=ReportType.GET_SALES_AND_TRAFFIC_REPORT,
        dataStartTime=start,
        dataEndTime=end,
        reportOptions={"asinGranularity": "CHILD"},
    )
    report_id = create_resp.payload["reportId"]

    # Poll until the report is ready
    status = None
    for _ in range(20):  # ~20 x 15s = 5 minutes max wait
        time.sleep(15)
        status_resp = reports_api.get_report(report_id)
        status = status_resp.payload["processingStatus"]
        print(f"Report status: {status}")
        if status in ("DONE", "FATAL", "CANCELLED"):
            break

    if status != "DONE":
        print(f"Report did not finish successfully (status: {status}). Skipping.")
        return

    document_id = status_resp.payload["reportDocumentId"]
    doc = reports_api.get_report_document(document_id, download=True)

    # python-amazon-sp-api decompresses gzip automatically when download=True
    raw = doc.payload.get("document")
    if raw is None:
        print("No document content returned.")
        return

    data = json.loads(raw) if isinstance(raw, str) else raw
    rows = data.get("salesAndTrafficByAsin", [])

    for row in rows:
        asin = row.get("childAsin") or row.get("parentAsin")
        report_date = data.get("reportSpecification", {}).get("dataStartTime", start)[:10]
        traffic = row.get("trafficByAsin", {})
        sales = row.get("salesByAsin", {})

        sessions = traffic.get("sessions")
        page_views = traffic.get("pageViews")
        units_ordered = sales.get("unitsOrdered")
        conversion_rate = traffic.get("unitSessionPercentage")

        conn.execute("""
            INSERT INTO daily_metrics (asin, date, sessions, page_views, units_ordered, conversion_rate)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(asin, date) DO UPDATE SET
                sessions=excluded.sessions,
                page_views=excluded.page_views,
                units_ordered=excluded.units_ordered,
                conversion_rate=excluded.conversion_rate
        """, (asin, report_date, sessions, page_views, units_ordered, conversion_rate))

    conn.commit()
    print(f"Saved {len(rows)} rows of metrics.")


def log_upload(asin: str, asset_type: str, notes: str = ""):
    """Call this manually right after you upload new content, to log it."""
    conn = init_db()
    conn.execute(
        "INSERT INTO uploads (asin, asset_type, submitted_at, notes) VALUES (?, ?, ?, ?)",
        (asin, asset_type, date.today().isoformat(), notes),
    )
    conn.commit()
    conn.close()
    print(f"Logged {asset_type} upload for {asin}.")


if __name__ == "__main__":
    conn = init_db()
    try:
        check_pending_uploads(conn)
        pull_sales_and_traffic(conn)
    finally:
        conn.close()
