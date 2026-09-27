#!/usr/bin/env python3
"""Strict OOXML checks for a generated PPTX before delivery.

PowerPoint rejects files that LibreOffice still renders happily, so a visual check is not
enough. The most common self-inflicted failure is a duplicated child element inside
`a:rPr`: setting `font.name` in python-pptx already creates `a:latin`, and appending another
`a:latin` for the East Asian face produces a file PowerPoint refuses to open.

Run this before handing any PPTX to a user:

    python validate_pptx.py deck.pptx

Exit code 0 means every check passed; 1 means at least one blocking problem was found.
"""

import argparse
import io
import posixpath
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

# Order of children inside a:rPr / a:defRPr as required by DrawingML.
RPR_ORDER = [
    "ln", "fill", "effectLst", "highlight", "uLnTx", "uLn",
    "uFillTx", "uFill", "latin", "ea", "cs", "sym", "hlinkClick", "hlinkMouseOver", "rtl", "extLst",
]

# Elements allowed at most once inside the parent element.
SINGLETON_CHILDREN = {
    "rPr": {"ln", "solidFill", "noFill", "gradFill", "blipFill", "pattFill", "grpFill",
            "effectLst", "highlight", "uLnTx", "uLn", "uFillTx", "uFill",
            "latin", "ea", "cs", "sym", "hlinkClick", "hlinkMouseOver", "rtl", "extLst"},
    "defRPr": {"ln", "solidFill", "noFill", "gradFill", "blipFill", "pattFill", "grpFill",
               "effectLst", "highlight", "uLnTx", "uLn", "uFillTx", "uFill",
               "latin", "ea", "cs", "sym", "hlinkClick", "hlinkMouseOver", "rtl", "extLst"},
    "bodyPr": {"prstTxWarp", "noAutofit", "normAutofit", "spAutoFit", "scene3d", "sp3d", "flatTx", "extLst"},
    "spPr": {"xfrm", "custGeom", "prstGeom", "noFill", "solidFill", "gradFill", "blipFill",
             "pattFill", "grpFill", "ln", "effectLst", "effectDag", "scene3d", "sp3d", "extLst"},
}

SP_ORDER = ["nvSpPr", "spPr", "style", "txBody"]


def load(path):
    z = zipfile.ZipFile(path)
    return z, set(z.namelist())


def check_zip(z):
    problems = []
    bad = z.testzip()
    if bad:
        problems.append(f"corrupt zip member: {bad}")
    return problems


def check_xml_wellformed(z):
    problems = []
    for n in z.namelist():
        if n.endswith((".xml", ".rels")):
            try:
                ET.fromstring(z.read(n))
            except ET.ParseError as exc:
                problems.append(f"malformed XML in {n}: {exc}")
    return problems


def check_relationships(z, names):
    problems = []
    for n in z.namelist():
        if not n.endswith(".rels"):
            continue
        base = "" if n == "_rels/.rels" else n.rsplit("/_rels/", 1)[0]
        for m in re.finditer(r'Target="([^"]+)"', z.read(n).decode("utf-8")):
            t = m.group(1)
            if t.startswith(("http", "mailto")):
                continue
            full = posixpath.normpath(posixpath.join(base, t)) if base else t.lstrip("/")
            if full not in names:
                problems.append(f"{n}: unresolved relationship target {t}")
    return problems


def check_content_types(z, names):
    problems = []
    ct = z.read("[Content_Types].xml").decode("utf-8")
    defaults = set(re.findall(r'<Default Extension="([^"]+)"', ct))
    overrides = set(re.findall(r'<Override PartName="([^"]+)"', ct))
    for n in names:
        if n == "[Content_Types].xml" or n.endswith("/"):
            continue
        ext = n.rsplit(".", 1)[-1].lower()
        if f"/{n}" in overrides or ext in defaults:
            continue
        problems.append(f"no content type declared for {n}")
    return problems


def check_required_parts(names):
    required = [
        "[Content_Types].xml", "_rels/.rels", "ppt/presentation.xml",
        "ppt/_rels/presentation.xml.rels", "docProps/core.xml", "docProps/app.xml",
    ]
    problems = [f"missing required part {r}" for r in required if r not in names]
    if not any(n.startswith("ppt/slideMasters/") for n in names):
        problems.append("no slide master found")
    if not any(n.startswith("ppt/theme/") for n in names):
        problems.append("no theme found")
    return problems


def check_duplicate_children(z):
    """Catch duplicated singleton children, the usual cause of 'file cannot be opened'."""
    problems = []
    for n in z.namelist():
        if not re.match(r"ppt/(slides|slideLayouts|slideMasters|notesSlides)/.*\.xml$", n):
            continue
        x = z.read(n).decode("utf-8")
        for parent, singles in SINGLETON_CHILDREN.items():
            for m in re.finditer(rf"<(?:a|p):{parent}\b[^>]*>(.*?)</(?:a|p):{parent}>", x, re.S):
                body = m.group(1)
                for child in singles:
                    count = len(re.findall(rf"<a:{child}[ />]", body))
                    if count > 1:
                        problems.append(
                            f"{n}: <a:{parent}> contains {count} <a:{child}> elements (max 1)")
    return problems


