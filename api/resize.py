from __future__ import annotations

import json
import zipfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from io import BytesIO
from pathlib import Path

from PIL import UnidentifiedImageError

from resize_core import (
    ALLOWED_EXTENSIONS,
    ProcessError,
    build_summary,
    parse_uploaded_images,
    resize_image,
    safe_filename,
    unique_name,
)


MAX_UPLOAD_BYTES = 4 * 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        if content_length <= 0:
            self.send_json_error("Tidak ada gambar yang dikirim.", HTTPStatus.BAD_REQUEST)
            return

        if content_length > MAX_UPLOAD_BYTES:
            self.send_json_error(
                "Upload terlalu besar untuk Vercel. Maksimal total 4 MB per proses.",
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )
            return

        try:
            body = self.rfile.read(content_length)
            file_fields = parse_uploaded_images(self.headers.get("Content-Type", ""), body)
        except ValueError as exc:
            self.send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return

        processed = []
        errors: list[ProcessError] = []
        used_names: set[str] = set()

        for index, field in enumerate(file_fields, start=1):
            suffix = Path(field.filename).suffix.lower()

            if suffix not in ALLOWED_EXTENSIONS:
                errors.append(ProcessError(field.filename, "Format harus JPG, JPEG, atau PNG."))
                continue

            try:
                if not field.data:
                    raise ValueError("File kosong.")

                safe_name = safe_filename(field.filename, f"gambar-{index}")
                output_name = unique_name(safe_name, used_names)
                processed.append(resize_image(field.data, output_name))
            except UnidentifiedImageError:
                errors.append(ProcessError(field.filename, "File bukan gambar yang valid."))
            except Exception as exc:
                errors.append(ProcessError(field.filename, str(exc)))

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
        if len(payload) > MAX_RESPONSE_BYTES:
            self.send_json_error(
                "Hasil ZIP terlalu besar untuk Vercel. Coba proses lebih sedikit gambar.",
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Content-Disposition", 'attachment; filename="hasil-resize-gambar.zip"')
        self.send_header("X-Processed-Count", str(len(processed)))
        self.send_header("X-Failed-Count", str(len(errors)))
        self.end_headers()
        self.wfile.write(payload)

    def send_json_error(self, message: str, status: HTTPStatus) -> None:
        payload = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
