#!/usr/bin/env python3
"""Keep slide illustrations but expose the main title and subtitle as editable text.

Workflow:
1. Take the tight model-provided boxes (produced from an upscaled crop) as the anchor.
2. Refine inside that anchor only: polarity-aware ink detection (dark text on light
   backgrounds, light text on dark backgrounds), row banding, multi-line grouping.
3. Erase the baked-in text by interpolating the surrounding background per column.
4. Rebuild a PPTX where each slide is the cleaned illustration plus editable text boxes.

Nothing is skipped: when pixel refinement is inconclusive the model box is used as-is.
"""

import argparse
import json
import math
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt

SLIDE_W_IN = 40.0 / 3.0
SLIDE_H_IN = 7.5
DEFAULT_PX_W = 2560
DEFAULT_PX_H = 1440
FONT_NAME = "Microsoft JhengHei"

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def set_run_font(run, size_pt, bold, color):
    """Apply run formatting without duplicating elements.

    In DrawingML each of `a:latin`, `a:ea` and `a:cs` may appear at most once inside
    `a:rPr`, and they must keep that order. Setting `font.name` already creates `a:latin`,
    so the East Asian and complex-script faces are inserted in order only when missing.
    Duplicated elements make PowerPoint report the file as corrupt even though
    LibreOffice still renders it.
    """
    run.font.size = Pt(round(size_pt, 1))
    run.font.bold = bold
    run.font.name = FONT_NAME
    run.font.color.rgb = RGBColor(*color)

    rPr = run._r.get_or_add_rPr()

    def ensure(tag, after):
        el = rPr.find(f"{{{A_NS}}}{tag}")
        if el is not None:
            return el
        el = rPr.makeelement(f"{{{A_NS}}}{tag}", {"typeface": FONT_NAME})
        anchor = rPr.find(f"{{{A_NS}}}{after}") if after else None
        if anchor is not None:
            anchor.addnext(el)
        else:
            rPr.append(el)
        return el

    ensure("latin", None)
    ensure("ea", "latin")
    ensure("cs", "ea")

DARK_INK_THR = 168
LIGHT_INK_THR = 175
DARK_BG_LEVEL = 120
LOGO_ZONE = (0.0, 0.0, 0.19, 0.15)


def px_to_emu(px, total_px, total_in):
    return Emu(int(round(px / total_px * total_in * 914400)))


def key_for(path: Path):
    m = re.search(r"(\d+)", path.stem)
    return str(int(m.group(1))) if m else path.stem


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def natural(name: str) -> tuple:
    """Sort so slide 2 precedes slide 10."""
    return tuple(int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name))


def find_images(image_dir: Path, pattern: str | None) -> list[Path]:
    """Collect slide images, tolerating any common extension and naming scheme.

    The Slides image deck writes files such as `s1_cover.webp`, while hand-saved exports
    are often `slide_01.png`. With no --pattern, accept every image in the directory.
    """
    if pattern:
        return sorted(image_dir.glob(pattern), key=lambda p: natural(p.name))
    return sorted((p for p in image_dir.iterdir()
                   if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES),
                  key=lambda p: natural(p.name))


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def group_rows(rows, gap_tol):
    bands = []
    start = prev = None
    for r in rows:
        if start is None:
            start = prev = r
            continue
        if r - prev > gap_tol:
            bands.append((int(start), int(prev)))
            start = r
        prev = r
    if start is not None:
        bands.append((int(start), int(prev)))
    return bands


def build_bands(ink, rx0, ry0, rx1, bbox_h, w, expected_lines, min_h_ratio):
    min_count = max(2, int(0.004 * (rx1 - rx0)))
    gap_tol = 3
    raw = group_rows(np.where(ink.sum(axis=1) >= min_count)[0], gap_tol)
    bands = []
    for a, b in raw:
        hh = b - a + 1
        if hh < min_h_ratio * bbox_h or hh > 1.5 * bbox_h:
            continue
        seg = ink[a:b + 1]
        cols = np.where(seg.sum(axis=0) > 0)[0]
        if len(cols) == 0:
            continue
        bx, ex = int(cols[0]) + rx0, int(cols[-1]) + rx0
        if ex - bx < 0.06 * w:
            continue
        bands.append({"box": (bx, a + ry0, ex, b + ry0), "h": int(hh)})
    if not bands:
        return []
    bands.sort(key=lambda b: b["box"][1])
    if len(bands) > expected_lines:
        keep = sorted(bands, key=lambda b: b["h"], reverse=True)[:expected_lines]
        keep.sort(key=lambda b: b["box"][1])
        bands = keep
    return bands


