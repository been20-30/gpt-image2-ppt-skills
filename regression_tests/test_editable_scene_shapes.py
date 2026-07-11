import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.editable_pptx.scene import EditableScene


def _plate(path: Path) -> Path:
    Image.new("RGB", (1600, 900), "white").save(path)
    return path


def _scene(tmp_path: Path, elements):
    return {
        "slide_number": 1,
        "canvas": {"width": 1600, "height": 900},
        "clean_plate": str(_plate(tmp_path / "plate.png")),
        "elements": elements,
    }


def test_scene_accepts_native_shape_and_connector(tmp_path):
    scene = EditableScene.from_dict(
        _scene(
            tmp_path,
            [
                {
                    "id": "banner",
                    "type": "native_shape",
                    "bbox_px": [100, 100, 500, 120],
                    "z_index": 10,
                    "style": {
                        "shape": "rounded_rectangle",
                        "fill": "#FFF4C2",
                        "line": "#E8B932",
                        "fill_transparency": 12,
                        "rotation": -5,
                    },
                },
                {
                    "id": "flow",
                    "type": "connector",
                    "bbox_px": [600, 160, 300, 0],
                    "z_index": 11,
                    "style": {
                        "line": "#7752C8",
                        "line_width_pt": 2,
                        "end_arrow": True,
                    },
                },
            ],
        )
    )
    assert [item.type for item in scene.elements] == ["native_shape", "connector"]


@pytest.mark.parametrize(
    "element, message",
    [
        (
            {
                "id": "bad_shape",
                "type": "native_shape",
                "bbox_px": [10, 10, 100, 100],
                "style": {"shape": "cloud_blob"},
            },
            "不支持的 shape",
        ),
        (
            {
                "id": "bad_color",
                "type": "native_shape",
                "bbox_px": [10, 10, 100, 100],
                "style": {"shape": "rectangle", "fill": "yellow"},
            },
            "颜色",
        ),
        (
            {
                "id": "bad_connector",
                "type": "connector",
                "bbox_px": [10, 10, 0, 0],
                "style": {"line": "#000000"},
            },
            "connector",
        ),
    ],
)
def test_scene_rejects_invalid_shape_fields(tmp_path, element, message):
    with pytest.raises(ValueError, match=message):
        EditableScene.from_dict(_scene(tmp_path, [element]))