def check_rpr_order(z):
    problems = []
    for n in z.namelist():
        if not re.match(r"ppt/(slides|slideLayouts|slideMasters)/.*\.xml$", n):
            continue
        x = z.read(n).decode("utf-8")
        for m in re.finditer(r"<a:rPr\b[^>]*>(.*?)</a:rPr>", x, re.S):
            body = m.group(1)
            order = re.findall(r"<a:([a-zA-Z]+)[ />]", body)
            ranks = [RPR_ORDER.index(t) for t in order if t in RPR_ORDER]
            if ranks != sorted(ranks):
                problems.append(f"{n}: <a:rPr> children are out of the required order")
    return problems


def check_shape_order(z):
    problems = []
    for n in z.namelist():
        if not re.match(r"ppt/slides/slide\d+\.xml$", n):
            continue
        x = z.read(n).decode("utf-8")
        for m in re.finditer(r"<p:sp>(.*?)</p:sp>", x, re.S):
            body = m.group(1)
            present = [t for t in SP_ORDER if f"<p:{t}>" in body]
            idx = [SP_ORDER.index(t) for t in present]
            if idx != sorted(idx):
                problems.append(f"{n}: <p:sp> children out of order ({present})")
            for needed in ("nvSpPr", "spPr", "txBody"):
                if f"<p:{needed}>" not in body:
                    problems.append(f"{n}: <p:sp> missing <p:{needed}>")
    return problems


def check_media(z, names):
    problems = []
    from PIL import Image
    for n in names:
        if "/media/" not in n:
            continue
        try:
            Image.open(io.BytesIO(z.read(n))).verify()
        except Exception as exc:
            problems.append(f"unreadable media {n}: {exc}")
    return problems


SLIDE_SIZES = {"screen4x3": 4 / 3, "screen16x9": 16 / 9,
               "screen16x10": 16 / 10, "screen43": 4 / 3}


def check_slide_size(z, names):
    """Catch a stale sldSz type attribute.

    python-pptx's default template declares sldSz type="screen4x3". Assigning slide_width
    and slide_height updates cx/cy but leaves the attribute alone, so a 16:9 deck can still
    claim to be 4:3 and PowerPoint may lay it out wrongly.
    """
    problems = []
    if "ppt/presentation.xml" not in names:
        return problems
    body = z.read("ppt/presentation.xml").decode("utf-8")
    m = re.search(r"<p:sldSz\b[^>]*>", body)
    if not m:
        return ["no <p:sldSz> element in presentation.xml"]
    tag = m.group(0)
    cx = re.search(r'cx="(\d+)"', tag)
    cy = re.search(r'cy="(\d+)"', tag)
    declared = re.search(r'type="([^"]+)"', tag)
    if not (cx and cy):
        return ["<p:sldSz> is missing cx/cy"]
    ratio = int(cx.group(1)) / int(cy.group(1))
    if declared:
        expected = SLIDE_SIZES.get(declared.group(1))
        if expected is not None and abs(ratio - expected) > 0.02:
            problems.append(
                f"sldSz type={declared.group(1)} disagrees with cx/cy ratio "
                f"({ratio:.3f}); set the matching type attribute or remove it")
    return problems


def check_slide_refs(z, names):
    problems = []
    if "ppt/presentation.xml" not in names:
        return ["ppt/presentation.xml missing"]
    p = z.read("ppt/presentation.xml").decode("utf-8")
    rels = z.read("ppt/_rels/presentation.xml.rels").decode("utf-8")
    rmap = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', rels))
    ids = re.findall(r'<p:sldId id="\d+" r:id="(rId\d+)"/>', p)
    for rid in ids:
        target = rmap.get(rid)
        if target is None:
            problems.append(f"presentation.xml references unknown {rid}")
            continue
        full = posixpath.normpath(posixpath.join("ppt", target))
        if full not in names:
            problems.append(f"{rid} points to missing part {full}")
    return problems


def main():
    ap = argparse.ArgumentParser(description="Validate a PPTX before delivering it.")
    ap.add_argument("pptx")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    z, names = load(args.pptx)
    checks = [
        ("zip integrity", lambda: check_zip(z)),
        ("XML well-formed", lambda: check_xml_wellformed(z)),
        ("required parts", lambda: check_required_parts(names)),
        ("content types", lambda: check_content_types(z, names)),
        ("relationships", lambda: check_relationships(z, names)),
        ("slide references", lambda: check_slide_refs(z, names)),
        ("duplicate singleton children", lambda: check_duplicate_children(z)),
        ("rPr child order", lambda: check_rpr_order(z)),
        ("p:sp child order", lambda: check_shape_order(z)),
        ("media decodable", lambda: check_media(z, names)),
        ("slide size consistency", lambda: check_slide_size(z, names)),
    ]

    failures = 0
    for label, fn in checks:
        try:
            problems = fn()
        except Exception as exc:
            problems = [f"check crashed: {exc}"]
        if problems:
            failures += len(problems)
            print(f"FAIL  {label}")
            for p in problems[:12]:
                print(f"        {p}")
            if len(problems) > 12:
                print(f"        ... and {len(problems) - 12} more")
        elif not args.quiet:
            print(f"ok    {label}")

    print()
    if failures:
        print(f"RESULT: {failures} problem(s) found. Do not deliver this file.")
        return 1
    print("RESULT: all checks passed. Safe to deliver.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
