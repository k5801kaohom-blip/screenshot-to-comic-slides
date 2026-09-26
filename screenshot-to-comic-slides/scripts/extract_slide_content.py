#!/usr/bin/env python3
"""Extract ordered slide content from screenshots with structured multimodal LLM output."""

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
        "slide_number": {"type": "integer"},
        "source_path": {"type": "string"},
        "title_traditional": {"type": "string"},
        "subtitle_traditional": {"type": "string"},
        "body_traditional": {"type": "array", "items": {"type": "string"}},
        "labels_traditional": {"type": "array", "items": {"type": "string"}},
        "layout_type": {"type": "string"},
        "visual_summary": {"type": "string"},
        "visual_objects": {"type": "array", "items": {"type": "string"}},
        "diagram_relationships": {"type": "array", "items": {"type": "string"}},
        "comic_redraw_brief": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "uncertain_text": {"type": "array", "items": {"type": "string"}}
    },
    "required": [
        "slide_number", "source_path", "title_traditional", "subtitle_traditional",
        "body_traditional", "labels_traditional", "layout_type", "visual_summary",
        "visual_objects", "diagram_relationships", "comic_redraw_brief",
        "confidence", "uncertain_text"
    ],
    "additionalProperties": False
}

SYSTEM = """你是專業簡報 OCR、資訊架構與臺灣繁體中文在地化專家。
忠實辨識單張簡報截圖。所有輸出使用臺灣繁體中文；保留品牌、英文縮寫、型號、日期與數字。
用詞採臺灣慣用語，例如基地台、演算法、介面、即時、公尺。不要猜測看不清的文字，改列入 uncertain_text。
comic_redraw_brief 必須說明如何保留原頁物件、構圖、角色、照片圖說與流程關係，重製為成熟的企業漫畫／向量資訊圖；不得只做文字條列。"""


def load_manifest(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    result = []
    for i, item in enumerate(data, 1):
        if isinstance(item, str):
            result.append({"slide_number": i, "source_path": item})
        else:
            result.append({"slide_number": int(item.get("slide_number", i)), "source_path": item["source_path"]})
    return result


def pick_model(client, requested):
    available = {m.id for m in client.models.list().data}
    if requested:
        if requested not in available:
            raise SystemExit(f"Requested model is unavailable: {requested}")
        return requested
    for candidate in ("gemini-3-flash-preview", "gpt-5-mini", "gpt-5"):
        if candidate in available:
            return candidate
    raise SystemExit("No preferred vision model available; pass --model from the live catalog")


def as_data_url(path: Path):
    mime = mimetypes.guess_type(path.name)[0] or "image/webp"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", type=Path)
    ap.add_argument("output_dir", type=Path)
    ap.add_argument("--model")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    client = OpenAI()
    model = pick_model(client, args.model)
    items = load_manifest(args.manifest)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    def extract(item):
        number = item["slide_number"]
        source = Path(item["source_path"])
        out = args.output_dir / f"slide_{number:03d}.json"
        if out.exists() and not args.overwrite:
            return {"slide_number": number, "status": "cached", "path": str(out)}
        if not source.exists():
            return {"slide_number": number, "status": "error", "error": f"Missing {source}"}
        prompt = (
            f"這是第 {number} 張簡報截圖。辨識所有與重製相關的標題、重點、表格、圖說、角色、設備與流程關係。"
            "忽略舊有公司 LOGO；後續將套用使用者提供的新品牌。"
        )
        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": as_data_url(source), "detail": "high"}}
                ]}
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "slide_extract", "strict": True, "schema": SCHEMA}
            }
        }
        if model.startswith("gpt-"):
            kwargs["max_completion_tokens"] = 8192
        else:
            kwargs["max_tokens"] = 8192
        last_error = None
        for attempt in range(3):
            try:
                response = client.chat.completions.create(**kwargs)
                data = json.loads(response.choices[0].message.content)
                data["slide_number"] = number
                data["source_path"] = str(source)
                out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                return {"slide_number": number, "status": "ok", "confidence": data["confidence"], "path": str(out)}
            except Exception as exc:
                last_error = repr(exc)
                time.sleep(2 * (attempt + 1))
        return {"slide_number": number, "status": "error", "error": last_error}

    results = []
    with cf.ThreadPoolExecutor(max_workers=max(1, min(args.workers, 10))) as pool:
        futures = [pool.submit(extract, item) for item in items]
        for future in cf.as_completed(futures):
            result = future.result()
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
    results.sort(key=lambda x: x["slide_number"])
    summary = args.output_dir / "summary.json"
    summary.write_text(json.dumps({"model": model, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
