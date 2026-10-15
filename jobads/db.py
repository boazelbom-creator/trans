"""SQLite database of ads (PRD §12)."""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

STATUS_NEW = "new"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_DISTRIBUTED = "distributed"
STATUSES = (STATUS_NEW, STATUS_APPROVED, STATUS_REJECTED, STATUS_DISTRIBUTED)

STATUS_LABELS = {
    STATUS_NEW: "חדשה",
    STATUS_APPROVED: "מאושרת",
    STATUS_REJECTED: "נדחתה",
    STATUS_DISTRIBUTED: "הופצה",
}

MANUAL_SOURCE = "ידני"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    community       TEXT NOT NULL,
    collect_date    TEXT NOT NULL,
    distribute_date TEXT NOT NULL DEFAULT '',
    source_name     TEXT NOT NULL DEFAULT '',
    source_url      TEXT NOT NULL DEFAULT '',
    origin_ad       TEXT NOT NULL,
    origin_hash     TEXT NOT NULL,
    sonnet_ad       TEXT NOT NULL,
    user_ad         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'new',
    tags            TEXT NOT NULL DEFAULT '[]',
    keywords        TEXT NOT NULL DEFAULT '[]',
    score           INTEGER NOT NULL DEFAULT 0,
    score_reason    TEXT NOT NULL DEFAULT '',
    model           TEXT NOT NULL DEFAULT '',
    prompt_version  TEXT NOT NULL DEFAULT '',
    updated_at      TEXT NOT NULL,
    origin_images   TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS ads_community_hash ON ads (community, origin_hash);
"""

# Columns for the presenting screen: everything except the ad texts.
_LIST_COLUMNS = (
    "id, community, collect_date, distribute_date, source_name, source_url, status, "
    "tags, keywords, score, model, prompt_version, updated_at"
)


class DatabaseError(Exception):
    """The database cannot be opened. The message is shown to the user."""


@dataclass
class Ad:
    id: int
    community: str
    collect_date: str
    distribute_date: str
    source_name: str
    source_url: str
    status: str
    tags: list[str]
    keywords: list[str]
    score: int
    model: str
    prompt_version: str
    updated_at: str
    origin_ad: str = ""
    sonnet_ad: str = ""
    user_ad: str = ""
    score_reason: str = ""
    origin_hash: str = ""
    origin_images: list[str] = field(default_factory=list)


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _row_to_ad(row: sqlite3.Row) -> Ad:
    data = dict(row)
    data["tags"] = json.loads(data["tags"] or "[]")
    data["keywords"] = json.loads(data["keywords"] or "[]")
    if "origin_images" in data:
        data["origin_images"] = json.loads(data["origin_images"] or "[]")
    return Ad(**data)


class Database:
    def __init__(self, path: Path):
        self.path = path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(path)
            self.conn.row_factory = sqlite3.Row
            if self.conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError("quick_check failed")
            self.conn.executescript(_SCHEMA)
            self._migrate()
            self.conn.commit()
        except sqlite3.DatabaseError as e:
            raise DatabaseError(f"קובץ מסד הנתונים פגום ולא ניתן לפתוח אותו:\n{path}\n{e}") from e
        except OSError as e:
            raise DatabaseError(f"לא ניתן ליצור את מסד הנתונים:\n{path}\n{e}") from e

    def _migrate(self) -> None:
        """Add columns introduced after the first version, to databases created before them."""
        columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(ads)")}
        if "origin_images" not in columns:
            self.conn.execute("ALTER TABLE ads ADD COLUMN origin_images TEXT NOT NULL DEFAULT '[]'")

    def close(self) -> None:
        self.conn.close()

    def add_ad(
        self,
        *,
        community: str,
        source_name: str,
        source_url: str,
        origin_ad: str,
        origin_hash: str,
        sonnet_ad: str,
        tags: list[str],
        keywords: list[str],
        score: int,
        score_reason: str,
        model: str,
        prompt_version: str,
    ) -> int:
        ts = now()
        cur = self.conn.execute(
            """INSERT INTO ads (community, collect_date, source_name, source_url, origin_ad, origin_hash,
                               sonnet_ad, user_ad, status, tags, keywords, score, score_reason,
                               model, prompt_version, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                community, ts, source_name, source_url, origin_ad, origin_hash,
                sonnet_ad, sonnet_ad, STATUS_NEW,
                json.dumps(tags, ensure_ascii=False), json.dumps(keywords, ensure_ascii=False),
                score, score_reason, model, prompt_version, ts,
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def find_by_hash(self, community: str, origin_hash: str) -> int | None:
        row = self.conn.execute(
            "SELECT id FROM ads WHERE community = ? AND origin_hash = ? ORDER BY id LIMIT 1",
            (community, origin_hash),
        ).fetchone()
        return row["id"] if row else None

    def get_ad(self, ad_id: int) -> Ad | None:
        row = self.conn.execute("SELECT * FROM ads WHERE id = ?", (ad_id,)).fetchone()
        return _row_to_ad(row) if row else None

    def list_ads(self, community: str) -> list[Ad]:
        rows = self.conn.execute(
            f"SELECT {_LIST_COLUMNS} FROM ads WHERE community = ? ORDER BY collect_date DESC, id DESC",
            (community,),
        ).fetchall()
        return [_row_to_ad(r) for r in rows]

    def set_images(self, ad_id: int, names: list[str]) -> None:
        self.conn.execute(
            "UPDATE ads SET origin_images = ? WHERE id = ?", (json.dumps(names, ensure_ascii=False), ad_id)
        )
        self.conn.commit()

    def update_text(self, ad_id: int, user_ad: str) -> None:
        self.conn.execute("UPDATE ads SET user_ad = ?, updated_at = ? WHERE id = ?", (user_ad, now(), ad_id))
        self.conn.commit()

    def set_status(self, ad_id: int, status: str) -> None:
        if status not in STATUSES:
            raise ValueError(status)
        self.conn.execute("UPDATE ads SET status = ?, updated_at = ? WHERE id = ?", (status, now(), ad_id))
        self.conn.commit()

    def mark_distributed(self, ad_id: int) -> None:
        ts = now()
        self.conn.execute(
            "UPDATE ads SET status = ?, distribute_date = ?, updated_at = ? WHERE id = ?",
            (STATUS_DISTRIBUTED, ts, ts, ad_id),
        )
        self.conn.commit()
