"""Cumulative Scenario A H&S write-off totals for dashboard KPIs."""

from __future__ import annotations

import os
import sqlite3

from services.bouncer_buffer import BOUNCER_DB_PATH, ensure_bouncer_buffer


def _waste_db_path() -> str:
    return os.getenv("BOUNCER_BUFFER_PATH", BOUNCER_DB_PATH)


def _ensure_waste_tracker(db_path: str = _waste_db_path()) -> None:
    conn = ensure_bouncer_buffer(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_waste_tracker (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            waste_qty INTEGER NOT NULL DEFAULT 0,
            waste_cost REAL NOT NULL DEFAULT 0
        );
        """
    )
    conn.execute(
        "INSERT OR IGNORE INTO daily_waste_tracker (id, waste_qty, waste_cost) VALUES (1, 0, 0);"
    )
    conn.close()


def record_scenario_a_waste(damaged_qty: int, waste_value: float) -> None:
    """Increment daily waste qty/cost after a Health & Safety write-off."""
    db_path = _waste_db_path()
    _ensure_waste_tracker(db_path)
    conn = ensure_bouncer_buffer(db_path)
    try:
        conn.execute(
            """
            UPDATE daily_waste_tracker
            SET waste_qty = waste_qty + ?,
                waste_cost = waste_cost + ?
            WHERE id = 1;
            """,
            (int(damaged_qty), float(waste_value)),
        )
        conn.commit()
    finally:
        conn.close()


def reset_daily_waste_totals() -> None:
    """Zero H&S waste KPI accumulators (e.g. when reconciliation log is purged)."""
    db_path = _waste_db_path()
    _ensure_waste_tracker(db_path)
    conn = ensure_bouncer_buffer(db_path)
    try:
        conn.execute(
            """
            UPDATE daily_waste_tracker
            SET waste_qty = 0, waste_cost = 0
            WHERE id = 1;
            """
        )
        conn.commit()
    finally:
        conn.close()


def get_daily_waste_totals() -> dict[str, float | int]:
    db_path = _waste_db_path()
    _ensure_waste_tracker(db_path)
    conn = ensure_bouncer_buffer(db_path)
    try:
        row = conn.execute(
            "SELECT waste_qty, waste_cost FROM daily_waste_tracker WHERE id = 1;"
        ).fetchone()
        if not row:
            return {"daily_waste_qty": 0, "daily_waste_cost": 0.0}
        return {
            "daily_waste_qty": int(row["waste_qty"]),
            "daily_waste_cost": round(float(row["waste_cost"]), 2),
        }
    finally:
        conn.close()
