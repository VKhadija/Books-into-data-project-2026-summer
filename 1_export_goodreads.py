"""
1_export_goodreads.py

Parses a Goodreads DSAR ("download my data") export and produces a clean
CSV baseline of your library.

Note: the DSAR export only contains title, rating, read_status, and
timestamps -- no author, publisher, ISBN, or year. Those get filled in
later, either from the shelf-photo extraction (3_match_books.py) or from
a lookup API like Open Library.

Usage:
    python 1_export_goodreads.py path/to/Goodreads.zip
    python 1_export_goodreads.py path/to/already_unzipped_folder

Output:
    goodreads_library.csv
"""

import csv
import json
import sys
import zipfile
from pathlib import Path


def load_review_json(source: Path) -> list[dict]:
    """Find and load review.json, whether source is the outer zip,
    an unzipped folder, or the inner review.zip / review.json directly."""

    if source.is_file() and source.suffix == ".json":
        return json.loads(source.read_text(encoding="utf-8"))

    if source.is_file() and source.suffix == ".zip":
        with zipfile.ZipFile(source) as outer:
            names = outer.namelist()

            # Case A: outer zip is the top-level Goodreads.zip containing review.zip
            if "review.zip" in names:
                with outer.open("review.zip") as inner_fp:
                    with zipfile.ZipFile(inner_fp) as inner:
                        with inner.open("review.json") as f:
                            return json.load(f)

            # Case B: outer zip IS review.zip
            if "review.json" in names:
                with outer.open("review.json") as f:
                    return json.load(f)

        raise FileNotFoundError(
            "Could not find review.json or review.zip inside the given zip."
        )

    if source.is_dir():
        # look for review.json directly, or review.zip inside the folder
        direct = source / "review.json"
        if direct.exists():
            return json.loads(direct.read_text(encoding="utf-8"))

        nested_zip = source / "review.zip"
        if nested_zip.exists():
            return load_review_json(nested_zip)

        # search recursively as a last resort
        matches = list(source.rglob("review.json"))
        if matches:
            return json.loads(matches[0].read_text(encoding="utf-8"))

    raise FileNotFoundError(f"Could not locate review.json starting from {source}")


def main():
    if len(sys.argv) != 2:
        print("Usage: python 1_export_goodreads.py <path to Goodreads.zip or folder>")
        sys.exit(1)

    source = Path(sys.argv[1])
    data = load_review_json(source)

    # first item in the DSAR export is usually just an "explanation" block, skip it
    entries = [d for d in data if "book" in d]

    out_path = Path("goodreads_library.csv")
    fields = ["title", "rating", "read_status", "date_added", "date_last_updated"]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for e in entries:
            writer.writerow(
                {
                    "title": e.get("book", "").strip(),
                    "rating": e.get("rating", ""),
                    "read_status": e.get("read_status", ""),
                    "date_added": e.get("created_at", ""),
                    "date_last_updated": e.get("updated_at", ""),
                }
            )

    print(f"Wrote {len(entries)} entries to {out_path.resolve()}")
    by_status = {}
    for e in entries:
        s = e.get("read_status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1
    for status, count in sorted(by_status.items(), key=lambda x: -x[1]):
        print(f"  {status}: {count}")


if __name__ == "__main__":
    main()
