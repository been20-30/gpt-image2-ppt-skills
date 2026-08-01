#!/usr/bin/env python3
"""Audit distilled style sidecars against cached source provenance."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def semantic_role(layout: dict[str, Any]) -> str:
    explicit = str(layout.get("semantic_role") or "").strip()
    if explicit:
        return explicit
    best_for = layout.get("best_for")
    if isinstance(best_for, list):
        for candidate in (
            "comparison",
            "timeline",
            "process",
            "metrics",
            "table",
            "agenda",
            "section",
            "quote",
            "closing",
            "cover",
            "content",
            "data",
        ):
            if any(candidate in str(value).lower() for value in best_for):
                return candidate
    return str(layout.get("page_type") or "content")


def looks_truncated(value: Any) -> bool:
    text = str(value or "").strip()
    if len(text) < 220:
        return False
    return text[-1].isalnum() and not text.endswith(("layout", "field", "panel", "zone"))


def audit_style(style_path: Path, provenance_dir: Path) -> dict[str, Any]:
    style_id = style_path.stem
    sidecar_path = style_path.with_suffix(".layouts.json")
    provenance = provenance_dir / style_id
    manifest_path = provenance / "source_manifest.json"
    profile_path = provenance / "style_profile.json"
    issues: list[str] = []
    layouts: list[dict[str, Any]] = []
    if not sidecar_path.exists():
        issues.append("missing layout sidecar")
    else:
        sidecar = load_json(sidecar_path)
        raw_layouts = sidecar.get("layouts")
        layouts = [item for item in raw_layouts or [] if isinstance(item, dict)]
        if not layouts:
            issues.append("empty layout sidecar")
    role_counts = Counter(semantic_role(layout) for layout in layouts)
    routed = sum(bool(layout.get("routing")) for layout in layouts)
    evidenced = sum(bool(layout.get("evidence_pages")) for layout in layouts)
    routable_roles = {
        "agenda",
        "content",
        "comparison",
        "timeline",
        "process",
        "framework",
        "data",
        "table",
        "metrics",
    }
    routable_layouts = [layout for layout in layouts if semantic_role(layout) in routable_roles]
    missing_routing_ids = [
        str(layout.get("id") or "unknown")
        for layout in routable_layouts
        if not layout.get("routing")
    ]
    missing_evidence_ids = [
        str(layout.get("id") or "unknown")
        for layout in layouts
        if not layout.get("evidence_pages")
    ]
    truncated = [
        str(layout.get("id") or "unknown")
        for layout in layouts
        if looks_truncated(layout.get("summary"))
    ]
    if missing_routing_ids:
        issues.append("missing routing on reusable layouts")
    if missing_evidence_ids:
        issues.append("incomplete source evidence mapping")
    if truncated:
        issues.append("possibly truncated layout summaries")
    if layouts and max(role_counts.values(), default=0) < 2:
        issues.append("no role has multiple layout archetypes")
    preview_count = 0
    known_page_ids: set[str] = set()
    if manifest_path.exists():
        manifest = load_json(manifest_path)
        manifest_images = manifest.get("images") or []
        preview_count = len(manifest_images)
        for index, item in enumerate(manifest_images):
            if isinstance(item, dict):
                page_index = item.get("slide_index", index)
            else:
                page_index = index
            try:
                known_page_ids.add(f"page-{int(page_index):02d}")
            except (TypeError, ValueError):
                known_page_ids.add(f"page-{index:02d}")
    else:
        issues.append("missing source manifest")
    source_evidence_count = 0
    invalid_evidence_pages: list[str] = []
    if not profile_path.exists():
        issues.append("missing authoritative source profile")
    else:
        profile = load_json(profile_path)
        source_evidence = profile.get("source_evidence")
        if not isinstance(source_evidence, list) or not source_evidence:
            issues.append("missing source evidence catalog")
        else:
            source_evidence_count = len(source_evidence)
            evidence_ids = {
                str(item.get("page_id") or "").strip()
                for item in source_evidence
                if isinstance(item, dict)
            }
            invalid_evidence_pages = sorted(
                page_id for page_id in evidence_ids if page_id and page_id not in known_page_ids
            )
            if invalid_evidence_pages:
                issues.append("source evidence references unknown pages")
    invalid_layout_evidence_pages = sorted(
        {
            str(page_id)
            for layout in layouts
            for page_id in (
                layout.get("evidence_pages")
                if isinstance(layout.get("evidence_pages"), list)
                else []
            )
            if str(page_id) not in known_page_ids
        }
    )
    if invalid_layout_evidence_pages:
        issues.append("layout evidence references unknown pages")
    return {
        "style_id": style_id,
        "style_path": str(style_path),
        "sidecar_path": str(sidecar_path),
        "source_manifest": str(manifest_path),
        "source_profile": str(profile_path),
        "preview_count": preview_count,
        "source_evidence_count": source_evidence_count,
        "invalid_evidence_pages": invalid_evidence_pages,
        "invalid_layout_evidence_pages": invalid_layout_evidence_pages,
        "layout_count": len(layouts),
        "role_counts": dict(sorted(role_counts.items())),
        "routed_layouts": routed,
        "evidenced_layouts": evidenced,
        "routing_coverage": (
            (len(routable_layouts) - len(missing_routing_ids)) / len(routable_layouts)
            if routable_layouts
            else 1.0
        ),
        "evidence_coverage": evidenced / len(layouts) if layouts else 0.0,
        "missing_routing_ids": missing_routing_ids,
        "missing_evidence_ids": missing_evidence_ids,
        "truncated_layout_ids": truncated,
        "issues": issues,
        "status": "ready" if not issues else "needs-upgrade",
    }


def audit_library(styles_dir: Path, provenance_dir: Path) -> dict[str, Any]:
    records = []
    for style_path in sorted(styles_dir.glob("*.md")):
        if not (provenance_dir / style_path.stem).exists():
            continue
        records.append(audit_style(style_path, provenance_dir))
    issue_counts = Counter(issue for record in records for issue in record["issues"])
    return {
        "styles_dir": str(styles_dir),
        "provenance_dir": str(provenance_dir),
        "style_count": len(records),
        "ready_count": sum(record["status"] == "ready" for record in records),
        "needs_upgrade_count": sum(record["status"] != "ready" for record in records),
        "issue_counts": dict(sorted(issue_counts.items())),
        "styles": records,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--styles-dir", default="styles")
    parser.add_argument("--provenance-dir", required=True)
    parser.add_argument("--output", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = audit_library(Path(args.styles_dir), Path(args.provenance_dir))
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
        print(f"Wrote audit: {output}")
    print(
        json.dumps(
            {
                "style_count": report["style_count"],
                "ready_count": report["ready_count"],
                "needs_upgrade_count": report["needs_upgrade_count"],
                "issue_counts": report["issue_counts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
