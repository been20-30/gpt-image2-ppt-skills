"""Mask normalization and pixel-locked image compositing."""

from __future__ import annotations

from PIL import Image, ImageChops


def _validate_sizes(original: Image.Image, edited: Image.Image, mask: Image.Image) -> None:
    if original.size != edited.size or original.size != mask.size:
        raise ValueError(
            f"图片与 mask 尺寸必须一致: original={original.size}, edited={edited.size}, mask={mask.size}"
        )


def composite_masked_edit(
    original: Image.Image,
    edited: Image.Image,
    internal_mask: Image.Image,
) -> Image.Image:
    """Use edited pixels only where the internal mask is white."""
    _validate_sizes(original, edited, internal_mask)
    base = original.convert("RGBA") if original.mode == "RGBA" else original.convert("RGB")
    candidate = edited.convert(base.mode)
    return Image.composite(candidate, base, internal_mask.convert("L"))


def make_api_edit_mask(internal_mask: Image.Image) -> Image.Image:
    """Convert 0=preserve/255=replace into an OpenAI-style alpha mask."""
    replace = internal_mask.convert("L")
    alpha = ImageChops.invert(replace)
    api_mask = Image.new("RGBA", replace.size, (255, 255, 255, 255))
    api_mask.putalpha(alpha)
    return api_mask


def changed_outside_mask(
    original: Image.Image,
    result: Image.Image,
    internal_mask: Image.Image,
) -> int:
    """Count changed pixels in the preserve region."""
    _validate_sizes(original, result, internal_mask)
    left = original.convert("RGBA")
    right = result.convert("RGBA")
    difference = ImageChops.difference(left, right).convert("L")
    preserve = ImageChops.invert(internal_mask.convert("L"))
    outside_difference = ImageChops.multiply(difference, preserve)
    return sum(1 for value in outside_difference.getdata() if value != 0)
