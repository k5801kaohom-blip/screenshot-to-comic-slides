---
name: screenshot-to-comic-slides
description: 將截圖做成企業漫畫簡報。觸發詞：截圖轉簡報、截圖做簡報、漫畫簡報、漫畫式簡報、企業漫畫、資訊圖簡報、把截圖變成簡報、圖片做成簡報、簡報重新繪製、簡體轉繁體簡報、加 LOGO 的簡報、可編輯標題簡報、KAOHOM 簡報。Turn ordered screenshot or image sets into branded, high-resolution corporate comic/vector presentation decks in Traditional Chinese. Use when users provide multiple slide screenshots, photos, diagrams, or scanned pages and want them reconstructed in order, localized from Simplified to Traditional Chinese, visually redrawn instead of copied, branded with a logo on every slide, and delivered as a Slides resource and PPTX.
metadata:
  alias_zh-TW: 截圖轉企業漫畫簡報
  short_alias_zh-TW: 漫畫簡報
  keywords_zh-TW: 截圖, 簡報, 漫畫, 漫畫式, 企業漫畫, 資訊圖, 繁體中文, 簡體轉繁體, LOGO, KAOHOM, 可編輯標題, 流程圖說
---

# Screenshot to Corporate Comic Slides

**中文名稱**：截圖轉企業漫畫簡報（可簡稱「漫畫簡報」）

直接說「**把截圖做成漫畫簡報**」即可觸發本技能，不需要記英文名稱。

## Goal

Rebuild an ordered screenshot set as a polished 16:9 presentation. Preserve each source page's meaning and visual relationships while replacing low-resolution photos, diagrams, and UI captures with consistent corporate comic/vector infographics. Localize all visible copy to Taiwan Traditional Chinese and apply the supplied brand identity.

## Read Before Starting

- Read `/home/ubuntu/skills/slides/SKILL.md` before creating the deck.
- Read `/home/ubuntu/skills/imagegen/SKILL.md` before deciding how to redraw visuals.
- Read `/home/ubuntu/skills/image-processing/SKILL.md` before deterministic image preprocessing.
- Read `/home/ubuntu/skills/builtin-llm-models/SKILL.md` before running `scripts/extract_slide_content.py`.
- Read `references/prompt-blueprints.md` before generating the first visual or a difficult case-study page.

## Deliverable Decision

Choose one route before initialization:

1. **Image-mode Slides — default for this skill**
   - Use when the user prioritizes visual polish, comic/vector redraws, or photo-to-illustration transformation.
   - Each slide becomes a full-bleed image; slide text inside the artwork is not separately editable.
   - Use the Slides image-generation lifecycle exactly: first page alone, then later pages in batches.

2. **Illustration + editable heading PPTX — use when the user wants to retype titles**
   - Keep every generated illustration, but expose the main title and subtitle as real,
     editable PowerPoint text so any heading can be replaced later.
   - Run the pipeline in "Editable headings" below. This is the standard answer to
     requests like "keep the pictures but let me change the titles myself".

3. **HTML/PPTX Slides — use only when every label and paragraph must stay editable**
   - Use when dense copy, table cells, or all body text must be editable.
   - Generate illustration assets first, then compose them through the Slides native file authoring channel.
   - Never generate slide files through shell/Python directly inside a Slides project.

If the user asks for both highly visual pages and fully editable copy, state the tradeoff and prefer editable titles/captions with generated supporting art.

## End-to-End Workflow

### 1. Inventory and order inputs

- Separate slide screenshots from logos and other brand assets.
- Preserve the user's attachment order. Never rely on filesystem listing order.
- Create an explicit JSON manifest with one object per slide:

```json
[
  {
    "slide_number": 1,
    "source_path": "/absolute/path/page-01.webp",
    "title_hint": ""
  }
]
```

- Use `scripts/make_contact_sheet.py` to confirm order and scan for missing or duplicate pages.
- Keep every original untouched.

### 2. Extract and localize content

- Fetch the live model catalog as required by the built-in LLM skill.
- Run `scripts/extract_slide_content.py` with modest concurrency.
- Require structured JSON containing Traditional Chinese title, subtitle, body points, labels, diagram relationships, visual objects, and uncertainty.
- Convert Simplified Chinese to Taiwan Traditional Chinese, including terminology such as:
  - 基站 → 基地台
  - 算法 → 演算法
  - 接口 → 介面
  - 实时 → 即時
  - 米 → 公尺 when it is a measurement unit
- Preserve English acronyms, product names, model numbers, dates, and numerical values.
- Never invent unreadable text. Record it in `uncertain_text` and omit it from generated art unless verified.

### 3. Plan one-to-one slide mapping

- Default to one source screenshot per output slide in the same sequence.
- Do not add a generic cover, agenda, or closing page when the user explicitly asks to recreate screenshots in order.
- Build the complete Slides outline before initialization.
- Use short titles and summaries grounded in the extraction JSON.

### 4. Define the visual system

