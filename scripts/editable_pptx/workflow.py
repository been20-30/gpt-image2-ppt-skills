"""Build opt-in editable PPTX decks from per-slide scene manifests."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .renderer import render_editable_deck
from .scene import EditableScene


@dataclass(frozen=True)
class EditableBuildResult:
    pptx_path: Path
    report_path: Path
    scene_files: tuple[Path, ...]


def discover_scene_files(scene_dir: Path | str, slide_numbers: Iterable[int]) -> tuple[Path, ...]:
    directory = Path(scene_dir)
    numbers = sorted({int(number) for number in slide_numbers})
    if not numbers:
        raise ValueError("可编辑模式至少需要一个 slide scene")
    if not directory.is_dir():
        raise ValueError(f"editable scene 目录不存在: {directory}")
    files: list[Path] = []
    missing: list[str] = []
    for number in numbers:
        path = directory / f"slide-{number:02d}.scene.json"
        if path.is_file():
            files.append(path)
        else:
            missing.append(path.name)
    if missing:
        raise ValueError(f"可编辑模式缺少 scene: {', '.join(missing)}（目录: {directory}）")
    return tuple(files)


def _resolve_scene_paths(data: dict, base_dir: Path) -> dict:
    resolved = copy.deepcopy(data)
    for key in ("clean_plate", "visual_master", "repair_mask"):
        value = resolved.get(key)
        if value and not Path(str(value)).is_absolute():
            resolved[key] = str((base_dir / str(value)).resolve())
    for element in resolved.get("elements") or []:
        asset = element.get("asset")
        if asset and not Path(str(asset)).is_absolute():
            element["asset"] = str((base_dir / str(asset)).resolve())
    return resolved


def load_scene_file(path: Path | str) -> EditableScene:
    scene_path = Path(path).resolve()
    data = json.loads(scene_path.read_text(encoding="utf-8"))
    return EditableScene.from_dict(_resolve_scene_paths(data, scene_path.parent))


def inventory_scenes(scenes: Iterable[EditableScene]) -> dict[str, int]:
    counts = {
        "native_text_count": 0,
        "image_layer_count": 0,
        "native_shape_count": 0,
        "connector_count": 0,
    }
    for scene in scenes:
        for element in scene.elements:
            key = f"{element.type}_count"
            if key in counts:
                counts[key] += 1
    return counts


def _safe_title(title: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff\-]+", "_", title)[:60] or "deck"


def build_editable_output(
    scene_dir: Path | str,
    slide_numbers: Iterable[int],
    output_dir: Path | str,
    title: str,
) -> EditableBuildResult:
    scene_files = discover_scene_files(scene_dir, slide_numbers)
    scenes = tuple(load_scene_file(path) for path in scene_files)
    declared = [scene.slide_number for scene in scenes]
    if len(declared) != len(set(declared)):
        raise ValueError(f"editable scene 的 slide_number 重复: {declared}")

    for path, scene in zip(scene_files, scenes):
        match = re.fullmatch(r"slide-(\d+)\.scene\.json", path.name)
        expected_number = int(match.group(1)) if match else None
        if expected_number != scene.slide_number:
            raise ValueError(
                f"editable scene 文件名与 slide_number 不一致: {path.name} -> {scene.slide_number}"
            )

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    pptx_path = output / f"{_safe_title(title)}-editable.pptx"
    render_editable_deck(scenes, pptx_path)

    report = {
        "status": "pass",
        "mode": "editable",
        "slide_count": len(scenes),
        **inventory_scenes(scenes),
        "picture_count": len(scenes) + sum(
            1 for scene in scenes for element in scene.elements if element.type == "image_layer"
        ),
        "scene_files": [str(path) for path in scene_files],
        "pptx": str(pptx_path),
    }
    report_path = output / "editable-quality-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return EditableBuildResult(pptx_path=pptx_path, report_path=report_path, scene_files=scene_files)
