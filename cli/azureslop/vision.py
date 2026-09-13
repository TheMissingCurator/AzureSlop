"""Bounded RGBA transport and PNG/contact-sheet output, using only the stdlib."""

import base64
import binascii
import json
from pathlib import Path
import struct
import zlib

MAX_PIXELS = 1024 * 1024
MAX_STRIP_PIXELS = 24 * MAX_PIXELS


def decode_image(image):
    if not isinstance(image, dict) or image.get("format") != "rgba8" or image.get("encoding") != "base64":
        raise ValueError("Expected a base64 RGBA8 viewport image")
    width, height = image.get("width"), image.get("height")
    if (type(width) is not int or type(height) is not int or
            not 1 <= width <= 1024 or not 1 <= height <= 1024 or width * height > MAX_PIXELS):
        raise ValueError("Invalid viewport image dimensions")
    data = image.get("data")
    expected = width * height * 4
    if not isinstance(data, str) or len(data) != 4 * ((expected + 2) // 3):
        raise ValueError("Invalid viewport image payload length")
    try:
        pixels = base64.b64decode(data, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Invalid base64 viewport image") from exc
    if len(pixels) != expected:
        raise ValueError("Invalid RGBA pixel count")
    return width, height, pixels


def png_bytes(width, height, pixels):
    if (type(width) is not int or type(height) is not int or width < 1 or height < 1 or
            width * height > MAX_STRIP_PIXELS or len(pixels) != width * height * 4):
        raise ValueError("Invalid PNG dimensions or pixels")

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data +
                struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))

    stride = width * 4
    compressor = zlib.compressobj()
    compressed = []
    for offset in range(0, len(pixels), stride):
        compressed.append(compressor.compress(b"\0" + pixels[offset:offset + stride]))
    compressed.append(compressor.flush())
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", b"".join(compressed)) + chunk(b"IEND", b""))


def contact_sheet(images, columns):
    if not images or len(images) > 24 or type(columns) is not int or not 1 <= columns <= len(images):
        raise ValueError("Contact sheet requires 1..24 images and valid columns")
    width, height, _ = images[0]
    if any((w, h) != (width, height) for w, h, _ in images):
        raise ValueError("Contact sheet images must have matching dimensions")
    rows = (len(images) + columns - 1) // columns
    out_w, out_h = width * columns, height * rows
    if out_w * out_h > MAX_STRIP_PIXELS:
        raise ValueError("Contact sheet exceeds pixel limit")
    pixels = bytearray(out_w * out_h * 4)
    for index, (_, _, data) in enumerate(images):
        if len(data) != width * height * 4:
            raise ValueError("Invalid contact sheet pixel count")
        x, y = index % columns * width, index // columns * height
        for line in range(height):
            offset = ((y + line) * out_w + x) * 4
            pixels[offset:offset + width * 4] = data[line * width * 4:(line + 1) * width * 4]
    return png_bytes(out_w, out_h, pixels)


def write_new(path, data):
    # Exclusive creation: never overwrite an existing capture or follow a file symlink.
    with Path(path).open("xb") as output:
        output.write(data)


def export_result(result, directory):
    """Export one successful image job; replace the large payload with local paths."""
    if result.get("status") != "done" or not result.get("result", {}).get("ok"):
        return result
    value = result["result"]["value"]
    if not isinstance(value, dict) or "image" not in value:
        raise ValueError("--output requires a viewport_capture or preview_capture result")
    width, height, pixels = decode_image(value["image"])
    directory = Path(directory).absolute()
    directory.mkdir(parents=True, exist_ok=False)
    image_path = directory / "viewport.png"
    write_new(image_path, png_bytes(width, height, pixels))
    value = dict(value, image={k: v for k, v in value["image"].items() if k != "data"}, path=str(image_path))
    result = dict(result, result=dict(result["result"], value=value))
    write_new(directory / "result.json", json.dumps(result, indent=2).encode())
    return result