Use the supplied brand first. If no brand guide exists, default to:

- 16:9, 1280 × 720
- clean white or deep navy canvas
- navy, brand blue, cyan, and one restrained warm accent
- mature corporate comic/vector style, not childish cartoons
- isometric rooms, cutaway buildings, equipment vignettes, line-art flows, signal waves, and restrained character scenes
- one dominant visual idea per slide
- 3–6 short labels rather than paragraphs inside generated images
- logo fixed at the exact same top-left position and scale on every page

### 5. Initialize the image deck

- Call `slides/init_slides` once with the complete ordered outline and `generate_mode: "image"`.
- Make the style request explicit: corporate comic/vector, Traditional Chinese, exact logo placement, high contrast, professional information design.
- Save the returned `project_id` and use it for every subsequent operation.

### 6. Lock the style with page 1

Generate page 1 alone.

- References: `[source screenshot for page 1, supplied logo]`.
- Instruct the generator to preserve the source page's semantic hierarchy, rebuild the scene as corporate vector art, and render the exact Traditional Chinese title.
- Require the logo at the top-left with correct proportions.
- Inspect page 1 before generating the rest. It becomes the visual continuity reference.

### 7. Generate remaining pages

For every later page:

- References: `[first generated slide, corresponding source screenshot]`.
- The first reference controls visual style and logo treatment.
- The second reference controls content, objects, composition, and captions.
- Issue one `slides/generate_image_slide` call per page.
- Batch at most 10 calls per response.
- Include exact verified title and only essential verified labels in each prompt.
- Preserve the source page's correspondence:
  - source photo collage → one coherent illustrated case-study scene or illustrated montage
  - topology → accurate node-edge technical infographic
  - comparison table → visual comparison matrix with verified values
  - product catalog → consistent illustrated product lineup
  - software screenshot → localized abstract dashboard, not an untranslated screenshot

### 8. Quality gate

Create contact sheets of the generated pages and inspect every slide.

Reject or regenerate a page if any of these fail:

- wrong page order or missing page
- missing, distorted, or misplaced logo
- Simplified Chinese, garbled title, or wrong technical term
- visual does not correspond to the source screenshot
- page is mostly text boxes instead of visual storytelling
- childish clip-art style, muddy colors, unreadable labels, or overcrowding
- critical numeric value, device, role, or arrow relationship changed
- obvious cropping or aspect-ratio damage

Regenerate only failed slides with a narrower prompt. Do not restart the whole deck.

### 9. Present and export

- Call `slides/present` only after all slides are generated.
- Call `slides/export` for PPTX when requested.
- If export reports `in_progress`, retry the same call after about 30 seconds.
- If a completed deck repeatedly times out during export, use `scripts/pack_image_slides_to_pptx.py` as a fallback to package the generated slide images into a 16:9 PPTX. State that the fallback PPTX contains full-slide images.
- Deliver both:
  - the Slides resource link returned by `slides/present`
  - the verified absolute PPTX path when the user requested a file

## Editable Headings

Use this whenever the user must be able to retype headings after delivery, for example
"change 公安辦案區 to 警察辦案區" or "replace 山東濟南 with a customer name".

The illustration stays untouched; only the baked-in heading becomes live text.

### 1. Locate the headings

- Run `scripts/locate_titles.py` over the generated slides to get a first-pass box for every
  title and subtitle. This pass uses a full-slide view and is only a coarse hint.
- Run `scripts/refine_titles.py` next. It crops, upscales, and asks a stronger vision model for
  tight boxes. This second pass is what makes multi-line headings and small subtitles reliable.

```bash
python scripts/locate_titles.py generated title_bbox.json --workers 4
python scripts/refine_titles.py generated title_bbox.json title_bbox_refined.json --workers 3
```

Both scripts accept any common image extension (`png`, `jpg`, `webp`, ...) and sort naturally,
so they work directly on a Slides `generated/` directory whose files are named `s1_cover.webp`.
Do not assume `slide_*.png`; pass `--pattern` only when the directory holds images you must
exclude.

> **Do not crop a fixed left-hand region.** An earlier version of `refine_titles.py` upscaled
> only the left 72% of the slide. Wide, centred headings lost their trailing characters and the
> model dutifully returned a truncated title — `病灶解剖：重複的 a:la`, `交付前四步標準作業流`
> instead of the full text. The crop now extends to cover the coarse boxes, and
> `recover_full_text()` falls back to the complete first-pass reading when the refined text is
> a prefix of it. Always read the refined titles back before building the deck; a clean
> validator run will not catch a title that is simply missing its last two characters.

### 2. Rewrite headings with an overrides file

Create a JSON file keyed by slide number. Anything omitted keeps the detected text.

```json
{
  "1": { "skip": true },
  "24": { "title": "警察辦案區管理" },
  "30": { "title": "XXX 智慧醫院案例" },
  "42": { "title": "外企實驗室資產管控實驗室" }
}
```

