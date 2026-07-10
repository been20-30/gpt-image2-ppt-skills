"""Strict scene model for the editable PPTX POC."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SUPPORTED_TYPES = {"native_text", "image_layer"}


@dataclass(frozen=True)
class SceneElement:
    id: str
    type: str
    bbox_px: tuple[float, float, float, float]
    z_index: int
    content: str = ""
    style: dict[str, Any] = field(default_factory=dict)
    asset: Path | None = None


@dataclass(frozen=True)
class EditableScene:
    slide_number: int
    canvas_width: int
    canvas_height: int
    clean_plate: Path
    elements: tuple[SceneElement, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EditableScene":
        canvas = data.get("canvas") or {}
        width = int(canvas.get("width") or 0)
        height = int(canvas.get("height") or 0)
        if width <= 0 or height <= 0:
            raise ValueError("canvas width/height 必须为正数")

        clean_plate = Path(str(data.get("clean_plate") or ""))
        if not clean_plate.is_file():
            raise ValueError(f"clean_plate 文件不存在: {clean_plate}")

        seen: set[str] = set()
        elements: list[SceneElement] = []
        for raw in data.get("elements") or []:
            element_id = str(raw.get("id") or "").strip()
            if not element_id:
                raise ValueError("元素缺少 id")
            if element_id in seen:
                raise ValueError(f"元素 id 重复: {element_id}")
            seen.add(element_id)

            element_type = str(raw.get("type") or "")
            if element_type not in SUPPORTED_TYPES:
                raise ValueError(f"不支持的元素类型: {element_type}")
            bbox_raw = raw.get("bbox_px")
            if not isinstance(bbox_raw, list) or len(bbox_raw) != 4:
                raise ValueError(f"{element_id} bbox_px 必须是 [x, y, w, h]")
            bbox = tuple(float(value) for value in bbox_raw)
            x, y, box_width, box_height = bbox
            if (
                x < 0
                or y < 0
                or box_width <= 0
                or box_height <= 0
                or x + box_width > width
                or y + box_height > height
            ):
                raise ValueError(f"{element_id} bbox 超出 canvas: {bbox}")

            asset = None
            if element_type == "image_layer":
                asset = Path(str(raw.get("asset") or ""))
                if not asset.is_file():
                    raise ValueError(f"{element_id} asset 文件不存在: {asset}")

            content = str(raw.get("content") or "")
            if element_type == "native_text" and not content:
                raise ValueError(f"{element_id} native_text 缺少 content")

            elements.append(
                SceneElement(
                    id=element_id,
                    type=element_type,
                    bbox_px=bbox,
                    z_index=int(raw.get("z_index") or 0),
                    content=content,
                    style=dict(raw.get("style") or {}),
                    asset=asset,
                )
            )

        return cls(
            slide_number=int(data.get("slide_number") or 1),
            canvas_width=width,
            canvas_height=height,
            clean_plate=clean_plate,
            elements=tuple(elements),
        )
