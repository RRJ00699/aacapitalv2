#!/usr/bin/env python3
"""Verify staged D1 objects locally and emit (but never execute) promotion SQL."""
from __future__ import annotations

import argparse
import hashlib
import sqlite3


def verified_objects(path: str):
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    sql = """SELECT s.object_key,s.sha256,s.content_type,s.byte_length,
                    GROUP_CONCAT(hex(c.chunk), '') payload_hex
             FROM ipomatrix_raw_stage s
             JOIN ipomatrix_raw_stage_chunks c ON c.object_key=s.object_key
             GROUP BY s.object_key,s.sha256,s.content_type,s.byte_length
             HAVING COUNT(*)=MAX(c.chunk_count) AND MIN(c.chunk_count)=MAX(c.chunk_count)"""
    for key, expected, content_type, byte_length, payload_hex in conn.execute(sql):
        payload = bytes.fromhex(payload_hex or "")
        actual = hashlib.sha256(payload).hexdigest()
        if actual.lower() == expected.lower() and len(payload) == byte_length:
            yield key, expected, content_type, payload
    conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("database")
    p.add_argument("--output", required=True, help="SQL artifact for owner review")
    a = p.parse_args()
    rows = list(verified_objects(a.database))
    with open(a.output, "w", encoding="utf-8") as out:
        out.write("-- GENERATED LOCALLY; OWNER APPROVAL REQUIRED BEFORE EXECUTION.\nBEGIN;\n")
        for key, digest, content_type, payload in rows:
            q = lambda s: "'" + s.replace("'", "''") + "'"
            out.write("INSERT INTO raw_objects(object_key,sha256,content_type,body) VALUES "
                      f"({q(key)},{q(digest)},{q(content_type)},X'{payload.hex()}') "
                      "ON CONFLICT(object_key) DO NOTHING;\n")
        out.write("COMMIT;\n")
    print(f"verified={len(rows)} proposed_promotions={len(rows)} output={a.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
