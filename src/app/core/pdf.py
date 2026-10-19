"""Bounded, disposable PDF parsing shared by resumes and verification."""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys

from app.core.config import Settings, get_settings


def _write_input(pipe, data):
    try:
        pipe.write(data)
        pipe.flush()
    except OSError:
        # A refused/killed worker may close stdin before accepting all bytes.
        pass
    finally:
        pipe.close()


def _parse(b64: str, *, strict: bool, settings: Settings | None,
           max_pages: int | None = None) -> tuple[str, int, dict]:
    settings = settings or get_settings()
    if len(b64) > settings.max_pdf_b64_chars:
        raise ValueError("pdf_input_limit")
    data = base64.b64decode(b64, validate=True)
    if not data.startswith(b"%PDF-"):
        raise ValueError("invalid_pdf_header")
    if max_pages is not None and max_pages < 1:
        raise ValueError("pdf_page_limit")
    limits = dict(pages=min(settings.pdf_max_pages, max_pages or settings.pdf_max_pages),
                  work=settings.pdf_max_work_units, depth=settings.pdf_max_depth,
                  decoded=settings.pdf_max_decoded_bytes, output=settings.pdf_max_output_chars,
                  memory=settings.pdf_worker_memory_mb * 1024 * 1024,
                  input=len(data), strict=strict)
    # Adjacent installed worker: independent of cwd/PYTHONPATH. -I prevents
    # user site/customization imports in the parser interpreter.
    command = [sys.executable, "-I", str(Path(__file__).with_name("pdf_worker.py")),
               json.dumps(limits)]
    # JSON escapes a non-BMP character as two six-byte surrogate escapes.
    cap = 12 * settings.pdf_max_output_chars + 1024
    # Concurrent bounded pipe IO avoids deadlock and keeps document text off
    # disk. Even unexpected stdout is read only up to the protocol limit.
    with ThreadPoolExecutor(max_workers=2) as io_pool:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={key: value for key, value in os.environ.items()
                 if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "LANG", "LC_ALL"}},
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        incoming = outgoing = None
        try:
            incoming = io_pool.submit(_write_input, process.stdin, data)
            outgoing = io_pool.submit(process.stdout.read, cap + 1)
            try:
                process.wait(timeout=settings.pdf_parse_timeout_seconds)
            except subprocess.TimeoutExpired:
                raise ValueError("pdf_timeout") from None
            if process.returncode != 0:
                raise ValueError("pdf_parse_failed")
            raw = outgoing.result()
            if len(raw) > cap:
                raise ValueError("pdf_output_limit")
            result = json.loads(raw)
            if "error" in result:
                raise ValueError(result["error"])
            return result["text"], result["pages"], result["meta"]
        finally:
            # Includes timeout, interruption, malformed output and memory death.
            if process.poll() is None:
                process.kill()
            process.wait()
            try:
                if incoming is not None:
                    incoming.result()
                if outgoing is not None:
                    outgoing.result()
            finally:
                process.stdin.close()
                process.stdout.close()


def pdf_b64_to_text(b64: str, *, settings: Settings | None = None) -> str:
    return _parse(b64, strict=True, settings=settings)[0]

def pdf_b64_to_document(b64: str, *, settings: Settings | None = None,
                        max_pages: int | None = None) -> tuple[str, int, dict]:
    """Retain verification's lenient reader, blank pages and normalized metadata."""
    return _parse(b64, strict=False, settings=settings, max_pages=max_pages)
