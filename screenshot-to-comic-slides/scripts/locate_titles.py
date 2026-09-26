#!/usr/bin/env python3
"""Locate the main title bounding box on each generated slide image."""

import argparse
import base64
import concurrent.futures as cf
import json
import mimetypes
import time
from pathlib import Path
from openai import OpenAI

SCHEMA = {
    "type": "object",
    "properties": {
        "title_text": {"type": "string"},
        "title_bbox": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Normalized [x0, y0, x1, y1] with values 0-1 relative to image size"
        },
        "subtitle_text": {"type": "string"},
        "subtitle_bbox": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Normalized [x0, y0, x1, y1] of the subtitle line under the title, or [0,0,0,0] if none"
        },
        "notes": {"type": "string"}
    },
    "required": ["title_text", "title_bbox", "subtitle_text", "subtitle_bbox", "notes"],
    "additionalProperties": False
}

SYSTEM = """你是簡報版面分析專家。給你一張 16:9 簡報投影片，請找出「最大的主標題文字」與其正下方的「副標題／一行說明」。
回報正規化座標 [x0, y0, x1, y1]，數值介於 0 到 1 之間，原點在左上角。
座標必須緊貼文字外框（包含筆畫邊緣，可略微外擴 1%），不要包含左側圖示或右側插圖。
若沒有副標題，subtitle_text 回空字串、subtitle_bbox 回 [0,0,0,0]。
標題文字請照抄，使用臺灣繁體中文。"""


def as_data_url(path: Path):
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image_dir", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--model", default="gemini-3-flash-preview")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--pattern", default="slide_*.png")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    client = OpenAI()
    images = sorted(args.image_dir.glob(args.pattern))
    if not images:
        raise SystemExit("no images")
    if args.output.exists() and not args.overwrite:
        data = json.loads(args.output.read_text(encoding="utf-8"))
        if len(data) == len(images):
            print("cached", args.output)
            return
    data = {}

    def locate(path: Path):
        key = path.name
        try:
            response = client.chat.completions.create(
                model=args.model,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": [
                        {"type": "text", "text": "請定位這張投影片的主標題與副標題。"},
                        {"type": "image_url", "image_url": {"url": as_data_url(path), "detail": "high"}}
                    ]}
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "title_bbox", "strict": True, "schema": SCHEMA}
                },
                max_tokens=2048
            )
            payload = json.loads(response.choices[0].message.content)
            payload["image"] = str(path)
            return key, payload
        except Exception as exc:
            return key, {"error": repr(exc), "image": str(path)}

    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for key, payload in pool.map(locate, images):
            data[key] = payload
            print(key, json.dumps(payload, ensure_ascii=False)[:160], flush=True)

    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("written", args.output)


if __name__ == "__main__":
    main()
