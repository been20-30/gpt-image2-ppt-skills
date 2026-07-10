import base64
import sys
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.editable_pptx.provider import OpenAIImageProvider


def _png_bytes() -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    Image.new("RGB", (2, 2), (12, 34, 56)).save(buffer, format="PNG")
    return buffer.getvalue()


PNG_BYTES = _png_bytes()


class FakeImages:
    def __init__(self, generate_bytes: bytes = PNG_BYTES, edit_bytes: bytes = PNG_BYTES):
        self.generate_bytes = generate_bytes
        self.edit_bytes = edit_bytes
        self.generate_kwargs = None
        self.edit_kwargs = None

    def generate(self, **kwargs):
        self.generate_kwargs = kwargs
        return SimpleNamespace(
            data=[SimpleNamespace(b64_json=base64.b64encode(self.generate_bytes).decode("ascii"))]
        )

    def edit(self, **kwargs):
        self.edit_kwargs = kwargs
        return SimpleNamespace(
            data=[SimpleNamespace(b64_json=base64.b64encode(self.edit_bytes).decode("ascii"))]
        )


class FakeClient:
    def __init__(self):
        self.images = FakeImages()


def _write_png(path: Path, mode: str = "RGB") -> Path:
    color = (255, 255, 255, 255) if mode == "RGBA" else (255, 255, 255)
    Image.new(mode, (2, 2), color).save(path)
    return path


def test_generate_writes_b64_png(tmp_path):
    client = FakeClient()
    provider = OpenAIImageProvider(client, "gpt-image-2", "high")

    output = provider.generate("完整 PPT 封面", tmp_path / "generated.png", "1024x1024")

    assert output.read_bytes() == PNG_BYTES
    assert client.images.generate_kwargs == {
        "model": "gpt-image-2",
        "prompt": "完整 PPT 封面",
        "size": "1024x1024",
        "quality": "high",
    }


def test_edit_sends_image_and_mask(tmp_path):
    image_path = _write_png(tmp_path / "image.png")
    mask_path = _write_png(tmp_path / "mask.png", mode="RGBA")
    client = FakeClient()
    provider = OpenAIImageProvider(client, "gpt-image-2", "high")

    output = provider.edit(
        image_path,
        mask_path,
        "只修复文字区域",
        tmp_path / "edited.png",
        "1024x1024",
    )

    assert output.read_bytes() == PNG_BYTES
    kwargs = client.images.edit_kwargs
    assert kwargs["model"] == "gpt-image-2"
    assert kwargs["prompt"] == "只修复文字区域"
    assert kwargs["size"] == "1024x1024"
    assert kwargs["quality"] == "high"
    assert kwargs["image"].closed is True
    assert kwargs["mask"].closed is True


def test_empty_image_response_is_rejected(tmp_path):
    client = FakeClient()
    client.images.generate = lambda **kwargs: SimpleNamespace(data=[])
    provider = OpenAIImageProvider(client, "gpt-image-2", "high")

    try:
        provider.generate("test", tmp_path / "generated.png", "1024x1024")
    except RuntimeError as exc:
        assert "没有返回图片数据" in str(exc)
    else:
        raise AssertionError("empty image response should fail")
