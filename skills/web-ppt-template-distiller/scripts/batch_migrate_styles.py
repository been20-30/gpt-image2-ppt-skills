#!/usr/bin/env python3
"""Migrate installed distilled styles through a same-prompt visual promotion gate."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
DISTILLER = HERE / "score_and_distill.py"
REPO_ROOT = HERE.parent.parent.parent


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def load_distiller_module():
    spec = importlib.util.spec_from_file_location("batch_migration_distiller", DISTILLER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load distiller: {DISTILLER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def source_root_for(provenance_dir: Path) -> Path:
    """Return the directory against which legacy manifest image paths were written."""
    if provenance_dir.parent.name == ".ppt-template-distill":
        return provenance_dir.parent.parent
    return provenance_dir.parent


def portable_manifest(manifest: dict[str, Any], provenance_dir: Path) -> dict[str, Any]:
    """Make cached preview paths absolute so migration is independent of caller cwd."""
    result = json.loads(json.dumps(manifest))
    source_root = source_root_for(provenance_dir)
    style_id = str(result.get("style_id") or "")
    for item in result.get("images") or []:
        if not isinstance(item, dict) or not item.get("path"):
            continue
        original = Path(str(item["path"])).expanduser()
        candidates = [original]
        if not original.is_absolute():
            candidates = [
                source_root / original,
                provenance_dir / style_id / "images" / original.name,
            ]
        resolved = next((path.resolve() for path in candidates if path.is_file()), None)
        if resolved is None:
            raise FileNotFoundError(f"cached preview is missing: {original}")
        item["path"] = str(resolved)
    return result


def discover_style_ids(
    styles_dir: Path,
    provenance_dir: Path,
    audit_json: Path | None = None,
) -> list[str]:
    if audit_json:
        audit = load_json(audit_json)
        return [
            str(item["style_id"])
            for item in audit.get("styles") or []
            if isinstance(item, dict) and item.get("status") != "ready"
        ]
    return [
        path.stem
        for path in sorted(styles_dir.glob("*.md"))
        if (provenance_dir / path.stem / "source_manifest.json").is_file()
    ]


def seed_workdir(style_id: str, provenance_dir: Path, work_root: Path) -> Path:
    source = provenance_dir / style_id
    work_dir = work_root / style_id
    work_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = work_dir / "source_manifest.json"
    quality_path = work_dir / "quality_report.json"
    if not manifest_path.exists():
        manifest = portable_manifest(load_json(source / "source_manifest.json"), provenance_dir)
        atomic_json(manifest_path, manifest)
    if not quality_path.exists():
        shutil.copy2(source / "quality_report.json", quality_path)
    seed_profile = work_dir / "seed_profile.json"
    if not seed_profile.exists():
        shutil.copy2(source / "style_profile.json", seed_profile)
    return work_dir


def classify_result(
    returncode: int,
    work_dir: Path,
    staged_md: Path,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    comparison_path = work_dir / "evaluations" / "migration-comparison.json"
    validation_path = work_dir / "validation_report.json"
    if returncode != 0:
        return "failed", [f"distiller exited with {returncode}"]
    if comparison_path.is_file():
        comparison = load_json(comparison_path)
        reasons.extend(str(value) for value in comparison.get("reasons") or [])
        if comparison.get("promoted") is True:
            sidecar = staged_md.with_suffix(".layouts.json")
            if staged_md.is_file() and sidecar.is_file():
                return "promoted", reasons
            return "failed", reasons + ["promotion report exists but staged pair is missing"]
        return "review", reasons or ["same-prompt migration gate did not promote"]
    if validation_path.is_file():
        validation = load_json(validation_path)
        error = str(validation.get("error") or "")
        reasons.append(error or str(validation.get("gate") or "validation incomplete"))
        if is_transient_generation_error(error):
            return "blocked-transient", reasons
    return "review", reasons or ["candidate did not reach pairwise migration comparison"]


def is_transient_generation_error(message: str) -> bool:
    normalized = message.lower()
    return any(
        marker in normalized
        for marker in (
            "service unavailable",
            "temporarily unavailable",
            "internal_error",
            "connection reset",
            "connection aborted",
            "timed out",
            "timeout",
            "rate limit",
            "too many requests",
        )
    )


def publish_pair(staged_md: Path, styles_dir: Path, backup_root: Path) -> Path:
    """Publish a promoted pair, rolling back both files if either replace fails."""
    staged_sidecar = staged_md.with_suffix(".layouts.json")
    if not staged_md.is_file() or not staged_sidecar.is_file():
        raise FileNotFoundError("cannot publish an incomplete staged style pair")
    target_md = styles_dir / staged_md.name
    target_sidecar = target_md.with_suffix(".layouts.json")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = backup_root / staged_md.stem / stamp
    backup_dir.mkdir(parents=True, exist_ok=True)
    for target in (target_md, target_sidecar):
        if target.is_file():
            shutil.copy2(target, backup_dir / target.name)

    incoming: list[tuple[Path, Path]] = []
    for source, target in ((staged_md, target_md), (staged_sidecar, target_sidecar)):
        temporary = target.with_name(f".{target.name}.migration-tmp")
        shutil.copy2(source, temporary)
        incoming.append((temporary, target))
    try:
        for temporary, target in incoming:
            os.replace(temporary, target)
    except Exception:
        for temporary, _ in incoming:
            temporary.unlink(missing_ok=True)
        for target in (target_md, target_sidecar):
            backup = backup_dir / target.name
            if backup.is_file():
                shutil.copy2(backup, target)
            else:
                target.unlink(missing_ok=True)
        raise
    return backup_dir


def run_style(args: argparse.Namespace, style_id: str) -> dict[str, Any]:
    styles_dir = args.styles_dir.resolve()
    provenance_dir = args.provenance_dir.resolve()
    migration_root = args.migration_root.resolve()
    work_root = migration_root / "work"
    staging_dir = migration_root / "staged"
    work_dir = seed_workdir(style_id, provenance_dir, work_root)
    manifest = load_json(work_dir / "source_manifest.json")
    style_name = str(manifest.get("style_name") or manifest.get("title") or style_id)
    url = str(manifest.get("canonical_url") or "").strip()
    if not url:
        raise ValueError(f"missing canonical_url for {style_id}")
    resume_profile = work_dir / "style_profile.json"
    if not resume_profile.is_file():
        resume_profile = work_dir / "seed_profile.json"

    if args.prepare_only and not args.dry_run:
        distiller = load_distiller_module()
        profile = load_json(resume_profile)
        page_ids = [
            f"page-{index:02d}" for index, _ in enumerate(manifest.get("images") or [])
        ]
        upgraded = distiller.upgrade_legacy_profile(profile, page_ids)
        baseline_sidecar = styles_dir / f"{style_id}.layouts.json"
        if baseline_sidecar.is_file():
            upgraded = distiller.preserve_legacy_sidecar_roles(
                upgraded,
                load_json(baseline_sidecar),
                page_ids,
            )
        issues = distiller.profile_contract_issues(upgraded, page_ids)
        vision_error = ""
        if issues and getattr(args, "repair_with_vision", False):
            distiller.load_scoped_env_files()
            try:
                upgraded = distiller.ensure_profile_contract(
                    manifest,
                    upgraded,
                    max(0, int(getattr(args, "max_profile_repairs", 2))),
                )
                issues = distiller.profile_contract_issues(upgraded, page_ids)
            except Exception as exc:
                vision_error = str(exc)
        atomic_json(work_dir / "style_profile.json", upgraded)
        prepared_md = work_dir / "prepared-candidate.md"
        if issues:
            prepared_md.unlink(missing_ok=True)
            prepared_md.with_suffix(".layouts.json").unlink(missing_ok=True)
            return {
                "style_id": style_id,
                "status": "needs-vision",
                "reasons": issues + ([f"vision repair failed: {vision_error}"] if vision_error else []),
                "work_dir": str(work_dir),
                "profile": str(work_dir / "style_profile.json"),
                "published": False,
            }
        style_md = distiller.render_style_markdown(upgraded, style_id, style_name)
        distiller.write_style_pair(
            prepared_md,
            style_md,
            upgraded,
            style_id,
            distiller.manifest_source_hash(manifest),
        )
        return {
            "style_id": style_id,
            "status": "prepared",
            "reasons": ["legacy profile compiled into the current structural contract"],
            "work_dir": str(work_dir),
            "profile": str(work_dir / "style_profile.json"),
            "prepared_pair": str(prepared_md),
            "published": False,
        }

    staged_md = staging_dir / f"{style_id}.md"
    command = [
        sys.executable,
        str(DISTILLER),
        "--url",
        url,
        "--style-id",
        style_id,
        "--name",
        style_name,
        "--styles-dir",
        str(staging_dir),
        "--work-dir",
        str(work_root),
        "--state-db",
        str(migration_root / "distill_state.sqlite"),
        "--profile-json",
        str(resume_profile),
        "--baseline-style",
        str(styles_dir / f"{style_id}.md"),
        "--closed-loop",
        "--validation-suite",
        "generalization",
        "--max-validation-rounds",
        str(args.max_validation_rounds),
        "--max-profile-repairs",
        str(args.max_profile_repairs),
        "--min-validation-score",
        str(args.min_validation_score),
        "--min-page-score",
        str(args.min_page_score),
        "--min-round-improvement",
        str(args.min_round_improvement),
        "--max-role-regression",
        str(args.max_role_regression),
        "--min-text-accuracy",
        str(args.min_text_accuracy),
        "--resume",
        "--overwrite",
    ]
    log_path = work_dir / "migration.log"
    if args.dry_run:
        return {
            "style_id": style_id,
            "status": "dry-run",
            "command": command,
            "work_dir": str(work_dir),
        }
    # Keep reusable role images/profile state, but never let a prior promotion marker or
    # staged pair satisfy the current run's gate.
    (work_dir / "evaluations" / "migration-comparison.json").unlink(missing_ok=True)
    (work_dir / "validation_report.json").unlink(missing_ok=True)
    staged_md.unlink(missing_ok=True)
    staged_md.with_suffix(".layouts.json").unlink(missing_ok=True)
    child_env = os.environ.copy()
    child_env.setdefault("DISTILL_IMAGE_RETRY_ROUNDS", str(args.image_retry_rounds))
    child_env.setdefault("DISTILL_IMAGE_RETRY_DELAY_SECS", str(args.image_retry_delay_secs))
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n[{datetime.now(timezone.utc).isoformat()}] {' '.join(command)}\n")
        log.flush()
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=child_env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    status, reasons = classify_result(completed.returncode, work_dir, staged_md)
    result: dict[str, Any] = {
        "style_id": style_id,
        "status": status,
        "returncode": completed.returncode,
        "reasons": reasons,
        "work_dir": str(work_dir),
        "log": str(log_path),
    }
    if status == "promoted" and args.publish:
        backup = publish_pair(staged_md, styles_dir, migration_root / "backups")
        result["published"] = True
        result["backup_dir"] = str(backup)
    else:
        result["published"] = False
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--styles-dir", type=Path, default=REPO_ROOT / "styles")
    parser.add_argument("--provenance-dir", type=Path, required=True)
    parser.add_argument("--migration-root", type=Path, required=True)
    parser.add_argument("--audit-json", type=Path)
    parser.add_argument("--style-id", action="append", default=[])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Compile legacy profiles into workdir candidates without image generation or publication.",
    )
    parser.add_argument(
        "--repair-with-vision",
        action="store_true",
        help="During --prepare-only, use Vision only for profiles whose page evidence cannot be compiled deterministically.",
    )
    parser.add_argument("--rerun-promoted", action="store_true")
    parser.add_argument(
        "--continue-on-transient",
        action="store_true",
        help="Continue to later styles after a transient image-service failure.",
    )
    parser.add_argument("--max-validation-rounds", type=int, default=2)
    parser.add_argument("--max-profile-repairs", type=int, default=2)
    parser.add_argument("--min-validation-score", type=float, default=82)
    parser.add_argument("--min-page-score", type=float, default=74)
    parser.add_argument("--min-round-improvement", type=float, default=3)
    parser.add_argument("--max-role-regression", type=float, default=2)
    parser.add_argument("--min-text-accuracy", type=float, default=90)
    parser.add_argument("--image-retry-rounds", type=int, default=4)
    parser.add_argument("--image-retry-delay-secs", type=float, default=45)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    style_ids = args.style_id or discover_style_ids(
        args.styles_dir.resolve(),
        args.provenance_dir.resolve(),
        args.audit_json.resolve() if args.audit_json else None,
    )
    if args.limit > 0:
        style_ids = style_ids[: args.limit]
    report_path = args.migration_root.resolve() / "batch_report.json"
    existing = load_json(report_path) if report_path.is_file() else {"styles": {}}
    records = existing.setdefault("styles", {})
    paused = False
    for index, style_id in enumerate(style_ids, start=1):
        prior = records.get(style_id) if isinstance(records, dict) else None
        if (
            not args.rerun_promoted
            and isinstance(prior, dict)
            and prior.get("status") == "promoted"
        ):
            print(f"[{index}/{len(style_ids)}] {style_id}: skip promoted", flush=True)
            continue
        print(f"[{index}/{len(style_ids)}] {style_id}: migrate", flush=True)
        try:
            result = run_style(args, style_id)
        except Exception as exc:
            result = {"style_id": style_id, "status": "failed", "error": str(exc)}
        records[style_id] = result
        existing["updated_at"] = datetime.now(timezone.utc).isoformat()
        existing["selected_count"] = len(style_ids)
        atomic_json(report_path, existing)
        print(f"  -> {result['status']}", flush=True)
        if result["status"] == "blocked-transient" and not args.continue_on_transient:
            existing["paused"] = True
            existing["paused_at_style"] = style_id
            existing["pause_reason"] = (result.get("reasons") or ["transient failure"])[0]
            atomic_json(report_path, existing)
            paused = True
            print("  transient generation outage: batch paused for safe resume", flush=True)
            break
    counts: dict[str, int] = {}
    for value in records.values():
        status = str(value.get("status") if isinstance(value, dict) else "unknown")
        counts[status] = counts.get(status, 0) + 1
    existing["counts"] = counts
    if not paused:
        existing["paused"] = False
        existing.pop("paused_at_style", None)
        existing.pop("pause_reason", None)
    atomic_json(report_path, existing)
    print(json.dumps({"report": str(report_path), "counts": counts}, ensure_ascii=False))
    if paused:
        return 75
    return 1 if counts.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
