# Quality Rubric

Score online PPT template candidates before distillation. Default acceptance threshold: `78 / 100`.

## Heuristic Score

- Preview coverage, 20 points: enough distinct slides. Full score at 8 or more useful preview pages.
- Resolution and aspect, 20 points: strong 16:9 consistency and at least 900px wide previews.
- Layout diversity, 20 points: thumbnails differ enough to indicate cover, agenda, content, data, section, or closing patterns.
- Palette coherence, 15 points: repeated colors with controlled accents; not random page-by-page color shifts.
- Visual richness, 15 points: enough contrast and shape/image structure to distill, without being empty or text-only.
- Reuse safety, 10 points: low dependency on logos, watermarks, celebrity photos, brand assets, or single-use illustrations.

## Vision Score

When a multimodal model is available, ask for:

- aesthetic_quality
- professional_polish
- layout_system
- slide_type_coverage
- originality_without_copying
- abstraction_safety

Reject if abstraction_safety is low even when the template looks good.

## Decision

- `accept`: total score is above threshold and no safety blocker exists.
- `review`: score is near threshold or source previews are limited; ask the user or use `--force-distill`.
- `reject`: low quality, insufficient previews, poor transferability, or high copyright/brand dependence.

Final style files must contain only abstract design rules and must not embed source images or source copy.

Source-quality acceptance authorizes distillation, not publication. When validation is enabled, the generated style must separately pass the closed-loop gate described in `closed-loop-validation.md` before it is promoted from staged output into the repository style library.
