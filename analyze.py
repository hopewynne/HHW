"""
analyze.py

Run this any time you want to see whether an upload moved the needle.
Usage:
    python analyze.py B0EXAMPLE123
"""

import sqlite3
import sys
import statistics
from datetime import date, timedelta

DB_PATH = "conversion.db"
WINDOW_DAYS = 14  # how many days before/after to compare


def analyze(asin: str):
    conn = sqlite3.connect(DB_PATH)

    upload = conn.execute(
        "SELECT asset_type, submitted_at, live_at FROM uploads "
        "WHERE asin = ? AND live_at IS NOT NULL "
        "ORDER BY live_at DESC LIMIT 1",
        (asin,),
    ).fetchone()

    if not upload:
        print(f"No confirmed-live upload found for {asin}. "
              f"(Either nothing logged yet, or it hasn't gone live.)")
        return

    asset_type, submitted_at, live_at = upload
    live_date = date.fromisoformat(live_at)

    before_start = (live_date - timedelta(days=WINDOW_DAYS)).isoformat()
    before_end = (live_date - timedelta(days=1)).isoformat()
    after_start = live_date.isoformat()
    after_end = (live_date + timedelta(days=WINDOW_DAYS)).isoformat()

    def rates_between(start, end):
        rows = conn.execute(
            "SELECT conversion_rate FROM daily_metrics "
            "WHERE asin = ? AND date BETWEEN ? AND ? AND conversion_rate IS NOT NULL",
            (asin, start, end),
        ).fetchall()
        return [r[0] for r in rows]

    before = rates_between(before_start, before_end)
    after = rates_between(after_start, after_end)

    print(f"\nASIN: {asin}")
    print(f"Upload type: {asset_type}  |  went live: {live_date}")
    print(f"Before window: {before_start} to {before_end}  ({len(before)} days of data)")
    print(f"After window:  {after_start} to {after_end}  ({len(after)} days of data)")

    if len(before) < 3 or len(after) < 3:
        print("\nNot enough data yet on one or both sides — check back once more days accumulate.")
        conn.close()
        return

    before_avg = statistics.mean(before)
    after_avg = statistics.mean(after)
    change = after_avg - before_avg
    pct_change = (change / before_avg * 100) if before_avg else float("nan")

    print(f"\nAvg conversion rate before: {before_avg:.2%}")
    print(f"Avg conversion rate after:  {after_avg:.2%}")
    print(f"Change: {change:+.2%}  ({pct_change:+.1f}% relative)")

    print("\nNote: this is a simple average comparison. Check for confounders")
    print("(price changes, stockouts, ad spend changes) before attributing the")
    print("full change to the content update.")

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python analyze.py <ASIN>")
        sys.exit(1)
    analyze(sys.argv[1])
