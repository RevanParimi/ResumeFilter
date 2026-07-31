"""Document parsing + deterministic forensics (S7.2).

NO LLM and no network. These checks are structural and arithmetic, so the
"every LLM step needs a deterministic fallback" convention is satisfied by
having no LLM at all -- the S6.2/S6.3 precedent.

The document does not survive this module. `parse_document` returns text,
metadata and a sha256 digest; the decoded bytes are local and go out of scope.
ParsedDocument deliberately has no field able to hold them.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from dataclasses import dataclass, field


class DocumentParseError(Exception):
    """The submitted body could not be decoded, was empty, or exceeded the
    page cap. Carries no document content."""


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    page_count: int
    digest: str                       # sha256 of the decoded bytes
    metadata: dict = field(default_factory=dict)


def parse_document(content_b64: str, *, max_pages: int) -> ParsedDocument:
    """Decode, extract text + metadata, and hash. PDF first; anything that is
    not a PDF is treated as a UTF-8 text body, because a pasted letter is still
    assessable and refusing it would push candidates toward worse workarounds.
    """
    try:
        data = base64.b64decode(content_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DocumentParseError("content is not valid base64") from exc
    if not data:
        raise DocumentParseError("document is empty")

    digest = hashlib.sha256(data).hexdigest()

    if data[:5] == b"%PDF-":
        from app.core.pdf import pdf_b64_to_document
        try:
            text, pages, meta = pdf_b64_to_document(content_b64)
        except DocumentParseError:
            raise
        except Exception as exc:  # pypdf raises a zoo of types on damaged files
            raise DocumentParseError("document could not be read as a PDF") from exc
        if pages > max_pages:
            raise DocumentParseError(f"document exceeds {max_pages} pages")
        return ParsedDocument(text=text, page_count=pages, digest=digest, metadata=meta)

    text = data.decode("utf-8", errors="replace").strip()
    if not text:
        raise DocumentParseError("document contains no readable text")
    return ParsedDocument(text=text, page_count=1, digest=digest)
