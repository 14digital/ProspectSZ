"""Local persistence; no credentials are stored."""
import json
import os
import sqlite3
from pathlib import Path

from .pipeline import Prospect


class Store:
    def __init__(self, path=None):
        path = Path(path or os.getenv("PROSPECTSZ_DB", "data/pipeline.sqlite3"))
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS prospects (website TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, at TEXT DEFAULT CURRENT_TIMESTAMP, website TEXT, action TEXT)")

    def connect(self):
        return sqlite3.connect(self.path, timeout=15)

    def all(self):
        with self.connect() as db:
            return [Prospect(**json.loads(row[0])) for row in db.execute("SELECT payload FROM prospects ORDER BY website")]

    def save(self, prospect, action):
        with self.connect() as db:
            db.execute("INSERT INTO prospects VALUES (?, ?) ON CONFLICT(website) DO UPDATE SET payload=excluded.payload",
                       (prospect.website, json.dumps(prospect.export())))
            db.execute("INSERT INTO audit(website, action) VALUES (?, ?)", (prospect.website, action))

    def delete(self, website):
        with self.connect() as db:
            db.execute("DELETE FROM prospects WHERE website=?", (website,))
            db.execute("DELETE FROM audit WHERE website=?", (website,))

    def audit(self):
        with self.connect() as db:
            return [{"at": r[0], "website": r[1], "action": r[2]} for r in db.execute(
                "SELECT at, website, action FROM audit ORDER BY id DESC LIMIT 100")]
