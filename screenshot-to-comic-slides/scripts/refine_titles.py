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
沒有副標題時，subtitle_text 留空字串、subtitle_bbox 回 [0,0,0,0]。
文字照抄，使用臺灣繁體中文。"""


def key_for(path: Path):
    m = re.search(r"(\d+)", path.stem)
    return str(int(m.group(1))) if m else path.stem


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image_dir", type=Path)
    ap.add_argument("coarse_json", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--model", default="gemini-3.1-pro-preview")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--x-max", type=float, default=0.72)
    ap.add_argument("--y-max", type=float, default=0.58)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    client = OpenAI()
    coarse = json.loads(args.coarse_json.read_text(encoding="utf-8"))
    images = sorted(args.image_dir.glob("slide_*.png"))
    if args.output.exists() and not args.overwrite:
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        if len(existing) == len(images):
            print("cached", args.output)
            return
    result = {}

    def refine(path: Path):
        im = Image.open(path).convert("RGB")
        w, h = im.size
        x1 = int(w * args.x_max)
        y1 = int(h * args.y_max)
        crop = im.crop((0, 0, x1, y1))
        scale = 1700 / crop.width
        crop = crop.resize((int(crop.width * scale), int(crop.height * scale)), Image.Resampling.LANCZOS)
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
                    data[field] = [round(box[0] * args.x_max, 4), round(box[1] * args.y_max, 4),
                                   round(box[2] * args.x_max, 4), round(box[3] * args.y_max, 4)]
            data["coarse"] = coarse.get(path.name, {})
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
