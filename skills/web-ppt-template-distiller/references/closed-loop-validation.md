# Closed-loop validation

Use this reference when changing validation roles, thresholds, evaluator fields, repair behavior, or terminal states.

## Loop

```text
accepted source previews
  → distilled profile
  → render role-diverse validation pages
  → evaluate page fit + deck consistency + copying risk
  → accept | reject | revise
  → revise complete profile and repeat until the round cap
```

The default roles are `cover`, `section`, `content`, and `data`. They test first-impression identity, rhythmic transition, medium-density hierarchy, and high-density numeric/chart behavior. Optional roles are `comparison` and `closing`.

For migration pilots and final promotion, use `--validation-suite generalization`. It adds a comparison case and a held-out mixed table+timeline data case. Layout selection for validation must call the production `assign_layouts()` router with the case content; do not bypass routing with the first layout or a hard-coded validation default. This catches profiles that overfit the fixed metrics-series sample.

## Gate

Before generating paid validation images, require the reusable-profile contract: complete per-preview `source_evidence`, at least three identity anchors, canonical `cover` / `section` / `content` / `data` layout-bank keys, at least two routed content and data archetypes, valid evidence references, and data routing that covers both metrics-series and table/timeline shapes. Attempt at most two full-profile structural repairs by default; recheck the complete contract after each repair and stop before image generation if it still fails.

Accept only when all conditions hold:

- In low-cost one-pass validation, `copying_risk` must not be `high`; in closed-loop auto-publication it must be `low` (`medium` requires review).
- The evaluator returned every requested role.
- `aggregate_score >= --min-validation-score`.
- Every role has `fit_score >= --min-page-score`.
- Every role has `readability_score` and `role_fitness_score` at or above the page threshold.
- Every role has `text_accuracy_score >= --min-text-accuracy`; missing, duplicated, misspelled, merged, or garbled supplied text fails the gate.
- The evaluator did not explicitly recommend `reject`.

Reject immediately when copying risk is high or the evaluator recommends rejection. Otherwise revise while rounds remain. When the cap is reached without acceptance, use `validation_review`; this is not a pass.

## Evaluation contract

The evaluator returns:

- `aggregate_score`: overall abstract style transfer.
- `identity_score`: recognizable palette, typography mood, spacing, image treatment, and decorative language.
- `deck_consistency_score`: whether the generated pages belong to one design system.
- `layout_transfer_score`: whether the style adapts to new page roles instead of copying one composition.
- `copying_risk`: `low`, `medium`, or `high`.
- `page_results.<role>`: `fit_score`, `readability_score`, `role_fitness_score`, matches, and mismatches.
- `page_results.<role>.text_accuracy_score` and `text_errors`: exact supplied-text fidelity.
- `system_matches` and `system_mismatches`: cross-page evidence.
- `repair_actions`: concrete profile-level changes.
- `recommendation`: `accept`, `revise`, or `reject`.

The script normalizes this into `gate`, `passed`, `minimum_page_score`, `missing_roles`, and the active thresholds. Treat normalized fields as the workflow authority.

## Repair contract

Revise the complete profile, not a loose patch. Preserve successful rules and repair systemic causes. Prefer measurable constraints and reusable layout grammar over adjectives. Do not improve one role by weakening consistency across the deck. Never introduce source assets, source copy, or an exact source arrangement.

Round 1 establishes the champion. A later profile is promoted only when all weak roles improve by at least `--min-round-improvement`, successful sentinel roles regress by no more than `--max-role-regression`, copying risk does not worsen, and the candidate avoids the hard rejection gate. Failed advancement rolls back to the champion. The final profile and Markdown always come from the champion round, not merely the last attempted round.

Re-run the reusable-profile contract after every profile revision, not only after the initial distillation. Use `--profile-json` to resume from an existing complete profile; the resumed profile must pass the same contract before paid image generation.

Validation generation is role-addressable and resumable: reuse each existing non-trivial PNG, and retry only missing roles. `DISTILL_IMAGE_RETRY_ROUNDS` controls outer retry rounds and `DISTILL_IMAGE_RETRY_DELAY_SECS` controls their cooldown. These wrap the image generator's own short retries and do not change any acceptance threshold. When a later validation round exhausts generation retries, write a `generation-failed` report and retain the earlier champion. With no completed champion, fail closed and publish nothing.

Do not repair a role by encoding the validation sample verbatim. Reusable roles such as content and data should offer multiple archetypes with machine-readable routing. For example, `metrics-series`, `table-timeline`, and `categorical-split` are distinct data shapes; exact metric or period counts belong in one archetype's capacity, not in the global data rule.

Each round writes:

```text
evaluations/round-NN/
├── profile.json
├── candidate-style.md
├── candidate-style.layouts.json
├── cover.png
├── section.png
├── content.png
├── data.png
└── report.json
```

Optional-role images appear only when requested. `evaluations/summary.json` points to the latest attempted round, selected champion round, and final gate.

## Cost discipline

One round generates one image per role and performs at least one multimodal evaluation. A repairable failure adds one profile-revision call before the next round. Default to two rounds. Increase the cap only after inspecting the reports and confirming that subsequent repairs are making measurable progress.
