"""Shrink already-downloaded creator images to small WebP thumbnails and update the database.

Stop the Scout server first (it keeps the database in memory and would overwrite the changes).
Usage:  .venv/Scripts/python scripts/compress_images.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import DB_PATH, IMG_DIR  # noqa: E402
from app.images import shrink  # noqa: E402


def main():
    renamed, before, after, skipped = {}, 0, 0, 0
    for path in sorted(IMG_DIR.iterdir()):
        if path.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"):
            continue
        data = path.read_bytes()
        small = shrink(data)
        if not small or len(small) >= len(data):
            skipped += 1
            before += len(data)
            after += len(data)
            continue
        target = path.with_suffix(".webp")
        target.write_bytes(small)
        if target != path:
            path.unlink()
            renamed[f"/img/{path.name}"] = f"/img/{target.name}"
        before += len(data)
        after += len(small)

    if renamed and DB_PATH.exists():
        text = DB_PATH.read_text(encoding="utf-8")
        for old, new in renamed.items():
            text = text.replace(f'"{old}"', f'"{new}"')
        json.loads(text)  # still valid JSON before we overwrite anything
        DB_PATH.write_text(text, encoding="utf-8")

    print(f"Images: {before / 1e6:.1f} MB -> {after / 1e6:.1f} MB "
          f"({len(renamed)} converted, {skipped} left as they were)")


if __name__ == "__main__":
    main()