- `skip: true` leaves a pure-illustration slide untouched, such as a cover with only a logo.
- A replacement that matches the original line count is laid out on the same lines.
- A replacement with a different line count is redistributed across the original lines, so
  two-line headings keep their two-line shape.

### 3. Build the editable deck

```bash
python scripts/overlay_editable_titles.py \
  --image-dir generated \
  --title-json title_bbox_refined.json \
  --overrides title_overrides.json \
  --out-dir out \
  --pptx KAOHOM_editable_titles.pptx \
  --report report.json \
  --image-format jpeg --jpeg-quality 90
```

The script erases the baked-in heading by comparing each pixel with a background estimated
from the strips above and below the text box, so bright headings on dark artwork and
low-contrast headings are removed alike. It then writes a text box in the same place, colour,
size, and alignment. `--image-format jpeg` keeps the file near 28 MB instead of about 90 MB.

### 4. Verify before delivery

Run the strict validator first. LibreOffice renders files that PowerPoint rejects, so a
visual check alone is never enough:

```bash
python scripts/validate_pptx.py deck_editable_titles.pptx
```

Then:

- Render the PPTX through LibreOffice and compare it with the original slides.
- Confirm each heading box is fully clean: no leftover strokes, no clipped first character.
- Confirm the new heading text appears on the correct line count.
- Check that the editable text is real text, not an image, before claiming editability.

#### The duplicate `a:latin` trap

`run.font.name = "..."` in python-pptx already creates `a:latin` inside `a:rPr`. Appending
another `a:latin` for the East Asian face produces `<a:latin/><a:latin/><a:ea/><a:cs/>`,
which PowerPoint reports as a corrupt file while LibreOffice still renders it correctly.
Each of `a:latin`, `a:ea`, and `a:cs` may appear at most once and must keep that order.
Use the `set_run_font()` helper in `overlay_editable_titles.py`, which checks for an
existing element before inserting, and never `append` font elements blindly.

#### The stale `sldSz` type trap

`python-pptx`'s default template declares `sldSz type="screen4x3"`. Assigning `slide_width` and
`slide_height` updates `cx`/`cy` but leaves that attribute untouched, so a 16:9 deck still
announces itself as 4:3 and PowerPoint may lay the slides out for the wrong page ratio. Set the
matching type when you set the size:

```python
from pptx.oxml.ns import qn
sld_sz = prs._element.find(qn("p:sldSz"))
if sld_sz is not None:
    sld_sz.set("type", "screen16x9")
```

`validate_pptx.py` includes a `slide size consistency` check that fails when the declared type
disagrees with the `cx`/`cy` ratio.

### 5. Report the result honestly

State clearly that headings and subtitles are editable text, while labels baked into the
illustration are not. If the user also needs those editable, move to route 3.

## Prompt Discipline

- Describe what the illustration must communicate, not only its art style.
- Name the scene, actors, devices, flow direction, and hierarchy.
- Give exact Traditional Chinese text in a clearly delimited block.
- Use minimal text in generated art. Prefer visually meaningful callouts.
- For case studies, preserve distinctive source objects and spatial relationships while replacing photographic rendering with a coherent corporate illustration.
- For formal diagrams, preserve topology and arrow direction exactly; polish must never override accuracy.

See `references/prompt-blueprints.md` for reusable prompt structures.

## Non-Negotiable Guardrails

- Never deliver a text-only deck when the user asked for comic-style or visual redesign.
- Never paste low-resolution screenshots as the main slide artwork when the user asked for redraws.
- Never retain Simplified Chinese UI screenshots without localization or abstraction.
- Never claim headings are editable unless `overlay_editable_titles.py` produced real text boxes.
- Never flatten an edited heading back into the artwork; keep it as live text.
- Never enlarge a replacement heading beyond its original box width; shrink the font instead of clipping characters.
- Never hand-edit a Slides `project.json`.
- Never use shell or Python to author HTML/PPTX slide files inside a Slides project; use the Slides-native lifecycle.
- Never claim exact transcription when source text is unreadable.
- Never fabricate customer names, metrics, certifications, product specifications, or deployment results.

## Bundled Resources

- `scripts/make_contact_sheet.py` — preserve order and create review sheets for source or generated images.
- `scripts/extract_slide_content.py` — batch OCR, semantic extraction, and Taiwan Traditional Chinese localization.
- `scripts/locate_titles.py` — first-pass title/subtitle box detection across all slides.
- `scripts/refine_titles.py` — second-pass tight boxes from an upscaled crop; use before any heading rewrite.
- `scripts/overlay_editable_titles.py` — erase baked-in headings and rebuild the deck with editable text boxes.
- `scripts/validate_pptx.py` — strict OOXML checks that catch files PowerPoint would refuse to open.
- `scripts/pack_image_slides_to_pptx.py` — fallback packager for completed image-mode Slides decks.
- `references/prompt-blueprints.md` — first-page, diagram, product, case-study, and regeneration prompt templates.
- `templates/brand_brief.example.json` — reusable brand/style intake structure.
