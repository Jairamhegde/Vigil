"""
First-start data load for PostgreSQL.

Locally, run.py loads data/ into SQLite before the server starts. On Azure the API container starts
against an empty Azure Database for PostgreSQL, so the first start loads data/ and computes the
metrics. Later starts find the data already there and skip it (use Refresh data to reload).
A PostgreSQL advisory lock makes sure two replicas never load at the same time.
"""
import logging
import time

from backend.db_connection import IS_POSTGRES, connect_db

LOAD_LOCK_ID = 7_314_202_611   # any constant shared by every replica


def _has_data(conn):
    if conn.execute("SELECT to_regclass('identity_metrics')").fetchone()[0] is None:
        return False
    return conn.execute("SELECT COUNT(*) FROM identity_metrics").fetchone()[0] > 0


def ensure_data_loaded():
    """Load data/ into PostgreSQL if it is empty. Returns True when a load ran. No-op on SQLite."""
    if not IS_POSTGRES:
        return False

    from backend.insert_data import load_all
    from backend.metrics import run as compute_metrics

    lock = connect_db()

    try:
        lock.execute("SELECT pg_advisory_lock(?)", (LOAD_LOCK_ID,))

        if _has_data(lock):
            return False

        started = time.time()
        logging.warning("Empty database: loading data/ into PostgreSQL (first start)...")
        counts = load_all()
        as_of, scored = compute_metrics()
        logging.warning(f"Loaded {counts}, scored {scored} identities as of {as_of} "
                        f"in {time.time() - started:.1f}s")
        return True
    finally:
        try:
            lock.execute("SELECT pg_advisory_unlock(?)", (LOAD_LOCK_ID,))
        finally:
            lock.close()
