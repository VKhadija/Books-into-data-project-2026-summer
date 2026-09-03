# Bookshelf → Data pipeline

Three scripts, run in order.

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."   # needed for step 2 only
```

## Step 1 — Clean up your Goodreads export

```bash
python 1_export_goodreads.py Goodreads.zip
```

Works whether you point it at the outer `Goodreads.zip`, an unzipped
folder, or `review.zip`/`review.json` directly.

→ produces `goodreads_library.csv` (title, rating, read_status, dates).

## Step 2 — Extract books from shelf photos

```bash
python 2_extract_books.py path/to/photos_folder
```

Sends each photo to Claude and asks for structured JSON per book
(title, author, publisher if visible, confidence, spine/cover). This is
deliberately a vision-LLM call rather than classic OCR (Tesseract/EasyOCR) —
spine text is usually rotated, decoratively fonted, and crammed dozens
to a photo, which classic OCR handles poorly.

Tips for best accuracy:
- Crop photos to one shelf at a time rather than a whole bookcase.
- Make sure no spines are cut off at the frame edge.
- The script is resumable — safe to Ctrl-C and rerun; it skips photos
  already in `extracted_books.jsonl`.

→ produces `extracted_books.jsonl` (raw, resumable) and
  `extracted_books.csv` (flattened, one row per book).

## Step 3 — Match against Goodreads + enrich metadata

```bash
python 3_match_books.py
```

- Fuzzy-matches each extracted book against your Goodreads titles
  (using `rapidfuzz`, not exact string matching — handles subtitle/
  punctuation/prefix differences).
- Looks up publisher + first-publish year for each book via the free
  Open Library API (no key required).
- Splits output into a clean final file and a review pile for anything
  low-confidence.

→ produces `library_final.csv` (your main dataset) and
  `needs_review.csv` (low-confidence extractions/matches to eyeball
  by hand).

## Known limitations, going in

- **Publisher location isn't in Open Library reliably** — for the
  "geography of publishers" visualization, you'll likely need to
  hand-map your most common publishers (Penguin Random House, Suhrkamp,
  TEAS Press, etc.) to a headquarters city/country. With 300+ books this
  is usually a small enough set (maybe 30-50 unique publishers) to do
  by hand once, rather than something worth automating.
- **Match threshold** (`MATCH_THRESHOLD = 82` in step 3) — lower it if
  too many real matches land in `needs_review.csv`; raise it if you're
  getting false-positive matches.
- **Multilingual titles** (Azerbaijani/German/English) can occasionally
  trip up fuzzy matching if Goodreads has a translated title and the
  spine has the original, or vice versa. Those will land in the review
  pile rather than silently mismatching.