def analyse_block(gray, bbox, w, h, is_title, text):
    """Refine a model box into a tight text box. Returns dict or None."""
    bx0, by0, bx1, by1 = (bbox[0] * w, bbox[1] * h, bbox[2] * w, bbox[3] * h)
    if bx1 <= bx0 or by1 <= by0:
        return None
    pad_x = 0.008 * w if is_title else 0.006 * w
    pad_y = 0.012 * h if is_title else 0.010 * h
    rx0, rx1 = int(clamp(bx0 - pad_x, 0, w)), int(clamp(bx1 + pad_x, 0, w))
    ry0, ry1 = int(clamp(by0 - pad_y, 0, h)), int(clamp(by1 + pad_y, 0, h))
    if rx1 - rx0 < 16 or ry1 - ry0 < 16:
        return None

    region = gray[ry0:ry1, rx0:rx1]
    lx0, ly0 = int(LOGO_ZONE[0] * w), int(LOGO_ZONE[1] * h)
    lx1, ly1 = int(LOGO_ZONE[2] * w), int(LOGO_ZONE[3] * h)
    mx0, my0 = max(0, lx0 - rx0), max(0, ly0 - ry0)
    mx1, my1 = min(rx1 - rx0, lx1 - rx0), min(ry1 - ry0, ly1 - ry0)

    bbox_h = by1 - by0
    expected_lines = max(1, len([p for p in text.split("\n") if p.strip()])) if text else 1
    min_h_ratio = 0.10 if expected_lines > 1 else 0.24

    inner = region[max(0, my0):max(1, my1), max(0, mx0):max(1, mx1)]
    probe = inner if inner.size > 200 else region
    light_text = float(np.median(probe)) < DARK_BG_LEVEL
    ink = (region > LIGHT_INK_THR) if light_text else (region < DARK_INK_THR)
    ink = ink.copy()
    if mx1 > mx0 and my1 > my0:
        ink[my0:my1, mx0:mx1] = False
    if not ink.any():
        return None
    bands = build_bands(ink, rx0, ry0, rx1, bbox_h, w, expected_lines, min_h_ratio)
    if not bands:
        return None

    x0 = min(b["box"][0] for b in bands)
    y0 = min(b["box"][1] for b in bands)
    x1 = max(b["box"][2] for b in bands)
    y1 = max(b["box"][3] for b in bands)
    heights = [b["h"] for b in bands]
    lines = [b["box"] for b in bands]
    return {"box": (x0, y0, x1, y1), "lines": lines, "heights": heights,
            "light_text": light_text, "refined": True}


def fallback_block(bbox, w, h):
    x0 = int(clamp(bbox[0] * w, 0, w))
    y0 = int(clamp(bbox[1] * h, 0, h))
    x1 = int(clamp(bbox[2] * w, 0, w))
    y1 = int(clamp(bbox[3] * h, 0, h))
    if x1 <= x0 or y1 <= y0:
        return None
    return {"box": (x0, y0, x1, y1), "lines": [(x0, y0, x1, y1)], "heights": [y1 - y0 + 1],
            "light_text": None, "refined": False}


def dominant_color(rgb, box, light_text=None):
    """Pick the text colour from the actual stroke pixels, verified against the background."""
    x0, y0, x1, y1 = box
    region = rgb[y0:y1 + 1, x0:x1 + 1].reshape(-1, 3)
    gray = region.mean(axis=1)
    light = bool(np.median(gray) < DARK_BG_LEVEL) if light_text is None else bool(light_text)
    if light:
        ink_sel = gray > LIGHT_INK_THR
    else:
        ink_sel = gray < DARK_INK_THR
    if ink_sel.sum() < 20:
        cut = np.percentile(gray, 90 if light else 10)
        ink_sel = gray > cut if light else gray < cut
    ink = region[ink_sel]
    bg = region[~ink_sel]
    if len(ink) == 0:
        return (255, 255, 255) if light else (11, 33, 54)
    ink_lum = float(np.median(ink.mean(axis=1)))
    bg_lum = float(np.median(bg.mean(axis=1))) if len(bg) else (0.0 if light else 255.0)
    color = tuple(int(v) for v in np.median(ink, axis=0))
    if light and ink_lum >= bg_lum - 10:
        if ink_lum > 200:
            color = (255, 255, 255)
    elif (not light) and ink_lum <= bg_lum + 10:
        if ink_lum > 140:
            color = (11, 33, 54)
    return color


