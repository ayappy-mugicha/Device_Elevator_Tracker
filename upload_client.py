"""Optional HTTP upload client for hard-example samples (disabled by default)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib import error, request


@dataclass
class UploadResult:
    attempted: bool
    success: bool
    detail: str
    status_code: Optional[int] = None


class UploadClient:
    """POST multipart-ish JSON+file when enabled. Keeps local files on failure."""

    def __init__(
        self,
        enabled: bool = False,
        url: str = "",
        timeout_sec: float = 30.0,
    ) -> None:
        self.enabled = bool(enabled)
        self.url = (url or "").strip()
        self.timeout_sec = float(timeout_sec)

    def maybe_upload(self, meta_path: Path, image_path: Path) -> UploadResult:
        if not self.enabled:
            return UploadResult(False, False, "upload_disabled")
        if not self.url:
            return UploadResult(False, False, "upload_url_empty")
        if not meta_path.exists() or not image_path.exists():
            return UploadResult(True, False, "missing_files")

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return UploadResult(True, False, f"meta_read_error:{exc}")

        boundary = "----ElevatorHardExampleBoundary"
        body = _build_multipart(boundary, meta, image_path)
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        }
        req = request.Request(self.url, data=body, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=self.timeout_sec) as resp:
                code = getattr(resp, "status", None) or resp.getcode()
                if 200 <= int(code) < 300:
                    return UploadResult(True, True, "ok", int(code))
                return UploadResult(True, False, f"http_{code}", int(code))
        except error.HTTPError as exc:
            return UploadResult(True, False, f"http_{exc.code}", int(exc.code))
        except error.URLError as exc:
            return UploadResult(True, False, f"url_error:{exc.reason}")
        except TimeoutError:
            return UploadResult(True, False, "timeout")


def _build_multipart(boundary: str, meta: dict, image_path: Path) -> bytes:
    chunks = []
    meta_bytes = json.dumps(meta, ensure_ascii=False).encode("utf-8")
    chunks.append(f"--{boundary}\r\n".encode())
    chunks.append(b'Content-Disposition: form-data; name="meta"\r\n')
    chunks.append(b"Content-Type: application/json\r\n\r\n")
    chunks.append(meta_bytes)
    chunks.append(b"\r\n")

    image_bytes = image_path.read_bytes()
    filename = image_path.name
    chunks.append(f"--{boundary}\r\n".encode())
    chunks.append(
        f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'.encode()
    )
    chunks.append(b"Content-Type: image/jpeg\r\n\r\n")
    chunks.append(image_bytes)
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks)
