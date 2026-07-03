from __future__ import annotations

import re
from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import default
from io import BytesIO
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageOps


MAX_SIZE_KB = 250
MAX_SIZE_BYTES = MAX_SIZE_KB * 1024
MAX_DIMENSION = (2000, 2000)
MIN_QUALITY = 20
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


@dataclass
class ProcessedImage:
    filename: str
    data: bytes
    original_kb: float
    result_kb: float
    quality: int
    size: tuple[int, int]


@dataclass
class ProcessError:
    filename: str
    message: str


@dataclass
class UploadedFile:
    filename: str
    data: bytes


def safe_filename(filename: str, fallback: str = "gambar") -> str:
    stem = Path(filename).stem.strip()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-_")
    return stem or fallback


def unique_name(name: str, used: set[str]) -> str:
    candidate = f"{name}.jpg"
    counter = 2

    while candidate.lower() in used:
        candidate = f"{name}-{counter}.jpg"
        counter += 1

    used.add(candidate.lower())
    return candidate


def normalize_image(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)

    if image.mode in ("RGBA", "LA") or (
        image.mode == "P" and "transparency" in image.info
    ):
        background = Image.new("RGB", image.size, "white")
        rgba = image.convert("RGBA")
        background.paste(rgba, mask=rgba.split()[-1])
        return background

    return image.convert("RGB")


def resize_image(file_bytes: bytes, original_filename: str) -> ProcessedImage:
    with Image.open(BytesIO(file_bytes)) as source:
        image = normalize_image(source)
        image.thumbnail(MAX_DIMENSION, Image.Resampling.LANCZOS)

        best_data = b""
        best_quality = 95

        for quality in range(95, MIN_QUALITY - 1, -5):
            buffer = BytesIO()
            image.save(
                buffer,
                format="JPEG",
                quality=quality,
                optimize=True,
                progressive=True,
            )
            result = buffer.getvalue()
            best_data = result
            best_quality = quality

            if len(result) <= MAX_SIZE_BYTES:
                break

        if len(best_data) > MAX_SIZE_BYTES:
            raise ValueError(
                f"Hasil masih {len(best_data) / 1024:.1f} KB pada quality {best_quality}."
            )

        return ProcessedImage(
            filename=original_filename,
            data=best_data,
            original_kb=len(file_bytes) / 1024,
            result_kb=len(best_data) / 1024,
            quality=best_quality,
            size=image.size,
        )


def build_summary(processed: Iterable[ProcessedImage], errors: Iterable[ProcessError]) -> str:
    lines = [
        "Ringkasan resize gambar",
        f"Target ukuran: maksimal {MAX_SIZE_KB} KB",
        f"Dimensi maksimal: {MAX_DIMENSION[0]} x {MAX_DIMENSION[1]} px",
        "",
    ]

    processed_list = list(processed)
    error_list = list(errors)

    if processed_list:
        lines.append("Berhasil:")
        for item in processed_list:
            width, height = item.size
            lines.append(
                "- "
                f"{item.filename}: {item.original_kb:.1f} KB -> {item.result_kb:.1f} KB, "
                f"{width}x{height}px, quality {item.quality}"
            )
        lines.append("")

    if error_list:
        lines.append("Gagal:")
        for item in error_list:
            lines.append(f"- {item.filename}: {item.message}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def parse_uploaded_images(content_type: str, body: bytes) -> list[UploadedFile]:
    uploads, _ = parse_multipart_form(content_type, body)
    return uploads


def parse_multipart_form(
    content_type: str,
    body: bytes,
) -> tuple[list[UploadedFile], dict[str, str]]:
    if not content_type.lower().startswith("multipart/form-data"):
        raise ValueError("Form upload tidak valid.")

    headers = (
        f"Content-Type: {content_type}\r\n"
        "MIME-Version: 1.0\r\n"
        "\r\n"
    ).encode("utf-8")
    message = BytesParser(policy=default).parsebytes(headers + body)

    if not message.is_multipart():
        raise ValueError("Form upload tidak berisi gambar.")

    uploads: list[UploadedFile] = []
    fields: dict[str, str] = {}
    for part in message.iter_parts():
        if part.get_content_disposition() != "form-data":
            continue

        field_name = part.get_param("name", header="content-disposition")
        if not field_name:
            continue

        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""

        if field_name == "images" and filename:
            uploads.append(UploadedFile(filename=filename, data=payload))
        elif not filename:
            fields[field_name] = payload.decode("utf-8", errors="replace")

    return uploads, fields
