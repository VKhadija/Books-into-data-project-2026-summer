import base64
import csv
import json
import sys
from pathlib import Path

import anthropic

MODEL = "claude-sonnet-4-6"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

SYSTEM_PROMPT = """You are cataloguing a home bookshelf from a photo. Read every \
book spine and cover you can see, including partially visible or angled ones.

For each book, extract:
- title (as printed; keep original language/script, don't translate)
- author (if visible; null if not)
- publisher (only if clearly visible, e.g. on a flat cover; usually null for spines)
- confidence: "high" (clearly legible), "medium" (mostly legible, some guessing), \
or "low" (partially cropped, blurry, or a best-effort guess)
- orientation: "spine" or "cover" (cover = book lying flat or facing out)

Skip non-book objects (decorations, photo frames, etc). If a spine is fully \
illegible, omit it rather than guessing wildly.

Respond with ONLY a JSON array, no other text, no markdown fences. Example:
[
  {"title": "Xəmsə", "author": "Nizami Gəncəvi", "publisher": "TEAS Press", \
"confidence": "high", "orientation": "cover"},
  {"title": "Feminizm hər kəs üçündür", "author": "bell hooks", "publisher": null, \
"confidence": "high", "orientation": "spine"}
]"""


def encode_image(path: Path) -> tuple[str, str]:
    media_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }[path.suffix.lower()]
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    return data, media_type


def extract_from_image(client: anthropic.Anthropic, path: Path) -> list[dict]:
    data, media_type = encode_image(path)

    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": data,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Extract every book you can see in this shelf photo.",
                    },
                ],
            }
        ],
    )

    text = "".join(block.text for block in response.content if block.type == "text")
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print(f"  [warn] could not parse JSON for {path.name}, skipping. Raw response:")
        print(f"  {text[:300]}")
        return []


def main():
    if len(sys.argv) != 2:
        print("Usage: python 2_extract_books.py <path to photos folder>")
        sys.exit(1)

    photos_dir = Path(sys.argv[1])
    photos = sorted(
        p for p in photos_dir.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not photos:
        print(f"No images found in {photos_dir}")
        sys.exit(1)

    jsonl_path = Path("extracted_books.jsonl")

    already_done = set()
    if jsonl_path.exists():
        with jsonl_path.open(encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                already_done.add(row["source_photo"])
        print(f"Resuming: {len(already_done)} photos already processed.")

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    with jsonl_path.open("a", encoding="utf-8") as out:
        for i, photo in enumerate(photos, 1):
            if photo.name in already_done:
                continue
            print(f"[{i}/{len(photos)}] {photo.name} ...", end=" ", flush=True)
            try:
                books = extract_from_image(client, photo)
            except Exception as e:
                print(f"ERROR: {e}")
                continue
            out.write(json.dumps({"source_photo": photo.name, "books": books}, ensure_ascii=False) + "\n")
            out.flush()
            print(f"found {len(books)} book(s)")

    # flatten to CSV
    rows = []
    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            for book in row["books"]:
                rows.append(
                    {
                        "title": book.get("title", ""),
                        "author": book.get("author") or "",
                        "publisher": book.get("publisher") or "",
                        "confidence": book.get("confidence", ""),
                        "orientation": book.get("orientation", ""),
                        "source_photo": row["source_photo"],
                    }
                )

    csv_path = Path("extracted_books.csv")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["title", "author", "publisher", "confidence", "orientation", "source_photo"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nDone. {len(rows)} books extracted from {len(photos)} photos.")
    print(f"  -> {jsonl_path.resolve()}  (raw, resumable)")
    print(f"  -> {csv_path.resolve()}  (flattened)")


if __name__ == "__main__":
    main()
