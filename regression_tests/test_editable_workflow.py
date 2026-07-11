import json
import sys
from pathlib import Path

import pytest
from PIL import Image
from pptx import Presentation

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.editable_pptx.workflow import build_editable_output, discover_scene_files


def _png(path: Path, color: str) -> Path:
    Image.new("RGB", (160, 90), color).save(path)
    return path


def _write_scene(scene_dir: Path, number: int, *, declared_number=None, with_shape=False) -> Path:
    scene_dir.mkdir(parents=True, exist_ok=True)
    _png(scene_dir / f"plate-{number}.png", "#10152A")
    elements = [
        {
            "id": f"title_{number}",
            "type": "native_text",
            "bbox_px": [20, 20, 100, 20],
            "z_index": 20,
            "content": f"第{number}页",
            "style": {"color": "#FFFFFF", "font_size_pt": 24},
        }
    ]
    if with_shape:
        elements.append(
            {
                "id": f"shape_{number}",
                "type": "native_shape",
                "bbox_px": [10, 10, 120, 40],
                "z_index": 10,
                "style": {"shape": "rounded_rectangle", "fill": "#7752C8"},
            }
        )
    data = {
        "slide_number": declared_number if declared_number is not None else number,
        "canvas": {"width": 160, "height": 90},
        "clean_plate": f"plate-{number}.png",
        "elements": elements,
    }
    path = scene_dir / f"slide-{number:02d}.scene.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_discover_scenes_requires_every_requested_slide(tmp_path):
    scene_dir = tmp_path / "scenes"
    _write_scene(scene_dir, 1)
    with pytest.raises(ValueError, match="slide-02.scene.json"):
        discover_scene_files(scene_dir, [1, 2])


def test_build_editable_output_writes_named_deck_and_summary(tmp_path):
    scene_dir = tmp_path / "scenes"
    _write_scene(scene_dir, 1)
    _write_scene(scene_dir, 2, with_shape=True)
    result = build_editable_output(scene_dir, [2, 1], tmp_path / "session", "季度复盘")

    assert result.pptx_path.name == "季度复盘-editable.pptx"
    assert result.report_path.name == "editable-quality-report.json"
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["mode"] == "editable"
    assert report["slide_count"] == 2
    assert report["native_text_count"] == 2
    assert report["native_shape_count"] == 1
    assert report["status"] == "pass"
    assert len(Presentation(result.pptx_path).slides) == 2


def test_build_rejects_duplicate_declared_slide_numbers(tmp_path):
    scene_dir = tmp_path / "scenes"
    _write_scene(scene_dir, 1, declared_number=1)
    _write_scene(scene_dir, 2, declared_number=1)
    with pytest.raises(ValueError, match="slide_number 重复"):
        build_editable_output(scene_dir, [1, 2], tmp_path / "session", "duplicate")


def test_build_rejects_scene_number_that_does_not_match_filename(tmp_path):
    scene_dir = tmp_path / "scenes"
    _write_scene(scene_dir, 1, declared_number=2)
    with pytest.raises(ValueError, match="文件名"):
        build_editable_output(scene_dir, [1], tmp_path / "session", "mismatch")


def test_discover_rejects_empty_request(tmp_path):
    with pytest.raises(ValueError, match="至少需要一个"):
        discover_scene_files(tmp_path, [])
