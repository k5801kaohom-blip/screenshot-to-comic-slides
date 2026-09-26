#!/usr/bin/env python3
"""Create ordered contact sheets from a slide-image manifest or plain path list."""

import argparse
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def load_items(path: Path):
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        items = []
        for i, item in enumerate(data, 1):
            if isinstance(item, str):
                items.append((i, Path(item), ""))
            else:
                items.append((int(item.get("slide_number", i)), Path(item["source_path"]), item.get("title_hint", "")))
        return items
    items = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if line and not line.startswith("#"):
            items.append((i, Path(line), ""))
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", type=Path)
    ap.add_argument("output_dir", type=Path)
    ap.add_argument("--columns", type=int, default=3)
    ap.add_argument("--rows", type=int, default=4)
    ap.add_argument("--thumb-width", type=int, default=420)
    args = ap.parse_args()

    items = load_items(args.manifest)
    if not items:
        raise SystemExit("Manifest has no images")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    tw = args.thumb_width
    th = round(tw * 9 / 16)
    label_h = 48
    margin = 18
    per_sheet = args.columns * args.rows
    sw = args.columns * tw + (args.columns + 1) * margin
    sh = args.rows * (th + label_h) + (args.rows + 1) * margin
    font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    font = ImageFont.truetype(str(font_path), 19) if font_path.exists() else ImageFont.load_default()

    outputs = []
    for offset in range(0, len(items), per_sheet):
        sheet = Image.new("RGB", (sw, sh), "white")
        draw = ImageDraw.Draw(sheet)
        for j, (number, img_path, title) in enumerate(items[offset:offset + per_sheet]):
            if not img_path.exists():
                raise FileNotFoundError(img_path)
            row, col = divmod(j, args.columns)
            x = margin + col * tw
            y = margin + row * (th + label_h)
            im = Image.open(img_path).convert("RGB")
            im.thumbnail((tw, th), Image.Resampling.LANCZOS)
            sheet.paste(im, (x + (tw - im.width) // 2, y + (th - im.height) // 2))
            draw.rectangle((x, y + th, x + tw, y + th + label_h), fill=(238, 242, 245))
            label = f"{number:02d}  {title or img_path.stem}"
            if len(label) > 44:
                label = label[:41] + "..."
            draw.text((x + 10, y + th + 11), label, fill=(11, 33, 54), font=font)
        out = args.output_dir / f"contact_{offset // per_sheet + 1:02d}.jpg"
        sheet.save(out, quality=92)
        outputs.append(str(out))

    print(json.dumps({"count": len(items), "contact_sheets": outputs}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
