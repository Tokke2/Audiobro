"""Värm Goodreads-cachen rad för rad (med pauser) så att GUI-demon kan köras
helt deterministiskt utan nya anrop. Används bara för demo/skärmdumpar."""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ags.goodreads import Goodreads, GoodreadsBlocked  # noqa: E402

QUERIES = [
    "Isprinsessan",
    "Harry Potter and the Philosopher's Stone J.K. Rowling",
    "Harry Potter J.K. Rowling",
    "Harry Potter 1",
    "Män som hatar kvinnor Stieg Larsson",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=2.5)
    ap.add_argument("--tries", type=int, default=6)
    ap.add_argument("--cooldown", type=float, default=45)
    args = ap.parse_args()

    g = Goodreads(min_delay=args.delay)
    for q in QUERIES:
        url = g.search_url(q)
        if url in g._cache:
            print(f"[cache] {q}")
            continue
        ok = False
        for i in range(args.tries):
            try:
                books = g.search(q, limit=8)
                print(f"[ok {len(books)}] {q}")
                ok = True
                break
            except GoodreadsBlocked:
                print(f"[blockerad, väntar {args.cooldown:.0f}s] {q}")
                time.sleep(args.cooldown)
        if not ok:
            print(f"[misslyckades] {q}")
    g.save_cache()
    g.close()
    print(f"cache: {g.cache_size()} poster")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
