# Stage 5 — Design Knowledge Architecture

## Scope

Stage 5 adds a data-driven Knowledge Layer around the existing image-first `gpt-image-2` workflow. It does not replace the generator, PNG→PPTX packaging, Template Clone, Editable Workflow, or Render verification, and it adds no Demo or template library.

## Architecture

`Audience → Purpose → Tone → Recipe → Style → Typography → Composition → Imagery → Layout → Prompt` is resolved by `scripts/design_knowledge.py`. The Resolver loads JSON entities, validates the shared schema, scores selection signals, applies priorities and confidence, injects default anti-pattern guardrails, and returns a Knowledge Bundle. When no knowledge matches, an empty valid bundle preserves the existing deterministic fallback.

`generate_ppt.py` consumes the bundle before Style Intelligence and Presentation Intelligence. `style_intelligence.select_style()` uses relationship hints from the bundle to rank Style Profiles. `presentation_intelligence.plan_intelligently()` remains the decision compiler for story role, visual strategy, typography, composition, and layout. The resulting Style Profile, Knowledge Bundle identifiers, and composition decisions are appended to the existing `gpt-image-2` prompt.

## Knowledge categories

The `design_knowledge/` layer provides `typography/`, `styles/`, `composition/`, `imagery/`, `audiences/`, `industries/`, `recipes/`, and `anti_patterns/` directories, a shared `knowledge_entity.schema.json`, a category `manifest.json`, and an initial `knowledge_catalog.json`. Every entity carries id, description, applicability, constraints, recommendations, optional forbidden patterns, selection signals, relationships, priority, and confidence.

## Executable contracts

| Stage | File/function | Input | Output | Consumer |
|---|---|---|---|---|
| Load/validate | `scripts/design_knowledge.py::load_knowledge` | category JSON files | entities + validation errors | Resolver |
| Resolve | `scripts/design_knowledge.py::resolve` | audience, purpose, tone, content type, industry | ranked entities and matched signals | Bundle builder |
| Bundle | `scripts/design_knowledge.py::knowledge_bundle` | ranked entities | audience/purpose/style/typography/composition/imagery/layout/anti-pattern bundle | Style and Presentation Intelligence |
| Style decision | `scripts/style_intelligence.py::select_style` | context + Knowledge Bundle | Style Profile | prompt compiler |
| Presentation decision | `scripts/presentation_intelligence.py::plan_intelligently` | plan + config + knowledge-enriched context | decision fields on each slide | `generate_ppt.py` |
| Prompt | `scripts/generate_ppt.py` | RuntimeProfile + enriched slide + Style/Knowledge | gpt-image-2 prompt | Generation Engine |

## Tests

`tests/test_design_knowledge.py` verifies schema loading, audience and purpose influence, recipe-to-style selection, Style-to-Typography relation, Composition and Imagery influence fields, Anti-pattern guardrails, runtime addition of a new entity without Python changes, and safe fallback when no knowledge exists. Existing Stage 2–4 tests remain green.

## Decisions

The layer intentionally avoids copying Dashi's runtime or changing the target's generation model. Knowledge is configuration-first, but its effects are executable: selected relationships change style ranking, slide decisions, and prompt directives. New entities can be added under the knowledge root and loaded by the same Resolver without changing the Python core.
