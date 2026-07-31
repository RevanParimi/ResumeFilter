"""S7.2 parsing: text + page count + metadata + digest, then the bytes go away."""

import base64
import hashlib

import pytest

from app.verification.documents import (
    DocumentParseError, ParsedDocument, parse_document,
)


def _pdf_b64(text: str = "Hello letter", *, producer: str | None = None) -> str:
    """Build a real one-page PDF in memory. pypdf is already a dependency."""
    import io

    from pypdf import PdfWriter
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    if producer:
        w.add_metadata({"/Producer": producer})
    buf = io.BytesIO()
    w.write(buf)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_a_plain_text_body_parses_without_a_pdf():
    """Not every letter arrives as a PDF; a pasted body is still assessable."""
    b64 = base64.b64encode(b"EXPERIENCE LETTER\nAcme Corp").decode("ascii")
    parsed = parse_document(b64, max_pages=20)
    assert isinstance(parsed, ParsedDocument)
    assert "Acme Corp" in parsed.text
    assert parsed.page_count == 1


def test_a_pdf_parses_and_reports_its_metadata():
    parsed = parse_document(_pdf_b64(producer="LetterMill 9000"), max_pages=20)
    assert parsed.page_count == 1
    assert parsed.metadata.get("producer") == "LetterMill 9000"


def test_the_digest_is_over_the_decoded_bytes():
    raw = b"EXPERIENCE LETTER"
    b64 = base64.b64encode(raw).decode("ascii")
    assert parse_document(b64, max_pages=20).digest == hashlib.sha256(raw).hexdigest()


def test_the_parsed_document_holds_no_reference_to_the_raw_bytes():
    """The bytes must not survive the request -- there is nowhere to put them."""
    parsed = parse_document(base64.b64encode(b"letter body").decode("ascii"), max_pages=20)
    assert not hasattr(parsed, "data")
    assert not hasattr(parsed, "raw")


def test_bad_base64_raises_a_parse_error_not_a_500():
    with pytest.raises(DocumentParseError):
        parse_document("!!!not base64!!!", max_pages=20)


def test_an_empty_document_raises_a_parse_error():
    with pytest.raises(DocumentParseError):
        parse_document(base64.b64encode(b"").decode("ascii"), max_pages=20)


def test_a_damaged_pdf_raises_a_parse_error_not_a_500():
    """pypdf raises a zoo of types on a truncated file; none may escape."""
    b64 = base64.b64encode(b"%PDF-1.7\nnot really a pdf at all").decode("ascii")
    with pytest.raises(DocumentParseError):
        parse_document(b64, max_pages=20)


def test_a_page_cap_is_enforced():
    import io

    from pypdf import PdfWriter
    w = PdfWriter()
    for _ in range(3):
        w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    with pytest.raises(DocumentParseError):
        parse_document(b64, max_pages=2)
