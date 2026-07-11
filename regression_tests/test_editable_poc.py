import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.editable_pptx.poc import run_poc


def _make_synthetic_poc(tmp_path: Path):
    visual_master = Image.new("RGB", (160, 90), (12, 18, 42))
    draw = ImageDraw.Draw(visual_master)
    draw.rectangle((12, 18, 92, 35), fill=(245, 245, 245))
    draw.rectangle((22, 45, 78, 55), fill=(160, 170, 190))
    master_path = tmp_path / "master.png"
    visual_master.save(master_path)

    edited = visual_master.copy()
    edit_draw = ImageDraw.Draw(edited)
    edit_draw.rectangle((10, 16, 96, 38), fill=(12, 18, 42))
    edit_draw.rectangle((20, 43, 82, 58), fill=(12, 18, 42))
    edited_path = tmp_path / "edited.png"
    edited.save(edited_path)

    scene = {
        "slide_number": 1,
        "visual_master": str(master_path),
        "canvas": {"width": 160, "height": 90},
        "repair_regions": [[10, 16, 86, 22], [20, 43, 62, 15]],
        "elements": [
            {
                "id": "title",
                "type": "native_text",
                "bbox_px": [12, 18, 80, 17],
                "z_index": 20,
                "content": "年度战略复盘",
                "style": {"font_size_pt": 24, "font_weight": 700, "color": "#FFFFFF"},
            },
            {
                "id": "subtitle",
                "type": "native_text",
                "bbox_px": [22, 44, 56, 12],
                "z_index": 21,
                "content": "AI 驱动的数字化未来",
                "style": {"font_size_pt": 14, "font_weight": 400, "color": "#A0AABE"},
            },
        ],
    }
    return scene, edited_path


def test_offline_poc_emits_pptx_and_report(tmp_path):
    scene, edited_candidate = _make_synthetic_poc(tmp_path)

    result = run_poc(scene, edited_candidate, tmp_path / "out")

    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert result.pptx_path.exists()
    assert result.clean_plate_path.exists()
    assert report["outside_mask_changed_pixels"] == 0
    assert report["native_text_count"] == 2
    assert report["picture_count"] == 1
    assert report["status"] == "pass"


def test_offline_poc_fails_report_when_candidate_size_differs(tmp_path):
    scene, _ = _make_synthetic_poc(tmp_path)
    wrong = tmp_path / "wrong.png"
    Image.new("RGB", (80, 90), (0, 0, 0)).save(wrong)

    try:
        run_poc(scene, wrong, tmp_path / "out")
    except ValueError as exc:
        assert "尺寸" in str(exc)
    else:
        raise AssertionError("mismatched edit candidate should fail")


def test_offline_poc_accepts_a_pixel_level_repair_mask(tmp_path):
    scene, edited_candidate = _make_synthetic_poc(tmp_path)
    mask = Image.new("L", (160, 90), 0)
    mask.putpixel((25, 25), 128)
    mask_path = tmp_path / "glyph-mask.png"
    mask.save(mask_path)
    scene.pop("repair_regions")
    scene["repair_mask"] = str(mask_path)

    result = run_poc(scene, edited_candidate, tmp_path / "out")

    saved_mask = Image.open(result.internal_mask_path).convert("L")
    assert saved_mask.getpixel((25, 25)) == 128
    assert saved_mask.getbbox() == (25, 25, 26, 26)
