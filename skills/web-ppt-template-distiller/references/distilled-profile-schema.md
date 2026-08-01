# Distilled profile schema

Use this reference when changing profile extraction, Markdown rendering, layout matching, or profile repair.

## Identity

- `style_id`, `style_name_zh`, `style_name_en`, `description`
- `palette`: reusable colors or color roles, not sampled source assets.
- `identity_anchors`: three to five abstract traits that must survive every page role.
- `core_visual`: concise visual direction.
- `source_evidence`: one abstract record per preview (`page_id`, `observed_roles`, `structural_signature`, `transferable_rules`, `source_specific_risks`). Layout evidence must reference these page ids.
- `provenance_summary`: source URLs and abstract observations only.

## Tokens

`design_tokens` should define colors, fonts, spacing, shape language, texture, grid, and motion/depth. Prefer measurable ratios, ranges, and relationships. Do not require unavailable proprietary fonts; state portable fallbacks.

## Layout grammar

- `layout_system`: cross-page grid, anchors, rails, rhythm, and visual-weight rules.
- `layout_bank`: object keyed by page role. Each role may be one compact archetype object or a list of 2-4 distinct archetypes. Each archetype contains:
  - `id`
  - `composition`
  - `zones`, preferably normalized to the 0–1 slide canvas
  - `content_capacity`
  - `routing`: machine-readable `content_shapes`, item/metric/series ranges, `requires`, `excludes`, and optional keywords
  - `evidence_pages`: source preview page ids supporting the abstract rule
  - `required_identity_anchors`
  - `optional_variants`
  - `avoid`
- `cover_layout`, `section_layout`, `content_layout`, `data_layout`, `closing_layout`: concise renderer-facing summaries retained for compatibility.
- `density_rules`: low-, medium-, and high-density adaptations. At high density, simplify decoration before reducing legibility.
- `variation_rules`: allowed ways to move emphasis while keeping identity.
- `anti_repetition_rules`: prevent consecutive slides from sharing the same composition and decoration placement.

Recommended layout roles are `cover`, `agenda`, `section`, `statement`, `content`, `image-content`, `comparison`, `timeline`, `process`, `framework`, `data`, `table`, `metrics`, `case-study`, `team`, `quote`, `diagram`, and `closing`. A profile may omit unsupported roles, but validation roles must have enough rules to generate a credible page.

Do not use `optional_variants` as a substitute for materially different layouts. If geometry, capacity, or semantic structure changes, create another archetype. Do not encode the exact validation sample as a universal role rule: “2-4 metrics plus 3-6 periods” can describe one routed data archetype, while the global data rule should also permit source-supported table/timeline, comparison, and categorical structures.

## Media and data

- `image_treatment`: crop, mask, color treatment, overlay, edge behavior, and safe replacement rules.
- `iconography`: stroke/fill language, geometry, complexity, and placement.
- `chart_style`: chart types, color mapping, axes, labels, lines, fills, highlights, and forbidden effects.

## Safety and use

- `forbidden`: stylistic failures and incompatible effects.
- `do_not_copy`: source-specific images, logos, characters, text, watermarks, and unique arrangements.
- `scenarios`: content domains where the abstraction transfers well.

Keep the structured JSON authoritative. Render `style.md` from it for model consumption; do not manually let the two representations drift.
