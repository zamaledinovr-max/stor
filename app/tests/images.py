"""Helpers to build small in-memory images for upload tests."""

from __future__ import annotations

import io

from PIL import Image


def make_image_bytes(
    fmt: str = "PNG",
    size: tuple[int, int] = (32, 32),
    color: tuple[int, int, int] = (30, 90, 200),
) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()
