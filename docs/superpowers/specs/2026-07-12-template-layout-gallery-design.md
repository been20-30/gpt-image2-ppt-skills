# Template Layout Gallery Design

## Goal

Create a user-facing gallery that demonstrates every declared layout in every built-in PPT style. The gallery must make visual comparison easy by using the same Chinese content in every style.

## Scope

- Cover all 32 `styles/*.md` style templates.
- Cover all 8 layouts in each matching `styles/*.layouts.json` file.
- Generate 256 slides in total.
- Deliver one independent 8-slide PPTX per style, plus the eight slide PNGs used to build it.
- Do not create a combined 256-slide PPTX.
- Keep the normal image-based PPTX mode; editable PPTX reconstruction is out of scope.

The current layout banks consistently expose these page forms:

1. Cover
2. Agenda
3. Section divider
4. Structured content
5. Two-zone comparison
6. Data or metric visualization
7. Quote
8. Closing

## Canonical Content

All styles use the same topic: **AI 做 PPT 的三种方式**.

The three methods are:

1. Direct image generation
2. HTML-based slide generation
3. Native PPT generation

The eight-slide narrative is:

1. **Cover:** AI 做 PPT 的三种方式
2. **Agenda:** 直接图像生成、HTML 生成、原生 PPT 生成
3. **Section:** 视觉表现、可编辑性与工程成本的取舍
4. **Overview:** Three cards explaining how each method works and where it fits
5. **Pros and cons:** Advantages on the left and limitations on the right, covering all three methods
6. **Comparison:** A clearly labeled, scenario-based five-level comparison across visual potential, generation speed, editability, compatibility, and automation
7. **Quote:** 没有绝对最好的生成方式，只有与交付目标更匹配的技术路线
8. **Closing:** 视觉展示选图像生成，Web 传播选 HTML，正式交付与协作编辑选原生 PPT

The comparison language must remain neutral and must not present illustrative ratings as industry research.

## Content Positioning

### Direct image generation

- Strengths: high visual potential, fast generation, and strong cross-slide consistency when constrained by a shared style prompt, layout bank, reference images, or templates.
- Limitations: text accuracy, element-level editability, deterministic output, and exact reproducibility.

### HTML generation

- Strengths: code-level control, reuse, automation, responsive layout, and web animation.
- Limitations: browser and export differences, conversion fidelity, and limited native PowerPoint editing after export.

### Native PPT generation

- Strengths: editable objects, Office compatibility, collaboration, and reliable formal delivery.
- Limitations: higher implementation complexity, more demanding precise layout logic, and visual quality that depends heavily on templates and the layout system.

## Generation Strategy

Use explicit layout assignment rather than automatic layout selection. Each style-specific plan must map its eight slides to the eight layout IDs declared in that style's layout bank, in file order. This guarantees one generated example per declared layout, including the distinct layout IDs in `eco-green-business-plan`.

Markdown remains the source of truth. Create or generate reviewable style-specific Markdown plans from the canonical content, then derive JSON plans with `scripts/md_to_plan.py`. Do not hand-edit generated JSON.

Use each style's own `styles/<id>.md` and matching layout bank. Each style produces a separate output directory containing images, generation records, and an 8-slide PPTX.

## Smoke Test and Rollout

1. Generate all eight layouts for `clean-tech-blue` as the smoke deck.
2. Review layout coverage, Chinese text legibility, content fit, visual consistency, and PPTX packaging.
3. After approval, generate the remaining 31 styles.
4. If a slide fails, regenerate only that slide while keeping its assigned layout and canonical content.

## Output Organization

The final gallery root should make each style independently browsable:

```text
outputs/<timestamp>/template-layout-gallery/
├── clean-tech-blue/
│   ├── images/
│   │   ├── slide-01.png
│   │   └── slide-08.png
│   ├── prompts.json
│   ├── metadata.json
│   └── clean-tech-blue-layout-gallery.pptx
└── y2k-chrome/
    ├── images/
    ├── prompts.json
    ├── metadata.json
    └── y2k-chrome-layout-gallery.pptx
```

The same directory structure applies to every style ID between these examples, for 32 style directories in total.

An inventory file may list style IDs, layout IDs, generation status, and output paths. It is an index only, not a combined presentation.

## Quality Gates

For every style:

- Exactly eight slides exist and each declared layout ID appears once.
- The same canonical meaning is preserved across styles.
- All visible text is simplified Chinese except necessary technical terms such as HTML and PPT.
- Slides are 16:9 landscape and contain no unintended square or portrait output.
- Titles and body text remain readable at normal presentation size.
- The data page labels its ratings as scenario-based reference, not measured industry data.
- Direct image generation is not described as inherently weak in cross-slide consistency.
- The PPTX opens successfully and contains the eight generated pages in the correct order.

## Failure Handling

- Missing style/layout sidecars stop that style before generation.
- Schema or content-capacity mismatch is fixed in the Markdown plan and regenerated through `md_to_plan.py`.
- Failed image requests are retried per slide, without changing the layout assignment.
- A failed style remains clearly marked incomplete; it is not silently omitted from the gallery.

## Out of Scope

- Editable scene reconstruction
- A combined master gallery PPTX
- Different content tailored to individual styles
- Template cloning from an external `.pptx`
- Claims based on fabricated benchmark data
