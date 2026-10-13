"""Seed shopfloor master catalog into SQLite."""

from services.shopfloor_catalog import catalog_db_path, init_shopfloor_catalog_db


def main() -> None:
    init_shopfloor_catalog_db()
    print(f"Shopfloor master catalog seeded at {catalog_db_path()}")


if __name__ == "__main__":
    main()
