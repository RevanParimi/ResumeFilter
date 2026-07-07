"""app/core/pdf.py — shared base64-PDF → text helper (route + ingest node)."""

import base64
import io

import pytest
from pypdf import PdfWriter

from app.core.pdf import pdf_b64_to_text


def _blank_pdf_b64() -> str:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return base64.b64encode(buf.getvalue()).decode()


def test_blank_pdf_yields_empty_text():
    assert pdf_b64_to_text(_blank_pdf_b64()).strip() == ""


def test_non_pdf_bytes_raise():
    junk_b64 = base64.b64encode(b"this is not a pdf").decode()
    with pytest.raises(Exception):
        pdf_b64_to_text(junk_b64)
