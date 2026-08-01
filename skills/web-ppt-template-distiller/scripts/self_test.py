#!/usr/bin/env python3
"""Deterministic smoke tests for the distiller's compiler and safety gates."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent.parent


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


distiller = load_module("distiller_self_test", HERE / "score_and_distill.py")
audit = load_module("distiller_audit_self_test", HERE / "audit_style_library.py")
batch_migrator = load_module(
    "batch_migrator_self_test", HERE / "batch_migrate_styles.py"
)
image_generator = load_module(
    "image_generator_self_test", REPO_ROOT / "scripts" / "image_generator.py"
)


def test_openai_endpoint_normalization() -> None:
    join = image_generator.openai_compatible_endpoint
    assert join("https://api.example.com", "images/generations") == (
        "https://api.example.com/v1/images/generations"
    )
    assert join("https://api.example.com/v1", "images/generations") == (
        "https://api.example.com/v1/images/generations"
    )
    assert join("https://relay.example.com/openai/v1/", "/v1/chat/completions") == (
        "https://relay.example.com/openai/v1/chat/completions"
    )


def test_multi_archetype_compiler() -> None:
    sidecar = distiller.build_layout_sidecar(
        {
            "layout_bank": {
                "data": [
                    {
                        "id": "metrics-series",
                        "composition": "metrics beside bars",
                        "routing": {"content_shapes": ["metrics-series"]},
                        "evidence_pages": ["page-06"],
                    },
                    {
                        "id": "table-timeline",
                        "composition": "attributes beside events",
                        "routing": {"content_shapes": ["timeline", "table"]},
                        "evidence_pages": ["page-06"],
                    },
                ]
            }
        },
        "demo",
    )
    assert [layout["id"] for layout in sidecar["layouts"]] == [
        "metrics-series",
        "table-timeline",
    ]


def test_validation_uses_production_routing() -> None:
    sidecar = distiller.build_layout_sidecar(
        {
            "layout_bank": {
                "data": [
                    {
                        "id": "metrics-series",
                        "composition": "metrics beside a quarterly series",
                        "routing": {"content_shapes": ["KPI trend chart"]},
                    },
                    {
                        "id": "table-timeline",
                        "composition": "attribute table beside dated milestones",
                        "routing": {
                            "content_shapes": ["tabular milestones"],
                            "requires": ["table", "timeline"],
                        },
                    },
                ]
            }
        },
        "demo",
    )
    standard = distiller.select_validation_layout("data", sidecar)
    holdout = distiller.select_validation_layout("data-table-timeline", sidecar)
    assert standard and standard["id"] == "metrics-series"
    assert holdout and holdout["id"] == "table-timeline"
    assert distiller.select_validation_roles(None, True) == [
        "cover",
        "section",
        "content",
        "data",
    ]
    assert "data-table-timeline" in distiller.select_validation_roles(
        None, True, "generalization"
    )


def test_profile_contract_blocks_incomplete_grammar() -> None:
    incomplete = {
        "identity_anchors": ["one", "two"],
        "source_evidence": [],
        "layout_bank": {
            "content_list": {
                "id": "list",
                "composition": "one list",
            }
        },
    }
    issues = distiller.profile_contract_issues(incomplete, ["page-00", "page-01"])
    assert any("identity_anchors" in issue for issue in issues)
    assert any("missing canonical role data" in issue for issue in issues)
    assert any("missing non-empty routing" in issue for issue in issues)

    valid = {
        "identity_anchors": ["one", "two", "three"],
        "source_evidence": [
            {
                "page_id": page_id,
                "observed_roles": ["content"],
                "structural_signature": "grid",
                "transferable_rules": ["stable grid"],
                "source_specific_risks": ["do not copy assets"],
            }
            for page_id in ("page-00", "page-01")
        ],
        "layout_bank": {
            "cover": {
                "id": "cover",
                "routing": {"content_shapes": ["general"]},
                "content_capacity": "one title and one subtitle",
                "evidence_pages": ["page-00"],
            },
            "section": {
                "id": "section",
                "routing": {"content_shapes": ["general"]},
                "content_capacity": {"density": "low"},
                "evidence_pages": ["page-00"],
            },
            "content": [
                {
                    "id": "list",
                    "routing": {"content_shapes": ["list"]},
                    "content_capacity": {"min_items": 2, "max_items": 4},
                    "evidence_pages": ["page-01"],
                },
                {
                    "id": "comparison",
                    "routing": {"content_shapes": ["comparison"]},
                    "content_capacity": {"columns": 2},
                    "evidence_pages": ["page-01"],
                },
            ],
            "data": [
                {
                    "id": "metrics",
                    "routing": {"content_shapes": ["metrics-series"]},
                    "content_capacity": {"max_metrics": 4},
                    "evidence_pages": ["page-01"],
                },
                {
                    "id": "timeline",
                    "routing": {"content_shapes": ["table", "timeline"]},
                    "content_capacity": {"max_items": 6},
                    "evidence_pages": ["page-01"],
                },
            ],
        },
    }
    assert distiller.profile_contract_issues(valid, ["page-00", "page-01"]) == []


def test_legacy_profile_upgrade_is_grounded_and_complete() -> None:
    profile = {
        "core_visual": ["sage blocks", "serif titles", "organic photography"],
        "layout_system": {
            "cover": "image and title split",
            "section": "number beside image",
            "content": "three-card grid",
            "data": "chart with callouts",
        },
    }
    page_ids = ["page-00", "page-01", "page-02", "page-03"]
    upgraded = distiller.upgrade_legacy_profile(profile, page_ids)
    assert distiller.profile_contract_issues(upgraded, page_ids) == []
    assert [item["page_id"] for item in upgraded["source_evidence"]] == page_ids
    assert upgraded["source_evidence"][2]["structural_signature"] == "three-card grid"
    assert len(upgraded["layout_bank"]["content"]) == 2
    assert len(upgraded["layout_bank"]["data"]) == 2
    assert "table" in upgraded["layout_bank"]["data"][1]["routing"]["content_shapes"]

    unresolved = distiller.upgrade_legacy_profile(profile, page_ids + ["page-04"])
    issues = distiller.profile_contract_issues(unresolved, page_ids + ["page-04"])
    assert any("needs visual review" in issue for issue in issues)

    full_profile = {
        "core_visual": ["one", "two", "three"],
        "layout_system": {
            "cover": "cover",
            "agenda": "agenda",
            "section": "section",
            "content": "content",
            "comparison": "comparison",
            "data": "data",
            "quote": "quote",
            "closing": "closing",
        },
    }
    full_ids = [f"page-{index:02d}" for index in range(8)]
    full_upgrade = distiller.upgrade_legacy_profile(full_profile, full_ids)
    assert {"agenda", "quote", "closing"}.issubset(full_upgrade["layout_bank"])
    assert len(distiller.build_layout_sidecar(full_upgrade, "demo")["layouts"]) == 9

    missing_quote = json.loads(json.dumps(full_upgrade))
    del missing_quote["layout_bank"]["quote"]
    missing_quote["legacy_required_roles"].remove("quote")
    restored = distiller.preserve_legacy_sidecar_roles(
        missing_quote,
        {
            "layouts": [
                {}, {}, {}, {}, {}, {},
                {"id": "quote-source", "page_type": "quote", "summary": "large statement"},
            ]
        },
        full_ids,
    )
    assert restored["layout_bank"]["quote"]["evidence_pages"] == ["page-06"]
    assert "quote" in restored["legacy_required_roles"]


def test_text_and_copying_gates() -> None:
    report = distiller.normalize_validation_report(
        {
            "aggregate_score": 94,
            "copying_risk": "low",
            "recommendation": "accept",
            "page_results": {
                "data": {
                    "fit_score": 94,
                    "readability_score": 94,
                    "role_fitness_score": 94,
                    "text_accuracy_score": 72,
                }
            },
        },
        ["data"],
        1,
        82,
        74,
        require_low_copying_risk=True,
        min_text_accuracy=90,
    )
    assert report["gate"] == "revise"
    assert report["minimum_text_accuracy_score"] == 72


def test_validation_prompt_forbids_unsupplied_decorative_text() -> None:
    prompt = distiller.validation_prompt_from_style(
        "## 基础提示词模板\nDemo",
        "demo",
        "data-table-timeline",
        '{"id":"numbered-timeline"}',
    )
    assert "every visible numeral" in prompt
    assert "if it is not in the" in prompt
    assert "replace them with non-text geometry" in prompt


def test_regression_rolls_back() -> None:
    champion = {
        "aggregate_score": 76,
        "copying_risk": "low",
        "gate": "revise",
        "page_results": {"cover": {"fit_score": 86}, "data": {"fit_score": 66}},
    }
    candidate = {
        "aggregate_score": 80,
        "copying_risk": "low",
        "gate": "revise",
        "page_results": {"cover": {"fit_score": 72}, "data": {"fit_score": 82}},
    }
    comparison = distiller.compare_validation_rounds(
        champion, candidate, ["cover", "data"], 82, 74
    )
    assert comparison["promoted"] is False
    assert comparison["maximum_sentinel_regression"] == 14


def test_library_audit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        styles = root / "styles"
        provenance = root / "provenance" / "demo"
        styles.mkdir()
        provenance.mkdir(parents=True)
        (styles / "demo.md").write_text("## 基础提示词模板\nDemo", encoding="utf-8")
        layouts = [
            {
                "id": f"data-{index}",
                "page_type": "data",
                "semantic_role": "data",
                "summary": f"Data layout {index}",
                "routing": {"content_shapes": [shape]},
                "evidence_pages": [f"page-{index - 1:02d}"],
            }
            for index, shape in enumerate(("metrics-series", "timeline"), start=1)
        ]
        (styles / "demo.layouts.json").write_text(
            json.dumps({"layouts": layouts}), encoding="utf-8"
        )
        (provenance / "source_manifest.json").write_text(
            json.dumps({"images": [{"slide_index": 0}, {"slide_index": 1}]}),
            encoding="utf-8",
        )
        (provenance / "style_profile.json").write_text(
            json.dumps(
                {
                    "source_evidence": [
                        {"page_id": "page-00", "observed_roles": ["data"]},
                        {"page_id": "page-01", "observed_roles": ["data"]},
                    ]
                }
            ),
            encoding="utf-8",
        )
        report = audit.audit_library(styles, root / "provenance")
        assert report["ready_count"] == 1


def test_batch_migration_requires_pairwise_promotion() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        work = root / "work"
        work.mkdir()
        staged = root / "staged" / "demo.md"
        staged.parent.mkdir()
        staged.write_text("demo", encoding="utf-8")
        staged.with_suffix(".layouts.json").write_text("{}", encoding="utf-8")
        status, _ = batch_migrator.classify_result(0, work, staged)
        assert status == "review"
        comparison = work / "evaluations" / "migration-comparison.json"
        comparison.parent.mkdir()
        comparison.write_text(
            json.dumps({"promoted": True, "reasons": ["net gain"]}),
            encoding="utf-8",
        )
        status, reasons = batch_migrator.classify_result(0, work, staged)
        assert status == "promoted"
        assert reasons == ["net gain"]

        comparison.unlink()
        (work / "validation_report.json").write_text(
            json.dumps(
                {
                    "status": "failed",
                    "error": "image generation service unavailable",
                }
            ),
            encoding="utf-8",
        )
        status, reasons = batch_migrator.classify_result(0, work, staged)
        assert status == "blocked-transient"
        assert "service unavailable" in reasons[0]


def test_batch_publish_backs_up_pair() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        staged = root / "staged" / "demo.md"
        styles = root / "styles"
        staged.parent.mkdir()
        styles.mkdir()
        staged.write_text("new-md", encoding="utf-8")
        staged.with_suffix(".layouts.json").write_text("new-json", encoding="utf-8")
        (styles / "demo.md").write_text("old-md", encoding="utf-8")
        (styles / "demo.layouts.json").write_text("old-json", encoding="utf-8")
        backup = batch_migrator.publish_pair(staged, styles, root / "backups")
        assert (styles / "demo.md").read_text(encoding="utf-8") == "new-md"
        assert (styles / "demo.layouts.json").read_text(encoding="utf-8") == "new-json"
        assert (backup / "demo.md").read_text(encoding="utf-8") == "old-md"
        assert (backup / "demo.layouts.json").read_text(encoding="utf-8") == "old-json"


def test_batch_prepare_only_never_uses_staging() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        styles = root / "styles"
        provenance = root / "provenance" / "demo"
        migration = root / "migration"
        styles.mkdir()
        provenance.mkdir(parents=True)
        (styles / "demo.md").write_text("old", encoding="utf-8")
        (styles / "demo.layouts.json").write_text('{"layouts":[]}', encoding="utf-8")
        images = []
        for index in range(4):
            image = provenance / f"page-{index:02d}.png"
            image.write_bytes(b"fake")
            images.append({"path": str(image), "slide_index": index})
        (provenance / "source_manifest.json").write_text(
            json.dumps(
                {
                    "canonical_url": "https://example.com/demo",
                    "style_id": "demo",
                    "style_name": "Demo",
                    "images": images,
                }
            ),
            encoding="utf-8",
        )
        (provenance / "quality_report.json").write_text(
            json.dumps({"decision": "accept", "total_score": 90}), encoding="utf-8"
        )
        (provenance / "style_profile.json").write_text(
            json.dumps(
                {
                    "core_visual": ["one", "two", "three"],
                    "layout_system": {
                        "cover": "cover split",
                        "section": "section split",
                        "content": "content grid",
                        "data": "data chart",
                    },
                }
            ),
            encoding="utf-8",
        )
        args = type(
            "Args",
            (),
            {
                "styles_dir": styles,
                "provenance_dir": root / "provenance",
                "migration_root": migration,
                "dry_run": False,
                "prepare_only": True,
            },
        )()
        result = batch_migrator.run_style(args, "demo")
        assert result["status"] == "prepared"
        assert (migration / "work/demo/prepared-candidate.md").is_file()
        assert not (migration / "staged/demo.md").exists()
        assert (styles / "demo.md").read_text(encoding="utf-8") == "old"


def test_every_distilled_output_is_a_pair() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        style_path = root / "styles" / "demo.md"
        profile = {
            "description": "Demo style",
            "layout_bank": {
                "cover": {
                    "id": "cover-hero",
                    "composition": "large title",
                    "routing": {"content_shapes": ["hero"]},
                    "content_capacity": {"density": "low"},
                },
                "content": {
                    "id": "content-split",
                    "composition": "split content",
                    "routing": {"content_shapes": ["bullets"]},
                    "content_capacity": {"density": "medium"},
                },
            },
        }
        sidecar_path = distiller.write_style_pair(
            style_path,
            "## 基础提示词模板\nDemo",
            profile,
            "demo",
        )
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        assert style_path.exists()
        assert sidecar_path == root / "styles" / "demo.layouts.json"
        assert [layout["id"] for layout in sidecar["layouts"]] == [
            "cover-hero",
            "content-split",
        ]

        prompt_path = root / "distill_prompt.md"
        distiller.write_manual_prompt(
            prompt_path,
            {"images": [{"path": "page-01.png"}]},
            {"total_score": 88, "decision": "accept"},
            "manual",
            "Manual",
            styles_dir=root / "custom-styles",
        )
        manual_prompt = prompt_path.read_text(encoding="utf-8")
        assert str(root / "custom-styles" / "manual.md") in manual_prompt
        assert str(root / "custom-styles" / "manual.layouts.json") in manual_prompt
        assert "不得只生成 Markdown" in manual_prompt


def test_migration_gate_requires_visible_net_improvement() -> None:
    roles = ["cover", "content"]
    strong = distiller.normalize_migration_comparison(
        {
            "baseline_aggregate_score": 80,
            "candidate_aggregate_score": 86,
            "baseline_copying_risk": "low",
            "candidate_copying_risk": "low",
            "decision": "promote",
            "role_results": {
                role: {
                    "baseline_fit_score": 80,
                    "candidate_fit_score": 85,
                    "baseline_readability_score": 84,
                    "candidate_readability_score": 87,
                    "candidate_text_accuracy_score": 96,
                }
                for role in roles
            },
        },
        roles,
        candidate_validation_passed=True,
        min_improvement=3,
        max_regression=2,
        min_text_accuracy=90,
    )
    assert strong["promoted"] is True
    assert strong["aggregate_gain"] == 6

    regressive = distiller.normalize_migration_comparison(
        {
            "baseline_aggregate_score": 80,
            "candidate_aggregate_score": 86,
            "baseline_copying_risk": "low",
            "candidate_copying_risk": "low",
            "decision": "promote",
            "role_results": {
                "cover": {
                    "baseline_fit_score": 88,
                    "candidate_fit_score": 82,
                    "baseline_readability_score": 90,
                    "candidate_readability_score": 89,
                    "candidate_text_accuracy_score": 96,
                },
                "content": {
                    "baseline_fit_score": 75,
                    "candidate_fit_score": 90,
                    "baseline_readability_score": 80,
                    "candidate_readability_score": 90,
                    "candidate_text_accuracy_score": 96,
                },
            },
        },
        roles,
        candidate_validation_passed=True,
        min_improvement=3,
        max_regression=2,
        min_text_accuracy=90,
    )
    assert regressive["promoted"] is False
    assert regressive["maximum_fit_regression"] == 6


def main() -> int:
    tests = [
        test_openai_endpoint_normalization,
        test_multi_archetype_compiler,
        test_validation_uses_production_routing,
        test_profile_contract_blocks_incomplete_grammar,
        test_legacy_profile_upgrade_is_grounded_and_complete,
        test_text_and_copying_gates,
        test_validation_prompt_forbids_unsupplied_decorative_text,
        test_regression_rolls_back,
        test_library_audit,
        test_batch_migration_requires_pairwise_promotion,
        test_batch_publish_backs_up_pair,
        test_batch_prepare_only_never_uses_staging,
        test_every_distilled_output_is_a_pair,
        test_migration_gate_requires_visible_net_improvement,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"{len(tests)} deterministic distiller tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
