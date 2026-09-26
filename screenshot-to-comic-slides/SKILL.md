---
name: screenshot-to-comic-slides
description: Turn ordered screenshot or image sets into branded, high-resolution corporate comic/vector presentation decks in Traditional Chinese. Use when users provide multiple slide screenshots, photos, diagrams, or scanned pages and want them reconstructed in order, localized from Simplified to Traditional Chinese, visually redrawn instead of copied, branded with a logo on every slide, and delivered as a Slides resource and PPTX.
---

# Screenshot to Corporate Comic Slides

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

2. **HTML/PPTX Slides — use only when editability or exact dense copy is primary**
   - Use when every label, table cell, or paragraph must remain editable.
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
- Never hand-edit a Slides `project.json`.
- Never use shell or Python to author HTML/PPTX slide files inside a Slides project; use the Slides-native lifecycle.
- Never claim exact transcription when source text is unreadable.
- Never fabricate customer names, metrics, certifications, product specifications, or deployment results.

## Bundled Resources

- `scripts/make_contact_sheet.py` — preserve order and create review sheets for source or generated images.
- `scripts/extract_slide_content.py` — batch OCR, semantic extraction, and Taiwan Traditional Chinese localization.
- `scripts/pack_image_slides_to_pptx.py` — fallback packager for completed image-mode Slides decks.
- `references/prompt-blueprints.md` — first-page, diagram, product, case-study, and regeneration prompt templates.
- `templates/brand_brief.example.json` — reusable brand/style intake structure.
