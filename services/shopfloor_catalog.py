"""Master shopfloor SKU catalog (SQLite seed + ledger entries for API Bouncer)."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any

from models.bouncer_schemas import ExpectedLedger

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CATALOG_JSON = _REPO_ROOT / "data" / "shopfloor_master_catalog.json"
_DEFAULT_DB = _REPO_ROOT / "data" / "shopfloor_catalog.db"

_REQUIRED_ROW_KEYS = ("ean", "product_name", "fixture_type", "bom_units", "unit_price_pence")

# Baked-in master SKUs — used when JSON is missing (e.g. /app/data masked by Docker volume).
MASTER_CATALOG_ROWS: list[dict[str, Any]] = [
    {
        "ean": "5010000000012",
        "product_name": "Multipack Crisps 6pk",
        "fixture_type": "SHELF",
        "bom_units": 12,
        "unit_price_pence": 250,
        "inner_pack_units": 6,
    },
    {
        "ean": "5020000000067",
        "product_name": "Chocolate Cookies",
        "fixture_type": "SHELF",
        "bom_units": 6,
        "unit_price_pence": 150,
        "inner_pack_units": 6,
    },
    {
        "ean": "5030000000098",
        "product_name": "Lemonade 2L",
        "fixture_type": "SHELF",
        "bom_units": 6,
        "unit_price_pence": 300,
    },
    {
        "ean": "5040000000105",
        "product_name": "Flour 1.5kg",
        "fixture_type": "SHELF",
        "bom_units": 12,
        "unit_price_pence": 250,
        "inner_pack_units": 12,
    },
]


def catalog_db_path() -> Path:
    return Path(os.getenv("SHOPFLOOR_CATALOG_PATH", str(_DEFAULT_DB)))


def _catalog_json_path() -> Path:
    override = os.getenv("SHOPFLOOR_CATALOG_JSON", "").strip()
    if override:
        return Path(override)
    return _CATALOG_JSON


def _normalize_catalog_row(raw: dict[str, Any]) -> dict[str, Any]:
    bom = int(raw["bom_units"])
    inner_raw = raw.get("inner_pack_units")
    inner_pack = int(inner_raw) if inner_raw is not None else bom
    return {
        "ean": str(raw["ean"]).strip(),
        "product_name": str(raw["product_name"]).strip(),
        "fixture_type": str(raw["fixture_type"]).strip().upper(),
        "bom_units": bom,
        "unit_price_pence": int(raw["unit_price_pence"]),
        "inner_pack_units": inner_pack,
    }


def _valid_catalog_row(raw: object) -> bool:
    if not isinstance(raw, dict):
        return False
    return all(key in raw for key in _REQUIRED_ROW_KEYS)


def load_master_catalog() -> list[dict[str, Any]]:
    """
    Load master SKU rows from JSON when present; otherwise use embedded catalog.
    Never raises — returns a list of normalized row dicts.
    """
    path = _catalog_json_path()
    if path.is_file():
        try:
            with path.open(encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, list):
                rows: list[dict[str, Any]] = []
                for item in payload:
                    if not _valid_catalog_row(item):
                        logger.warning("Skipping invalid shopfloor catalog row: %r", item)
                        continue
                    rows.append(_normalize_catalog_row(item))
                if rows:
                    return rows
            logger.warning(
                "Shopfloor catalog at %s is empty or malformed; using embedded master SKUs.",
                path,
            )
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning(
                "Failed to read shopfloor catalog from %s (%s); using embedded master SKUs.",
                path,
                exc,
            )
    else:
        logger.info(
            "Shopfloor catalog JSON not found at %s; using embedded master SKUs.",
            path,
        )

    return deepcopy(MASTER_CATALOG_ROWS)


def catalog_by_product_name() -> dict[str, dict[str, Any]]:
    return {row["product_name"]: row for row in load_master_catalog()}


def catalog_by_ean() -> dict[str, dict[str, Any]]:
    return {row["ean"]: row for row in load_master_catalog()}


def parent_sku_for_ean(ean: str) -> str:
    return f"EAN-{ean}"


def build_master_ledger_db() -> dict[str, ExpectedLedger]:
    """
    Map parent SKU (EAN-{ean}) -> ExpectedLedger for API Bouncer CENTRAL_LEDGER_DB merge.
    """
    ledger: dict[str, ExpectedLedger] = {}
    for row in load_master_catalog():
        try:
            normalized = _normalize_catalog_row(row)
            ean = normalized["ean"]
            bom = normalized["bom_units"]
            inner_pack = normalized["inner_pack_units"]
            multipack_retail = round(normalized["unit_price_pence"] / 100.0, 2)
            parent = parent_sku_for_ean(ean)
            ledger[parent] = ExpectedLedger(
                parent_sku=parent,
                ean=ean,
                expected_quantity=bom,
                planogram_location="CAM-AISLE-04",
                expected_format="SHRINK_WRAPPED_MULTIPACK",
                linked_child_sku=f"{parent}-SINGLE",
                retail_price=multipack_retail,
                pack_quantity=inner_pack,
                is_alcohol=False,
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Skipping shopfloor ledger row %r: %s", row, exc)
    return ledger


def init_shopfloor_catalog_db() -> None:
    path = catalog_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = load_master_catalog()
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shopfloor_master_catalog (
                ean TEXT PRIMARY KEY,
                product_name TEXT NOT NULL,
                fixture_type TEXT NOT NULL,
                bom_units INTEGER NOT NULL,
                unit_price_pence INTEGER NOT NULL,
                inner_pack_units INTEGER
            )
            """
        )
        try:
            conn.execute(
                "ALTER TABLE shopfloor_master_catalog ADD COLUMN inner_pack_units INTEGER"
            )
        except sqlite3.OperationalError:
            pass
        conn.executemany(
            """
            INSERT OR REPLACE INTO shopfloor_master_catalog
                (ean, product_name, fixture_type, bom_units, unit_price_pence, inner_pack_units)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["ean"],
                    row["product_name"],
                    row["fixture_type"],
                    int(row["bom_units"]),
                    int(row["unit_price_pence"]),
                    int(row.get("inner_pack_units", row["bom_units"])),
                )
                for row in rows
            ],
        )
        conn.commit()
