"""Dynamic retail SKU catalog loaded from products.json at runtime."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional, TypedDict

logger = logging.getLogger(__name__)


class _SkuCatalogEntryRequired(TypedDict):
    ean: str
    name: str


class SkuCatalogEntry(_SkuCatalogEntryRequired, total=False):
    """Product row from products.json; ``price`` is optional for manifest-only SKUs."""

    price: float


_DEFAULT_PRODUCTS_PATH = Path(__file__).resolve().parent.parent / "data" / "products.json"

_cache: Optional[Dict[str, SkuCatalogEntry]] = None
_cache_mtime: Optional[float] = None


def products_file_path() -> Path:
    configured = os.getenv("WIP_PRODUCTS_PATH", "").strip()
    if configured:
        return Path(configured)
    return _DEFAULT_PRODUCTS_PATH


def reload_products() -> Dict[str, SkuCatalogEntry]:
    """Force reload of the product catalog from disk."""
    global _cache, _cache_mtime
    _cache = None
    _cache_mtime = None
    return get_simulation_sku_pool()


def get_simulation_sku_pool() -> Dict[str, SkuCatalogEntry]:
    """Return the current product catalog, reloading when the JSON file changes."""
    global _cache, _cache_mtime

    path = products_file_path()
    if not path.is_file():
        raise FileNotFoundError(f"Product catalog not found: {path}")

    mtime = path.stat().st_mtime
    if _cache is not None and _cache_mtime == mtime:
        return _cache

    with path.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    if isinstance(raw, dict) and "products" in raw:
        products = raw["products"]
    elif isinstance(raw, dict):
        products = raw
    else:
        raise ValueError(f"Invalid products.json structure in {path}")

    if not isinstance(products, dict):
        raise ValueError(f"Product catalog must be an object map in {path}")

    typed: Dict[str, SkuCatalogEntry] = {}
    for sku, entry in products.items():
        if not isinstance(entry, dict):
            raise ValueError(f"Invalid catalog entry for SKU {sku!r} in {path}")
        typed[str(sku)] = SkuCatalogEntry(
            ean=str(entry["ean"]),
            name=str(entry["name"]),
            **({"price": float(entry["price"])} if "price" in entry else {}),
        )

    _cache = typed
    _cache_mtime = mtime
    logger.info("Loaded %d products from %s", len(_cache), path)
    return _cache


def get_sku_profile(sku: str) -> SkuCatalogEntry:
    pool = get_simulation_sku_pool()
    return pool.get(
        sku,
        {"ean": "5012300000000", "name": sku.replace("-", " ").title()},
    )


def get_unit_price(sku: str, sku_price: Optional[float] = None) -> float:
    """Resolve unit price from SKU state or catalog (0.0 if unknown)."""
    if sku_price is not None:
        return sku_price
    return get_sku_profile(sku).get("price", 0.0)
