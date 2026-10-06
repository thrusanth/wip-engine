import os
import sqlite3

DB_PATH = os.getenv("EDGE_BUFFER_PATH", "edge_buffer.db")


def init_edge_buffer(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_queue (
            event_id TEXT PRIMARY KEY,
            sku TEXT NOT NULL,
            action TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending'
        );
        """
    )
    return conn


def ensure_edge_buffer(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Initialize the local edge buffer if it does not exist yet."""
    return init_edge_buffer(db_path)


if __name__ == "__main__":
    init_edge_buffer()
    print(f"Edge buffer database initialized at {DB_PATH} (WAL mode enabled).")
