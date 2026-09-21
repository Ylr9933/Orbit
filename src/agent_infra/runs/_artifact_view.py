"""Bounded, lossless reading views over immutable artifact bytes (no storage changes)."""

import base64
import codecs
import mimetypes
from pathlib import PurePosixPath
from typing import Any, BinaryIO
from urllib.parse import quote, urlencode

from agent_infra.records.api import BlobRef

DEFAULT_PAGE_BYTES = 16 * 1024
MAX_PAGE_BYTES = 64 * 1024
DOWNLOAD_LIMIT_BYTES = 16 * 1024**2
_TEXT_SUFFIXES = {".jsonl", ".ndjson", ".log", ".yaml", ".yml", ".toml", ".md", ".csv"}
_BINARY_SUFFIXES = {".bin", ".pt", ".pth", ".ckpt", ".safetensors", ".npy", ".npz", ".pkl"}


def validate_view(format: str, offset: int, limit: int) -> None:
    if format not in {"auto", "text", "base64", "metadata"}:
        raise ValueError("format must be auto, text, base64 or metadata")
    if type(offset) is not int or offset < 0:
        raise ValueError("offset must be a non-negative byte offset")
    if type(limit) is not int or not 4 <= limit <= MAX_PAGE_BYTES:
        raise ValueError(f"limit must be 4–{MAX_PAGE_BYTES} bytes")


def _text(data: bytes, *, final: bool) -> str:
    text = codecs.getincrementaldecoder("utf-8")().decode(data, final=final)
    if any(ord(c) < 32 and c not in "\t\n\r\f" for c in text):
        raise ValueError("content contains binary control characters")
    return text


def _kind(path: str, media_type: str, sample: bytes, *, final: bool) -> tuple[str, str]:
    # Only known raster signatures become images; SVG is readable source, not rendered markup.
    if sample.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image", "image/png"
    if sample.startswith(b"\xff\xd8\xff"):
        return "image", "image/jpeg"
    if sample.startswith((b"GIF87a", b"GIF89a")):
        return "image", "image/gif"
    if sample.startswith(b"RIFF") and sample[8:12] == b"WEBP":
        return "image", "image/webp"
    suffix = PurePosixPath(path).suffix.lower()
    guessed, compression = mimetypes.guess_type(path)
    mime = guessed or media_type
    if compression or suffix in _BINARY_SUFFIXES:
        return "binary", "application/octet-stream"
    textual = (
        mime.startswith("text/")
        or mime in {"application/json", "application/xml", "image/svg+xml"}
        or mime.endswith(("+json", "+xml"))
        or suffix in _TEXT_SUFFIXES
    )
    if not textual and mime != "application/octet-stream":
        return "binary", mime
    try:
        _text(sample, final=final)
    except (UnicodeDecodeError, ValueError):
        return "binary", mime
    return "text", mime if textual else "text/plain"


def artifact_view(
    file: BinaryIO,
    ref: BlobRef,
    *,
    run_id: str,
    artifact_id: str,
    member: str,
    format: str,
    offset: int,
    limit: int,
) -> dict[str, Any]:
    validate_view(format, offset, limit)
    if offset > ref.size_bytes:
        raise ValueError("offset exceeds file size")
    if file.seek(0, 2) != ref.size_bytes:
        raise ValueError("stored artifact size mismatch")
    file.seek(0)
    sample = file.read(min(4096, ref.size_bytes))
    kind, mime = _kind(member, ref.media_type, sample, final=len(sample) == ref.size_bytes)
    download_path = (
        f"/api/v1/runs/{quote(run_id, safe='')}/artifacts/{quote(artifact_id, safe='')}?"
        + urlencode({"member": member})
    )
    result: dict[str, Any] = {
        "run_id": run_id,
        "artifact_id": artifact_id,
        "path": member,
        "size_bytes": ref.size_bytes,
        "digest": ref.digest,
        "media_type": mime,
        "kind": kind,
        "format": "metadata",
        "download": {
            "controller_path": download_path,
            "requires_auth": True,
            "response_encoding": "base64",
            "available": ref.size_bytes <= DOWNLOAD_LIMIT_BYTES,
            "max_bytes": DOWNLOAD_LIMIT_BYTES,
        },
    }
    if format == "metadata" or (format == "auto" and kind != "text"):
        return result
    file.seek(offset)
    data = file.read(min(limit, ref.size_bytes - offset))
    selected = "text" if format == "auto" else format
    if selected == "text":
        try:
            text = _text(data, final=offset + len(data) == ref.size_bytes)
        except (UnicodeDecodeError, ValueError) as error:
            if format == "text":
                raise ValueError(
                    "not a UTF-8 text page; use next_offset for character boundaries, "
                    "or format=base64 for original bytes"
                ) from error
            result.update(reason="page is not UTF-8 text; request format=base64", kind="binary")
            return result
        # The incremental decoder withholds an incomplete trailing character; retry those bytes.
        data = text.encode("utf-8")
        result["text"] = text
    else:
        result["content_base64"] = base64.b64encode(data).decode("ascii")
    end = offset + len(data)
    result.update(
        format=selected,
        offset=offset,
        bytes_read=len(data),
        next_offset=end if end < ref.size_bytes else None,
        eof=end == ref.size_bytes,
        truncated=end < ref.size_bytes,
    )
    return result
