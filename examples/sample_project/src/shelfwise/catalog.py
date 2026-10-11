"""Book catalogue search."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Book:
    id: int
    isbn: str
    title: str
    author: str


def search_titles(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[Book]:
    """Case-insensitive substring search over titles and authors."""
    pattern = f"%{query.lower()}%"
    rows = conn.execute(
        "SELECT id, isbn, title, author FROM books "
        "WHERE lower(title) LIKE ? OR lower(author) LIKE ? ORDER BY title LIMIT ?",
        (pattern, pattern, limit),
    ).fetchall()
    return [Book(*row) for row in rows]
