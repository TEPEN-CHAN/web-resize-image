from __future__ import annotations

import html
import json
import mimetypes
import re
import sys
import zipfile
from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageOps, UnidentifiedImageError


# ================== KONFIGURASI ==================
MAX_SIZE_KB = 250
MAX_SIZE_BYTES = MAX_SIZE_KB * 1024
MAX_DIMENSION = (2000, 2000)
MIN_QUALITY = 20
DEFAULT_PORT = 8000
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
INDEX_FILE = BASE_DIR / "index.html"


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


def write_console(message: str) -> None:
    if sys.stdout:
        print(message)


def normalize_image(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)

    if image.mode in ("RGBA", "LA") or (
        image.mode == "P" and "transparency" in image.info
    ):
        background = Image.new("RGB", image.size, "white")
        background.paste(image.convert("RGBA"), mask=image.convert("RGBA").split()[-1])
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
    for part in message.iter_parts():
        if part.get_content_disposition() != "form-data":
            continue

        if part.get_param("name", header="content-disposition") != "images":
            continue

        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""

        if filename:
            uploads.append(UploadedFile(filename=filename, data=payload))

    return uploads


class ResizeHandler(SimpleHTTPRequestHandler):
    server_version = "ResizeImageWeb/1.0"

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self.serve_file(INDEX_FILE, "text/html; charset=utf-8")
            return

        if self.path.startswith("/static/"):
            relative = self.path.removeprefix("/static/").split("?", 1)[0]
            target = (STATIC_DIR / relative).resolve()

            if STATIC_DIR.resolve() not in target.parents and target != STATIC_DIR.resolve():
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self.serve_file(target, content_type)
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path not in ("/resize", "/api/resize"):
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_length = int(self.headers.get("Content-Length", "0") or "0")
        if content_length <= 0:
            self.send_json_error("Tidak ada gambar yang dikirim.", HTTPStatus.BAD_REQUEST)
            return

        if content_length > MAX_UPLOAD_BYTES:
            self.send_json_error(
                "Ukuran upload terlalu besar. Maksimal total 100 MB.",
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )
            return

        try:
            body = self.rfile.read(content_length)
            file_fields = parse_uploaded_images(self.headers.get("Content-Type", ""), body)
        except ValueError as exc:
            self.send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return

        processed: list[ProcessedImage] = []
        errors: list[ProcessError] = []
        used_names: set[str] = set()

        for index, field in enumerate(file_fields, start=1):
            if not field.filename:
                continue

            original_filename = field.filename
            suffix = Path(original_filename).suffix.lower()

            if suffix not in ALLOWED_EXTENSIONS:
                errors.append(
                    ProcessError(original_filename, "Format harus JPG, JPEG, atau PNG.")
                )
                continue

            try:
                file_bytes = field.data
                if not file_bytes:
                    raise ValueError("File kosong.")

                safe_name = safe_filename(original_filename, f"gambar-{index}")
                output_name = unique_name(safe_name, used_names)
                item = resize_image(file_bytes, output_name)
                processed.append(item)
            except UnidentifiedImageError:
                errors.append(ProcessError(original_filename, "File bukan gambar yang valid."))
            except Exception as exc:
                errors.append(ProcessError(original_filename, str(exc)))

        if not processed:
            message = "Tidak ada gambar yang berhasil diproses."
            if errors:
                message += " " + " ".join(
                    f"{error.filename}: {error.message}" for error in errors[:3]
                )
            self.send_json_error(message, HTTPStatus.BAD_REQUEST)
            return

        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in processed:
                archive.writestr(item.filename, item.data)

            archive.writestr("ringkasan_proses.txt", build_summary(processed, errors))

        payload = zip_buffer.getvalue()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header(
            "Content-Disposition",
            'attachment; filename="hasil-resize-gambar.zip"',
        )
        self.send_header("X-Processed-Count", str(len(processed)))
        self.send_header("X-Failed-Count", str(len(errors)))
        self.end_headers()
        self.wfile.write(payload)

    def serve_file(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json_error(self, message: str, status: HTTPStatus) -> None:
        payload = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: object) -> None:
        if not sys.stderr:
            return

        clean_args = tuple(html.escape(str(arg)) for arg in args)
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % clean_args))


def run() -> None:
    port = DEFAULT_PORT

    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Port tidak valid: {sys.argv[1]}")
            sys.exit(2)

    address = ("127.0.0.1", port)
    httpd = ThreadingHTTPServer(address, ResizeHandler)
    write_console(f"Web resize gambar berjalan di http://{address[0]}:{address[1]}")
    write_console("Tekan Ctrl+C untuk berhenti.")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        write_console("\nServer dihentikan.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run()
