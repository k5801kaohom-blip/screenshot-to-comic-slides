# Prompt Blueprints

Use these as structures, not rigid copy. Fill every bracket with verified content from the source extraction.

## First slide: lock brand and visual style

```text
Create a 16:9 high-resolution corporate comic/vector presentation slide.
Purpose: [what this source page communicates].
Source fidelity: use the supplied source screenshot for semantic hierarchy, objects, scene, and relationships; redraw everything rather than pasting the screenshot.
Visual scene: [people, facility, devices, flows, floor plan, product, or diagram].
Composition: [dominant focal point, secondary callouts, negative space, reading order].
Style: mature enterprise consulting illustration; semi-flat or isometric vector art; crisp 2 px line work; brand navy, brand blue, cyan, and restrained warm accent; no childish cartoon style.
Exact Traditional Chinese title: 「[title]」
Essential labels only: 「[label 1]」「[label 2]」「[label 3]」
Branding: reproduce the supplied logo accurately at the top-left, preserving aspect ratio and clear space.
Avoid: Simplified Chinese, garbled text, long paragraphs, generic stock clip-art, unreadable micro-labels, unrelated objects.
```

## Later slide: style + source reference

Use the first generated slide as reference 1 and the corresponding source screenshot as reference 2.

```text
Create slide [N] in exactly the same brand system, illustration language, logo treatment, color palette, and visual density as reference 1.
Reconstruct the content of reference 2 as a polished corporate comic/vector infographic.
Message: [one-sentence takeaway].
Preserve from the source: [distinctive objects], [actors], [spatial arrangement], [diagram arrows or table values], [photo captions].
Redraw as: [isometric room / cutaway building / product lineup / technical topology / role-based scene / comparison matrix].
Exact Traditional Chinese title: 「[title]」
Essential verified labels: 「[labels]」
Make the page visually led, with illustration occupying most of the canvas and no more than 3–6 short labels.
Keep the KAOHOM/brand logo at the identical top-left position and scale shown in reference 1.
Avoid: Simplified Chinese, copied screenshot pixels, photo-real collage, childish cartoons, text-box-heavy layout, changed technical relationships.
```

## Case-study photo replacement

```text
Transform the source photo collage into one coherent illustrated case-study scene or a tightly organized illustrated montage.
Preserve the recognizable evidence: [building exterior], [device on ceiling], [wristband], [dashboard or floor map], [people and room type].
Show cause and effect with restrained cyan callout lines and short Traditional Chinese captions.
Do not invent a different customer site, building type, device, or workflow.
```

## Technical topology or flowchart

```text
Rebuild the topology as an accurate corporate technical infographic.
Nodes, in order: [node list].
Directed relationships: [A → B], [B ↔ C], [C → D].
Keep arrows and data-flow directions exact. Use modern vector hardware symbols and clear grouping layers.
Decorative polish must not change the graph.
```

## Comparison slide

```text
Replace the source table with a visual comparison matrix using verified values only.
Compared options: [options].
Criteria: [criteria].
Verified values: [values].
Highlight the intended advantage with brand cyan or amber, never by fabricating a higher score.
Keep all numbers, units, and acronyms exact.
```

## Product lineup

```text
Redraw the supplied product photos as a consistent product illustration family.
Preserve form factor, color variants, buttons, display, strap, mounting method, and charger relationships.
Arrange as a premium product catalog with short Traditional Chinese captions and ample whitespace.
```

## Focused regeneration prompt

```text
Regenerate only slide [N]. Preserve the established deck style and all correct content.
Fix exactly these failures:
1. [incorrect or garbled title → exact replacement]
2. [missing logo / wrong position]
3. [wrong object or relationship]
4. [page too text-heavy → replace with specified scene]
Do not change: [verified parts to preserve].
```

## QA prompt for a review agent

```text
Compare the generated slide with its source screenshot and extraction JSON.
Return pass/fail for: page correspondence, Traditional Chinese title, terminology, numerical fidelity, logo presence, visual storytelling, diagram direction, and legibility.
List only material failures that require regeneration. Do not critique subjective minor spacing.
```
