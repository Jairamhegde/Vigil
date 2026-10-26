import logging
import sqlite3

from utils.path import GUARD_DB


def connect_db(db_path=GUARD_DB):
    try:
        conn = sqlite3.connect(db_path)
        return conn
    except Exception as e:
        logging.error(f"Failed to connect to the database :{e}")
