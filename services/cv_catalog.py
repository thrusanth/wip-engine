"""Edge CV product catalog — stock-record names must match character-for-character."""

from __future__ import annotations

from typing import Any

from models.bouncer_schemas import ExpectedLedger
from services.shopfloor_catalog import parent_sku_for_ean

CV_PRODUCT_CATALOG: dict[str, dict[str, Any]] = {
    "walkers_crisps_6pk": {
        "ean": "5000328376677",
        "name": "Walkers Ready Salted Crisps 6x25g",
        "parent_price": 2.35,
        "pack_size": 6,
        "child_sku_suffix": "SINGLE-WASTE",
        "printer_target": "CAM-AISLE-04-ZPL-PRINTER",
    },
    "heinz_beans_4pk": {
        "ean": "5000157024886",
        "name": "Heinz B/Beans In TOMT SCE 4x415g",
        "parent_price": 4.00,
        "pack_size": 4,
        "child_sku_suffix": "SINGLE-WASTE",
        "printer_target": "CAM-AISLE-02-ZPL-PRINTER",
    },
    "coca_cola_8pk": {
        "ean": "5449000058386",
        "name": "Coca Cola Regular 8x330ml",
        "parent_price": 6.00,
        "pack_size": 8,
        "child_sku_suffix": "SINGLE-WASTE",
        "printer_target": "CAM-AISLE-05-ZPL-PRINTER",
    },
    "schweppes_lemonade_2l": {
        "ean": "5000193900861",
        "name": "Schweppes Lemonade 2L BTL",
        "parent_price": 2.00,
        "pack_size": 1,
        "child_sku_suffix": "SINGLE-WASTE",
        "printer_target": "CAM-AISLE-05-ZPL-PRINTER",
    },
    "fosters_lager_4pk": {
        "ean": "5035766185239",
        "name": "Fosters Lager 4x440ml",
        "parent_price": 4.50,
        "pack_size": 4,
        "child_sku_suffix": "SINGLE-WASTE",
        "printer_target": "CAM-AISLE-06-ZPL-PRINTER",
    },
    "galaxy_cookie_180g": {
        "ean": "5060402904776",
        "name": "Galaxy Cookie 180g",
        "parent_price": 2.50,
        "pack_size": 1,
        "child_sku_suffix": "SINGLE-WASTE",
        "printer_target": "CAM-AISLE-03-ZPL-PRINTER",
    },
    "doritos_cool_original_sharing_bag": {
        "ean": "5000328028613",
        "name": "Doritos Tortilla Chips Cool Original Sharing Bag Crisps",
        "parent_price": 2.75,
        "pack_size": 1,
        "child_sku_suffix": "SINGLE-WASTE",
        "printer_target": "CAM-AISLE-04-ZPL-PRINTER",
    },
    "asahi_super_dry_620ml": {
        "ean": "8008440246066",
        "name": "Asahi Super Dry 5% 620ml",
        "parent_price": 3.55,
        "pack_size": 1,
        "child_sku_suffix": "SINGLE-WASTE",
        "printer_target": "CAM-AISLE-06-ZPL-PRINTER",
    },
}


def _fixture_from_printer_target(printer_target: str) -> str:
    text = str(printer_target)
    if "-ZPL-PRINTER" in text:
        return text.split("-ZPL-PRINTER")[0]
    return "CAM-AISLE-04"


def resolve_cv_catalog_item(identifier: str) -> tuple[str, dict[str, Any]] | None:
    """
    Resolve a catalog entry by slug key, exact stock `name`, or EAN.
    Returns (catalog_key, item dict).
    """
    if identifier in CV_PRODUCT_CATALOG:
        return identifier, CV_PRODUCT_CATALOG[identifier]

    for key, item in CV_PRODUCT_CATALOG.items():
        if item.get("name") == identifier:
            return key, item
        if item.get("ean") == identifier:
            return key, item

    return None


def expected_ledger_from_cv_item(item: dict[str, Any]) -> ExpectedLedger:
    ean = str(item["ean"])
    parent = parent_sku_for_ean(ean)
    pack_size = max(1, int(item["pack_size"]))
    printer_target = str(item.get("printer_target") or "")
    fixture = _fixture_from_printer_target(printer_target)
    is_alcohol = "lager" in str(item.get("name", "")).lower() or "fosters" in str(
        item.get("name", "")
    ).lower()

    return ExpectedLedger(
        parent_sku=parent,
        ean=ean,
        expected_quantity=pack_size * 2,
        planogram_location=fixture,
        expected_format="SHRINK_WRAPPED_MULTIPACK",
        linked_child_sku=f"{parent}-SINGLE",
        retail_price=float(item["parent_price"]),
        pack_quantity=pack_size,
        is_alcohol=is_alcohol,
        abv_strength=4.0 if is_alcohol else None,
        volume_litres=0.44 if is_alcohol else None,
        excise_duty=0.45 if is_alcohol else None,
        vat_amount=0.20 if is_alcohol else None,
    )
