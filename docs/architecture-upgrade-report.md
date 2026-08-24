# Architecture Upgrade Report — gpt-image2-ppt-ar-pro

## Executive summary

The Fork keeps the original `gpt-image-2` image-generation and PNG-to-PPTX workflow. The upgrade adds decision-making and verification layers around it instead of replacing the engine. The architecture now separates presentation planning, generation, design quality, and technical quality. The final delivery decision is the intersection of independent Design Quality and Technical Quality results.

## Original architecture review

The original project is strong at style/template ingestion, prompt compilation, external image slots, session metadata, image generation, and PPTX packaging. Its main architectural gap was that visual quality, technical validity, and storytelling intent were not represented as independent machine-readable contracts. A successful image or PPTX could therefore pass without proving RTL safety, layout diversity, typography suitability, or visual hierarchy.

## What was adopted from Dashi

Dashi's useful ideas were adopted selectively: canonical content metadata, explicit story roles, composition families, layout signatures, a pre-generation allocation step, machine-readable validation, and a Render→Inspect→Fix loop. These ideas improve decision traceability and prevent the agent from treating each slide as an isolated prompt.

## What was deliberately rejected

The project did not copy Dashi's React/browser Runtime, HTML-first rendering model, or its full editable-object architecture. Those are appropriate for Dashi's browser-editable deck model but would replace the target's image-native strengths and violate the requirement to preserve `gpt-image-2`. The target remains image-first, with the new contracts acting as an orchestration and verification layer.

## Four-system architecture

### Presentation Intelligence

`design_system/arabic_design_system.json` defines Arabic typography, type scale, spacing, contrast floors, safe text zones, and text-first priorities. `design_system/layout_taxonomy.json` defines story roles and composition families. `scripts/select_layouts.py` adds `layout_family`, `story_role`, `layout_signature`, direction, and an anti-repetition policy to a compatible plan.

### Generation Engine

`scripts/generate_ppt.py` remains the production engine and still selects `gpt-image-2`. It now appends the selected composition family, narrative role, and layout signature to the compiled image prompt and records them in pending task metadata. Existing style sidecars, template handling, external asset slots, session editing, and PPTX packaging remain available.

### Design Quality Engine

`scripts/quality_engine.py::design_quality` evaluates typography budget, hierarchy, composition repetition, art-direction family validity, storytelling roles, consistency, and card overuse. It produces an independent score and hard failures. A valid PPTX does not automatically pass this engine.

### Technical Quality Engine

`scripts/quality_engine.py::technical_quality` evaluates declared Arabic/RTL direction, render presence, image validity, 16:9 aspect ratio, safe-zone contract flags, and LibreOffice evidence. It produces a separate score and hard failures. A visually attractive slide does not automatically pass this engine.

### Final decision

`scripts/quality_gate.py` is a backward-compatible CLI wrapper. It delegates to both engines and returns separate `design_quality` and `technical_quality` objects plus `final_decision`. Remediation ownership belongs to the lower-scoring engine.

## Typography and RTL behavior

Arabic plans activate the Arabic design system. Headings use a specified Arabic pairing, body copy uses the Arabic body font pairing, and numbers/dates/code/chart axes are isolated. RTL is an explicit plan contract rather than an informal prompt suggestion. Safe text zones and text budgets are represented in the design system and enforced or reported by the engines.

## Tests

`tests/test_quality_architecture.py` covers adjacent-layout rejection, varied-story acceptance, independence between design and technical results, RTL rejection, render counting, and LibreOffice evidence. Additional regression checks compile all Python scripts, validate the installer shell syntax, run `git diff --check`, and run `generate_ppt.py --prepare-only` to prove compatibility with the existing gpt-image-2 path.

## References

1. [Target Fork](https://github.com/been20-30/gpt-image2-ppt-skills)
2. [Dashi engineering reference](https://github.com/been20-30/dashi-ppt-skill)

## Stage 2: executable intelligence

The second architecture stage adds `scripts/presentation_intelligence.py`. It turns each slide into a decision chain: story role → content density → visual strategy → typography decision → layout family → composition → generation instruction. The resulting fields are consumed by `generate_ppt.py` and appended to the gpt-image-2 prompt, so the intelligence changes generation behavior rather than acting as documentation.

The stage also adds `scripts/design_critic.py`. It converts design failures into actionable repairs with a problem, cause, recommended change, and regeneration instruction. `quality_engine.py` now includes independent dimensions for information design, visual metaphor, and premium feel, and the final report carries the critic output alongside separate design and technical results.

## Stage 4 — Design System Intelligence

Stage 4 adds `design_system/style_profiles.json`, `design_system/composition_grammar.json`, and `scripts/style_intelligence.py`. A Style Profile now describes visual identity, color and typography philosophy, font pair, type scale, spacing, border/radius, image and illustration treatment, shape language, density, whitespace, composition preference, acceptable families, forbidden patterns, and focal-point behavior.

`style_intelligence.select_style()` scores topic, audience, purpose, tone, content type, and requested style. The selected profile is injected into the existing `gpt-image-2` prompt with color philosophy, typography philosophy, image treatment, shape language, focal behavior, forbidden patterns, and composition preference. No new template library was added.

Composition Grammar describes focal point, anchor, supporting element, reading path, whitespace/text/image zones, balance, scale relationship, and hierarchy. The configuration is intentionally separate from layout family names so two editorial slides can have different composition grammars.

Stage 4 also extends tests to verify data-driven style selection, emitted composition grammar, prompt influence, and existing Stage 3 behavior. The full test suite passes without generating a new Demo.
