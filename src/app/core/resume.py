"""One resume acceptance boundary, before models, graphs or intake writes."""

from app.core.config import Settings
from app.core.pdf import pdf_b64_to_text
from app.core.pdf_execution import PdfExecutor


class ResumeInputError(ValueError):
    """Safe refusal code plus client detail; never parser exception content."""

    def __init__(self, reason: str, detail: str | None = None):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail or reason


async def read_resume_input_async(*, executor: PdfExecutor, **kwargs) -> str:
    # Text precedence and cheap input refusals require no worker admission.
    if kwargs.get('resume_text') or not kwargs.get('resume_pdf_b64'):
        return read_resume_input(**kwargs)
    if len(kwargs['resume_pdf_b64']) > kwargs['settings'].max_pdf_b64_chars:
        return read_resume_input(**kwargs)
    return await executor.run(read_resume_input, **kwargs)


def validate_resume_text(text: str, settings: Settings) -> str:
    # Count before trimming: padding must not bypass the decoded/raw text cap.
    if len(text) > settings.max_resume_chars:
        raise ResumeInputError("resume_too_long",
            f"resume_text exceeds max_resume_chars={settings.max_resume_chars}")
    text = text.strip()
    if not text:
        raise ResumeInputError("empty_resume")
    return text


def read_resume_input(
    *, resume_text: str | None = None, resume_pdf_b64: str | None = None,
    settings: Settings,
) -> str:
    # Preserve existing text precedence and caps on either supplied source.
    text = validate_resume_text(resume_text, settings) if resume_text else None
    if resume_pdf_b64 and len(resume_pdf_b64) > settings.max_pdf_b64_chars:
        raise ResumeInputError("pdf_too_large",
            f"resume_pdf_b64 exceeds max_pdf_b64_chars={settings.max_pdf_b64_chars}")
    if text is not None:
        return text
    if not resume_pdf_b64:
        raise ResumeInputError("empty_resume")
    try:
        text = pdf_b64_to_text(resume_pdf_b64, settings=settings)
    except Exception:
        # The parser has many exception types; none is public error detail.
        raise ResumeInputError("pdf_parse_failed") from None
    try:
        return validate_resume_text(text, settings)
    except ResumeInputError as exc:
        # Empty scanned/blank PDFs are unreadable, not low-evidence resumes.
        if exc.reason == "empty_resume":
            raise ResumeInputError("pdf_no_readable_text") from None
        raise
