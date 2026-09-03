"""
run_free_ocr.py

FREE version - no API key, no billing, everything runs locally on your
computer using EasyOCR.

Put this file in the SAME folder as your shelf photos, open it in
Spyder, and press the green Run button (or F5).

Honest tradeoff vs. the paid API version: classic OCR struggles more
with angled/rotated spine text than the vision-API approach does, so
expect to do more manual cleanup afterward. It reads raw text off each
photo into a CSV - it does NOT separate "title" from "author"
automatically, since that needs actual reading comprehension, not just
character recognition. You (or you + me in chat, for free) will sort
title-vs-author out from the raw text afterward.

First run will download a small language model (one-time, needs
internet connection, no cost).
"""

import subprocess
import sys

def install_if_missing(package, import_name=None):
    import_name = import_name or package
    try:
        __import__(import_name)
    except ImportError:
        print("Installing " + package + " ... (this can take a few minutes the first time)")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

install_if_missing("easyocr")

import csv
from pathlib import Path

import easyocr

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# Languages to read. "en" = English, "az" = Azerbaijani not supported
# by EasyOCR directly, so we use a Latin-alphabet-friendly set that
# handles most Azerbaijani characters reasonably well. Add more codes
# if you have books in other languages, e.g. "de" for German, "ru" for
# Russian (Cyrillic - use as a separate run, mixing scripts hurts
# accuracy).
LANGUAGES = ["en"]


def main():
    this_folder = Path(__file__).parent
    photos = sorted(p for p in this_folder.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS)

    if not photos:
        print("No photos found in " + str(this_folder))
        print("Make sure this script is saved in the same folder as your photos.")
        return

    print("Found " + str(len(photos)) + " photo(s) in " + str(this_folder))
    print("Loading OCR model (first run downloads it, can take a minute)...")

    reader = easyocr.Reader(LANGUAGES)

    rows = []
    for i, photo in enumerate(photos, 1):
        print("[" + str(i) + "/" + str(len(photos)) + "] " + photo.name + " ...", end=" ", flush=True)
        try:
            results = reader.readtext(str(photo))
        except Exception as e:
            print("ERROR: " + str(e))
            continue

        for (bbox, text, confidence) in results:
            text = text.strip()
            if len(text) < 2:
                continue  # skip stray single characters / noise
            rows.append({
                "raw_text": text,
                "ocr_confidence": round(confidence, 2),
                "source_photo": photo.name,
            })
        print("found " + str(len(results)) + " text block(s)")

    csv_path = this_folder / "ocr_raw_text.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["raw_text", "ocr_confidence", "source_photo"])
        writer.writeheader()
        writer.writerows(rows)

    print("")
    print("Done! " + str(len(rows)) + " text blocks extracted.")
    print("Open this file to see results: " + str(csv_path))
    print("")
    print("Next: this is RAW text, not yet sorted into title/author.")
    print("You can review ocr_raw_text.csv yourself, or paste rows from it")
    print("back into a chat with Claude to help sort out which text is a")
    print("title vs an author vs junk, for free.")


if __name__ == "__main__":
    main()