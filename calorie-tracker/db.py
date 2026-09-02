"""
Storage layer.

By default this uses a local SQLite file (calorie-tracker/data/calories.db) -
good for running the app on your own computer.

If TURSO_DATABASE_URL is set (used when this app is deployed to a host with
no permanent disk, e.g. Render's free tier), it talks to a remote Turso
(libSQL) database instead, so your logged meals survive redeploys/restarts.

Either way, callers use the same three functions: query(), query_one(), execute().
Rows support both row["column"] and row[0] access.
"""

import os
import sqlite3

from flask import g

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_DB_PATH = os.path.join(BASE_DIR, "data", "calories.db")

TURSO_URL = os.environ.get("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")
USE_TURSO = bool(TURSO_URL)

_turso_client = None
if USE_TURSO:
    import libsql_client

    _turso_client = libsql_client.create_client_sync(url=TURSO_URL, auth_token=TURSO_AUTH_TOKEN)
else:
    os.makedirs(os.path.dirname(LOCAL_DB_PATH), exist_ok=True)


def _local_conn():
    if "db" not in g:
        g.db = sqlite3.connect(LOCAL_DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_local(exception=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def query(sql, params=()):
    if USE_TURSO:
        return list(_turso_client.execute(sql, list(params)).rows)
    return _local_conn().execute(sql, params).fetchall()


def query_one(sql, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql, params=()):
    if USE_TURSO:
        result = _turso_client.execute(sql, list(params))
        return result.last_insert_rowid
    conn = _local_conn()
    cur = conn.execute(sql, params)
    conn.commit()
    return cur.lastrowid


def init_db():
    execute(
        """
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_date TEXT NOT NULL,
            entry_time TEXT NOT NULL,
            description TEXT,
            calories INTEGER NOT NULL,
            protein_g REAL,
            carbs_g REAL,
            fat_g REAL,
            source TEXT NOT NULL,
            photo_path TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