def erase_text(rgb, box, light_text=None, dilate=5, pad=28, delta=22):
    """Erase baked-in text by comparing each pixel with an interpolated background.

    The background is estimated per column from the strips above and below the text
    box, so bright text on dark artwork and low-contrast text are handled alike.
    """
    h, w = rgb.shape[:2]
    x0, y0, x1, y1 = box
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w - 1, x1), min(h - 1, y1)
    if x1 <= x0 or y1 <= y0:
        return rgb
    ry0 = max(0, y0 - pad)
    ry1 = min(h, y1 + 1 + pad)
    region = rgb[ry0:ry1, x0:x1 + 1].astype(np.float32)
    H, W = region.shape[:2]
    if H < 5 or W < 2:
        return rgb
    strip = max(2, min(pad // 2, max(2, (H - (y1 - y0 + 1)) // 2)))
    top_ref = region[:strip].mean(axis=0)
    bot_ref = region[H - strip:].mean(axis=0)
    ramp = np.linspace(0.0, 1.0, H)[:, None, None]
    bg = top_ref[None, :, :] * (1.0 - ramp) + bot_ref[None, :, :] * ramp
    diff = np.abs(region - bg).max(axis=2)
    mask = diff > delta
    keep = np.zeros((H, W), dtype=bool)
    ky0 = max(0, y0 - ry0 - 4)
    ky1 = min(H, (y1 - ry0) + 5)
    keep[ky0:ky1, :] = True
    mask &= keep
    if not mask.any():
        return rgb
    m = (mask.astype(np.uint8) * 255)
    if dilate > 0:
        m = np.asarray(Image.fromarray(m).filter(ImageFilter.MaxFilter(2 * dilate + 1)))
    m = (m > 127) & keep
    out = region.copy()
    out[m] = bg[m]
    if m.any():
        soft = np.asarray(Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
                          .filter(ImageFilter.GaussianBlur(1.2))).astype(np.float32)
        blend = np.asarray(Image.fromarray((m.astype(np.uint8) * 255))
                           .filter(ImageFilter.GaussianBlur(1.6))).astype(np.float32) / 255.0
        blend = blend[:, :, None]
        out = out * (1.0 - blend) + soft * blend
    rgb[ry0:ry1, x0:x1 + 1] = np.clip(out, 0, 255).astype(np.uint8)
    return rgb


def estimate_width(text, size_pt):
    return sum((0.56 if ord(ch) < 0x2E80 else 1.0) * size_pt for ch in text)


def text_units(text):
    return max(1.0, sum((0.56 if ord(ch) < 0x2E80 else 1.0) for ch in text))


def split_text(text, line_boxes):
    text = text.strip()
    if "\n" in text:
        parts = [p.strip() for p in text.split("\n") if p.strip()]
        if len(parts) == len(line_boxes):
            return parts
        if len(parts) == 1:
            return parts
        text = "".join(parts)
    if len(line_boxes) < 2 or len(text) < len(line_boxes):
        return [text]
    widths = [max(1, b[2] - b[0]) for b in line_boxes]
    total = sum(widths)
    out, cursor = [], 0
    for i, wd in enumerate(widths):
        if i == len(widths) - 1:
            out.append(text[cursor:])
        else:
            take = max(1, int(round(len(text) * wd / total)))
            out.append(text[cursor:cursor + take])
            cursor += take
    return [s for s in out if s]


def split_like_original(text, orig_lines):
    """Distribute replacement text over the original line count, keeping tail lengths."""
    text = text.strip()
    n = len(orig_lines)
    if n < 2 or "\n" in text:
        return [p for p in text.split("\n") if p.strip()] or [text]
    if len(text) <= n:
        return [text]
    tail = [len(l) for l in orig_lines[1:]]
    if len(text) - sum(tail) >= 1:
        parts = []
        cursor = len(text)
        for length in reversed(tail):
            parts.insert(0, text[cursor - length:cursor])
            cursor -= length
        parts.insert(0, text[:cursor])
        return [p for p in parts if p.strip()]
    widths = [max(1, len(l)) for l in orig_lines]
    total = sum(widths)
    parts, cursor = [], 0
    for i, wd in enumerate(widths):
        if i == len(widths) - 1:
            parts.append(text[cursor:])
        else:
            take = max(1, int(round(len(text) * wd / total)))
            take = min(take, max(1, len(text) - cursor - (len(widths) - i - 1)))
            parts.append(text[cursor:cursor + take])
            cursor += take
    return [p for p in parts if p.strip()]


def add_textbox(slide, box, lines_text, color, px_w, px_h, size_pt, bold, wrap, pad_x=10, pad_y=8):
    x0, y0, x1, y1 = box
    left = px_to_emu(x0 - pad_x, px_w, SLIDE_W_IN)
    top = px_to_emu(max(0, y0 - pad_y), px_h, SLIDE_H_IN)
    width = px_to_emu((x1 - x0) + 2 * pad_x + int(0.02 * px_w), px_w, SLIDE_W_IN)
    height = px_to_emu((y1 - y0) + 2 * pad_y, px_h, SLIDE_H_IN)
    shape = slide.shapes.add_textbox(left, top, width, height)
    tf = shape.text_frame
    tf.word_wrap = False
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.TOP
    for i, line in enumerate(lines_text):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.line_spacing = 1.0
        run = p.add_run()
        run.text = line
        set_run_font(run, size_pt, bold, color)
    return shape


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image-dir", type=Path, required=True)
    ap.add_argument("--title-json", type=Path, required=True)
    ap.add_argument("--overrides", type=Path)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--pptx", type=Path, required=True)
    ap.add_argument("--pattern", default=None,
                    help="glob for slide images; default: every image file in the directory")
    ap.add_argument("--report", type=Path)
    ap.add_argument("--image-format", choices=("png", "jpeg"), default="png")
    ap.add_argument("--jpeg-quality", type=int, default=90)
    args = ap.parse_args()

    hints = json.loads(args.title_json.read_text(encoding="utf-8"))
    overrides = json.loads(args.overrides.read_text(encoding="utf-8")) if args.overrides else {}
    cleaned_dir = args.out_dir / "cleaned"
    cleaned_dir.mkdir(parents=True, exist_ok=True)

    prs = Presentation()
    prs.slide_width = px_to_emu(DEFAULT_PX_W, DEFAULT_PX_W, SLIDE_W_IN)
    prs.slide_height = px_to_emu(DEFAULT_PX_H, DEFAULT_PX_H, SLIDE_H_IN)
    blank = prs.slide_layouts[6]

    report = []
    for path in find_images(args.image_dir, args.pattern):
        key = key_for(path)
        hint = hints.get(path.name, {})
        override = overrides.get(key, {})
        rgb = np.asarray(Image.open(path).convert("RGB")).copy()
        h, w = rgb.shape[:2]
        gray = rgb.mean(axis=2)
        px_per_pt = h / (SLIDE_H_IN * 72)
        entry = {"image": path.name, "key": key}

        if override.get("skip") or not hint.get("title_bbox"):
            entry["skipped"] = True
            report.append(entry)
            slide = prs.slides.add_slide(blank)
            slide.shapes.add_picture(str(path), 0, 0, width=prs.slide_width, height=prs.slide_height)
            continue

        has_override = "title" in override
        raw_title = str(override.get("title", hint.get("title_text", ""))).strip()
        title_text = raw_title.replace("\n", " ")
        sub_text = str(override.get("subtitle", hint.get("subtitle_text", ""))).strip()

        title = analyse_block(gray, hint["title_bbox"], w, h, True, raw_title)
        if title is None:
            title = fallback_block(hint["title_bbox"], w, h)
        if title is None:
            entry["skipped"] = True
            report.append(entry)
            slide = prs.slides.add_slide(blank)
            slide.shapes.add_picture(str(path), 0, 0, width=prs.slide_width, height=prs.slide_height)
            continue

        light = title["light_text"]
        if light is None:
            light = float(np.median(gray[title["box"][1]:title["box"][3] + 1,
                                        title["box"][0]:title["box"][2] + 1])) < DARK_BG_LEVEL
        title_color = dominant_color(rgb, title["box"], light)
        raw_lines = [p.strip() for p in raw_title.split("\n") if p.strip()]
        erase_boxes = [title["box"]]
        hb = hint.get("title_bbox") or []
        if hb and (len(raw_lines) > 1 or has_override):
            model_box = (int(hb[0] * w), int(hb[1] * h), int(hb[2] * w), int(hb[3] * h))
            if model_box[3] - model_box[1] > (title["box"][3] - title["box"][1]) * 1.15:
                erase_boxes.append((min(model_box[0], title["box"][0]),
                                    max(0, model_box[1] - 2),
                                    max(model_box[2], title["box"][2]),
                                    min(h - 1, model_box[3] + 2)))
        if len(raw_lines) > 1 and hb:
            model_box = (int(hb[0] * w), int(hb[1] * h), int(hb[2] * w), int(hb[3] * h))
            lh = max(8.0, (hb[3] - hb[1]) * h / len(raw_lines))
            est_pt = lh / 0.96 / px_per_pt
            units = [text_units(t) for t in raw_lines]
            avail_pt = (max(model_box[2], title["box"][2]) - min(model_box[0], title["box"][0]) + 2 * 10) / px_per_pt
            need_pt = max(units) * est_pt
            if need_pt > avail_pt and need_pt > 0:
                est_pt *= max(0.62, avail_pt / need_pt)
            entry["est_size_pt"] = round(est_pt, 1)
        for eb in erase_boxes:
            rgb = erase_text(rgb, eb, light)

        sub = None
        if sub_text and hint.get("subtitle_bbox") and sum(hint["subtitle_bbox"]) > 0:
            sub = analyse_block(gray, hint["subtitle_bbox"], w, h, False, sub_text)
            if sub is None:
                sub = fallback_block(hint["subtitle_bbox"], w, h)
            if sub and (sub["box"][1] - title["box"][3]) > 0.17 * h:
                sub = None
            if sub and sub["box"][3] > title["box"][3] + 0.30 * h:
                sub = None
        sub_color = (11, 33, 54)
        if sub:
            sub_light = sub["light_text"]
            if sub_light is None:
                sub_light = light
            sub_color = dominant_color(rgb, sub["box"], sub_light)
            rgb = erase_text(rgb, sub["box"], sub_light, dilate=4, pad=22)

        if args.image_format == "jpeg":
            cleaned_path = cleaned_dir / f"{path.stem}_clean.jpg"
            Image.fromarray(rgb).save(cleaned_path, format="JPEG", quality=args.jpeg_quality,
                                      subsampling=0, optimize=True)
        else:
            cleaned_path = cleaned_dir / f"{path.stem}_clean.png"
            Image.fromarray(rgb).save(cleaned_path)
        slide = prs.slides.add_slide(blank)
        slide.shapes.add_picture(str(cleaned_path), 0, 0, width=prs.slide_width, height=prs.slide_height)

        hb = hint["title_bbox"]
        model_box = (int(hb[0] * w), int(hb[1] * h), int(hb[2] * w), int(hb[3] * h))
        model_h = max(10.0, (hb[3] - hb[1]) * h)
        model_w = max(10.0, (hb[2] - hb[0]) * w)
        if len(raw_lines) > 1:
            lh = max(8.0, model_h / len(raw_lines))
            size_pt = lh / 0.96 / px_per_pt
            texts = raw_lines
            out_box = model_box
        elif has_override:
            orig_lines = [p.strip() for p in hint.get("title_text", "").split("\n") if p.strip()]
            orig_lines = orig_lines or [hint.get("title_text", "")]
            texts = split_like_original(title_text, orig_lines)
            if len(texts) > 1:
                lh = max(8.0, model_h / len(texts))
                size_pt = lh / 0.96 / px_per_pt
            else:
                size_pt = model_h / 0.98 / px_per_pt
            out_box = model_box
        else:
            size_pt = float(np.median(title["heights"])) / 0.86 / px_per_pt
            texts = split_text(title_text, title["lines"])
            out_box = title["box"]
        avail = (max(model_w, out_box[2] - out_box[0]) + 2 * 10 + int(0.05 * w)) / px_per_pt
        widest = max(estimate_width(t, size_pt) for t in texts)
        if widest > avail and widest > 0:
            size_pt *= max(0.5, avail / widest)
        add_textbox(slide, out_box, texts, title_color, w, h, size_pt, True, len(texts) > 1)
        entry["title"] = {"text": title_text, "lines": texts, "box": title["box"],
                          "heights": title["heights"], "size_pt": round(size_pt, 1),
                          "color": title_color, "refined": title["refined"], "light": bool(light)}

        if sub and sub_text:
            sub_size = float(np.median(sub["heights"])) / 0.86 / px_per_pt
            sub_texts = split_text(sub_text, sub["lines"])
            sub_avail = (sub["box"][2] - sub["box"][0] + 2 * 10 + int(0.03 * w)) / px_per_pt
            sub_widest = max(estimate_width(t, sub_size) for t in sub_texts)
            if sub_widest > sub_avail and sub_widest > 0:
                sub_size *= max(0.62, sub_avail / sub_widest)
            add_textbox(slide, sub["box"], sub_texts, sub_color, w, h, sub_size, False,
                        len(sub_texts) > 1)
            entry["subtitle"] = {"text": sub_text, "lines": sub_texts, "box": sub["box"],
                                 "heights": sub["heights"], "size_pt": round(sub_size, 1),
                                 "color": sub_color, "refined": sub["refined"]}
        report.append(entry)

    args.pptx.parent.mkdir(parents=True, exist_ok=True)
    prs.save(args.pptx)
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"slides": len(report), "pptx": str(args.pptx)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
