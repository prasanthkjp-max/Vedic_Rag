"""Regression test for search_engine.VedicSearchEngine.load_index().

Guards the critical bug where load_index() referenced `page_map`/`emb_list`
before they were initialised, raising a NameError that the broad except
swallowed — leaving the RAG index permanently empty (zero grounding passages
for every AI prediction/chat/marriage reading).

Standalone, no server/network needed: seeds a real page row with a valid
embedding blob into an isolated temp DB and asserts the index actually loads it.
Run: python3 test_search_index_load.py  (exit 0 = pass, 1 = fail)
"""
import os
import struct
import sqlite3
import tempfile
import sys

from config import EMBEDDING_DIM, connect_db, ensure_fts
from search_engine import VedicSearchEngine


def _seed_db(path):
    conn = connect_db(path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS books (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "filename TEXT UNIQUE, title TEXT, total_pages INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS pages (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "book_id INTEGER, page_num INTEGER, raw_text TEXT, embedding BLOB, "
        "UNIQUE(book_id, page_num))"
    )
    cur.execute("INSERT INTO books (filename, title, total_pages) VALUES (?, ?, ?)",
                ("brihat.pdf", "Brihat Parashara Hora Shastra", 1))
    book_id = cur.lastrowid
    # A correctly-dimensioned embedding blob (EMBEDDING_DIM 4-byte floats).
    vec = [0.1] * EMBEDDING_DIM
    blob = struct.pack(f"{EMBEDDING_DIM}f", *vec)
    cur.execute(
        "INSERT INTO pages (book_id, page_num, raw_text, embedding) VALUES (?, ?, ?, ?)",
        (book_id, 1, "The seventh house governs marriage and the spouse.", blob),
    )
    conn.commit()
    ensure_fts(conn)
    conn.close()


def main():
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "vedic_rag_test.db")
        _seed_db(db_path)

        se = VedicSearchEngine(db_path=db_path)

        if len(se.page_map) == 1:
            print("[PASS] load_index: seeded page loaded into page_map")
        else:
            print(f"[FAIL] load_index: page_map len == {len(se.page_map)}, expected 1")
            failures += 1

        if se.embeddings is not None and se.embeddings.shape[0] == 1:
            print("[PASS] load_index: embeddings matrix populated")
        else:
            shape = None if se.embeddings is None else se.embeddings.shape
            print(f"[FAIL] load_index: embeddings shape == {shape}, expected (1, {EMBEDDING_DIM})")
            failures += 1

    if failures:
        print(f"\n{failures} CHECK(S) FAILED")
        sys.exit(1)
    print("\nALL SEARCH INDEX LOAD CHECKS PASS")


if __name__ == "__main__":
    main()
