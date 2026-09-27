#!/usr/bin/env python3
"""Second pass: crop the title area, upscale, and ask the model for a tight bbox."""

import argparse
import base64
import concurrent.futures as cf
import io
import json
import re
from pathlib import Path
from PIL import Image
from openai import OpenAI

SCHEMA = {
    "type": "object",
    "properties": {
        "title_text": {"type": "string"},
        "title_bbox": {"type": "array", "items": {"type": "number"}},
        "subtitle_text": {"type": "string"},
        "subtitle_bbox": {"type": "array", "items": {"type": "number"}}
    },
    "required": ["title_text", "title_bbox", "subtitle_text", "subtitle_bbox"],
    "additionalProperties": False
}

SYSTEM = """這是一張簡報投影片左上角的放大裁切圖。請找出「最大的主標題文字」以及正下方的「副標題／一行說明」。
回傳正規化座標 [x0, y0, x1, y1]，範圍 0 到 1，原點在左上角，務必緊貼文字外框（可外擴 0.5%）。
只框選文字本身，不要包含圖示、插圖或 LOGO。
標題文字請「完整照抄」，即使文字延伸到裁切邊緣也要全部寫出，不可省略或截斷。
沒有副標題時，subtitle_text 留空字串、subtitle_bbox 回 [0,0,0,0]。
文字照抄，使用臺灣繁體中文。"""

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def key_for(path: Path):
    m = re.search(r"(\d+)", path.stem)
    return str(int(m.group(1))) if m else path.stem


def natural(name: str) -> tuple:
    """Sort so slide 2 precedes slide 10."""
    return tuple(int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name))


def find_images(image_dir: Path, pattern):
    """Collect slide images, tolerating any common extension and naming scheme.

    The Slides image deck writes files such as `s1_cover.webp`, while hand-saved exports
    are often `slide_01.png`. With no --pattern, accept every image in the directory.
    """
    if pattern:
        return sorted(image_dir.glob(pattern), key=lambda p: natural(p.name))
    return sorted((p for p in image_dir.iterdir()
                   if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES),
                  key=lambda p: natural(p.name))


def crop_extent(coarse_entry: dict, x_min: float, y_min: float) -> tuple:
    """Decide how much of the slide to crop for the upscale pass.

    A fixed left-hand crop silently truncates wide centred headings: the model never
    sees the right-hand characters and returns a cut-off title. So the crop always
    covers the full width of the coarse boxes from the first pass, with a margin.
    """
    xf, yf = x_min, y_min
    for field in ("title_bbox", "subtitle_bbox"):
        box = coarse_entry.get(field) or []
        if box and len(box) == 4 and sum(box) > 0:
            xf = max(xf, float(box[2]) + 0.04)
            yf = max(yf, float(box[3]) + 0.05)
    return min(xf, 1.0), min(yf, 1.0)


def recover_full_text(refined: str, coarse: str) -> str:
    """Restore a title the crop may have cut off.

    If the refined reading is a truncated prefix of the coarse reading, the crop hid the
    tail. Prefer the longer, complete coarse text rather than shipping a clipped heading.
    """
    r = (refined or "").strip()
    c = (coarse or "").strip()
    if not c or not r:
        return r or c
    r_flat, c_flat = r.replace("\n", ""), c.replace("\n", "")
    if r_flat != c_flat and c_flat.startswith(r_flat):
        return c
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image_dir", type=Path)
    ap.add_argument("coarse_json", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--model", default="gemini-3.1-pro-preview")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--x-max", type=float, default=0.78,
                    help="minimum crop width; extended automatically to cover wide titles")
    ap.add_argument("--y-max", type=float, default=0.60,
                    help="minimum crop height; extended automatically to cover the subtitle")
    ap.add_argument("--pattern", default=None,
                    help="glob for slide images; default: every image file in the directory")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    client = OpenAI()
    coarse = json.loads(args.coarse_json.read_text(encoding="utf-8"))
    images = find_images(args.image_dir, args.pattern)
    if not images:
        raise SystemExit(f"no images found in {args.image_dir}")
    if args.output.exists() and not args.overwrite:
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        if len(existing) == len(images):
            print("cached", args.output)
            return
    result = {}

    def refine(path: Path):
        entry = coarse.get(path.name, {})
        xf, yf = crop_extent(entry, args.x_max, args.y_max)
        im = Image.open(path).convert("RGB")
        w, h = im.size
        crop = im.crop((0, 0, int(w * xf), int(h * yf)))
        scale = 1700 / crop.width
        crop = crop.resize((int(crop.width * scale), int(crop.height * scale)),
                           Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        crop.save(buf, format="PNG")
        url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        try:
            response = client.chat.completions.create(
                model=args.model,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": [
                        {"type": "text", "text": "請定位主標題與副標題的文字框。"},
                        {"type": "image_url", "image_url": {"url": url, "detail": "high"}}
                    ]}
                ],
                response_format={"type": "json_schema",
                                 "json_schema": {"name": "tight_bbox", "strict": True, "schema": SCHEMA}},
                max_tokens=2048
            )
            data = json.loads(response.choices[0].message.content)
            # map crop-normalized coords back to full-slide normalized coords
            for field in ("title_bbox", "subtitle_bbox"):
                box = data[field]
                if box and sum(box) > 0:
                    data[field] = [round(box[0] * xf, 4), round(box[1] * yf, 4),
                                   round(box[2] * xf, 4), round(box[3] * yf, 4)]
            # restore any text the crop cut off
            data["title_text"] = recover_full_text(data.get("title_text"),
                                                   entry.get("title_text"))
            data["subtitle_text"] = recover_full_text(data.get("subtitle_text"),
                                                      entry.get("subtitle_text"))
            data["crop"] = [round(xf, 3), round(yf, 3)]
            data["coarse"] = entry
            return path.name, data
        except Exception as exc:
            return path.name, {"error": repr(exc)}

    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for name, data in pool.map(refine, images):
            result[name] = data
            print(name, json.dumps(data, ensure_ascii=False)[:180], flush=True)

    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("written", args.output)


if __name__ == "__main__":
    main()