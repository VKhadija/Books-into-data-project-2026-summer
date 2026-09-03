"""
3_match_books.py

Two jobs:
1. Fuzzy-match extracted_books.csv (from shelf photos) against
   goodreads_library.csv, so you know which physical books you've
   already logged/rated on Goodreads.
2. Enrich each book with publisher + publication year via the Open
   Library API (free, no key needed) -- since neither the photos nor
   the Goodreads DSAR export reliably give you that.

Setup:
    pip install -r requirements.txt

Usage:
    python 3_match_books.py

Output:
    library_final.csv     -- one row per unique book, merged + enriched
    needs_review.csv      -- low-confidence matches / extractions to check by hand
"""

import csv
import re
import time
from pathlib import Path

import requests
from rapidfuzz import fuzz

EXTRACTED_CSV = Path("extracted_books.csv")
GOODREADS_CSV = Path("goodreads_library.csv")
MATCH_THRESHOLD = 82  # 0-100, title+author similarity score; below this -> needs_review


def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"^(the|a|an)\s+", "", text)
    text = re.split(r"[:\(]", text)[0]  # drop subtitles/parentheticals
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def dedupe_extracted(rows: list[dict]) -> list[dict]:
    """Same physical book can appear once (good). Same book photographed
    twice (e.g. overlapping shelf photos) should be merged, keeping the
    higher-confidence extraction."""
    conf_rank = {"high": 3, "medium": 2, "low": 1, "": 0}
    best: dict[str, dict] = {}
    for row in rows:
        key = normalize(row["title"])
        if not key:
            continue
        if key not in best or conf_rank[row["confidence"]] > conf_rank[best[key]["confidence"]]:
            best[key] = row
    return list(best.values())


def match_against_goodreads(extracted: list[dict], goodreads: list[dict]) -> list[dict]:
    gr_normalized = [(normalize(g["title"]), g) for g in goodreads]

    results = []
    for book in extracted:
        norm_title = normalize(book["title"])
        best_score, best_match = 0, None

        for gr_norm_title, gr_row in gr_normalized:
            score = fuzz.token_sort_ratio(norm_title, gr_norm_title)
            if score > best_score:
                best_score, best_match = score, gr_row

        book = dict(book)
        if best_match and best_score >= MATCH_THRESHOLD:
            book["goodreads_match"] = best_match["title"]
            book["goodreads_rating"] = best_match["rating"]
            book["goodreads_status"] = best_match["read_status"]
            book["match_score"] = best_score
        else:
            book["goodreads_match"] = ""
            book["goodreads_rating"] = ""
            book["goodreads_status"] = ""
            book["match_score"] = best_score if best_match else 0
        results.append(book)
    return results


def enrich_with_openlibrary(book: dict) -> dict:
    """Look up publisher + year via Open Library. Best-effort: silently
    leaves fields blank on failure/no match rather than crashing the run."""
    query_title = book["title"]
    query_author = book.get("author", "")

    try:
        params = {"title": query_title, "limit": 1}
        if query_author:
            params["author"] = query_author
        resp = requests.get("https://openlibrary.org/search.json", params=params, timeout=10)
        resp.raise_for_status()
        docs = resp.json().get("docs", [])
        if docs:
            doc = docs[0]
            book["publisher"] = book.get("publisher") or (doc.get("publisher", [""])[0] if doc.get("publisher") else "")
            book["year"] = doc.get("first_publish_year", "")
            book["ol_subjects"] = ", ".join(doc.get("subject", [])[:5]) if doc.get("subject") else ""
        else:
            book["year"] = ""
            book["ol_subjects"] = ""
    except requests.RequestException:
        book["year"] = ""
        book["ol_subjects"] = ""

    return book


def main():
    extracted = load_csv(EXTRACTED_CSV)
    goodreads = load_csv(GOODREADS_CSV)

    if not extracted:
        print(f"No data in {EXTRACTED_CSV} -- run 2_extract_books.py first.")
        return

    print(f"Loaded {len(extracted)} extracted book rows, {len(goodreads)} Goodreads entries.")

    extracted = dedupe_extracted(extracted)
    print(f"After de-duplication: {len(extracted)} unique books.")

    matched = match_against_goodreads(extracted, goodreads) if goodreads else [
        {**b, "goodreads_match": "", "goodreads_rating": "", "goodreads_status": "", "match_score": 0}
        for b in extracted
    ]

    print("Enriching with Open Library (publisher/year) -- this hits a live API, please be patient...")
    enriched = []
    for i, book in enumerate(matched, 1):
        enriched.append(enrich_with_openlibrary(book))
        if i % 20 == 0:
            print(f"  {i}/{len(matched)}")
        time.sleep(0.2)  # be polite to the free API

    fields = [
        "title", "author", "publisher", "year", "ol_subjects",
        "confidence", "orientation", "source_photo",
        "goodreads_match", "goodreads_rating", "goodreads_status", "match_score",
    ]

    final_path = Path("library_final.csv")
    review_path = Path("needs_review.csv")

    with final_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(enriched)

    needs_review = [
        b for b in enriched
        if b["confidence"] == "low" or (goodreads and int(b["match_score"] or 0) < MATCH_THRESHOLD)
    ]
    with review_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(needs_review)

    print(f"\nDone.")
    print(f"  -> {final_path.resolve()}  ({len(enriched)} books)")
    print(f"  -> {review_path.resolve()}  ({len(needs_review)} to check by hand)")


if __name__ == "__main__":
    main()
