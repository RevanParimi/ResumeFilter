"""Real hostile PDF structures must be refused before extraction/model work."""

import base64
import io
from pathlib import Path
import subprocess
import sys
import time

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, EncodedStreamObject, NameObject

from app.core.config import Settings
from app.core.pdf import pdf_b64_to_document, pdf_b64_to_text
from app.main import create_app
from app.verification.documents import DocumentParseError, parse_document
from tests.conftest import ADMIN_HEADERS
from tests.test_resume_input_boundary import counts

from app.core.resume import read_resume_input
from tests.pdf_helpers import adversarial_pdf, resume_pdf, xref_stream_pdf


@pytest.mark.parametrize('kind,setting,value', [
    ('pages', 'pdf_max_pages', 2),
    ('expansion', 'pdf_max_decoded_bytes', 1024),
    ('array', 'pdf_max_work_units', 80),
])
def test_real_adversarial_pdfs_are_refused(services, kind, setting, value):
    setattr(services.settings, setting, value)
    with pytest.raises(ValueError, match='pdf_parse_failed'):
        read_resume_input(resume_pdf_b64=adversarial_pdf(kind), settings=services.settings)


def test_pdf_page_limit_accepts_exact_boundary(services):
    services.settings.pdf_max_pages = 1
    assert read_resume_input(resume_pdf_b64=resume_pdf('Python'), settings=services.settings) == 'Python'


@pytest.mark.parametrize('kind,setting,value,reason', [
    ('raw-expansion', 'pdf_max_decoded_bytes', 1024, 'pdf_expansion_limit'),
    ('page-cycle', 'pdf_max_pages', 10, 'pdf_page_tree_invalid'),
    ('parent-cycle', 'pdf_max_pages', 10, 'pdf_parent_cycle'),
    ('page-depth', 'pdf_max_depth', 8, 'pdf_depth_limit'),
    ('form-depth', 'pdf_max_depth', 8, 'pdf_depth_limit'),
    ('form-cycle', 'pdf_max_work_units', 10000, 'pdf_form_cycle'),
    ('forms', 'pdf_max_work_units', 2000, 'pdf_work_limit'),
    ('operations', 'pdf_max_work_units', 100, 'pdf_work_limit'),
])
def test_structure_and_invocation_work_preflight(services, kind, setting, value, reason):
    setattr(services.settings, setting, value)
    with pytest.raises(ValueError, match=reason):
        pdf_b64_to_text(adversarial_pdf(kind, repeats=100 if kind == 'operations' else 12),
                        settings=services.settings)


def test_valid_nested_and_repeated_forms_keep_text(services):
    assert pdf_b64_to_text(adversarial_pdf('forms', repeats=3), settings=services.settings).count('Python') == 4


def test_flated_stream_exact_expansion_boundary(services):
    pdf = resume_pdf('Python')
    length = len(PdfReader(io.BytesIO(base64.b64decode(pdf))).pages[0]['/Contents'].get_data())
    services.settings.pdf_max_decoded_bytes = length
    assert pdf_b64_to_text(pdf, settings=services.settings) == 'Python'
    services.settings.pdf_max_decoded_bytes -= 1
    with pytest.raises(ValueError, match='pdf_expansion_limit'):
        pdf_b64_to_text(pdf, settings=services.settings)


def test_large_real_compressed_allocation_bomb_is_refused(services):
    pdf = adversarial_pdf('allocation-bomb')
    assert len(pdf) < services.settings.max_pdf_b64_chars
    with pytest.raises(ValueError, match='pdf_expansion_limit'):
        pdf_b64_to_text(pdf, settings=services.settings)


def test_xref_expansion_is_bounded_during_reader_construction(services):
    assert pdf_b64_to_document(xref_stream_pdf(), settings=services.settings)[:2] == ('', 1)
    services.settings.pdf_max_decoded_bytes = 1024
    with pytest.raises(ValueError, match='pdf_expansion_limit'):
        pdf_b64_to_document(xref_stream_pdf(padding=8192), settings=services.settings)


def test_repeated_content_array_checks_allocation_not_unique_bytes(services):
    pdf = adversarial_pdf('array', repeats=4)
    stream = PdfReader(io.BytesIO(base64.b64decode(pdf))).pages[0]['/Contents'][0].get_object()
    length = len(stream.get_data())
    services.settings.pdf_max_decoded_bytes = length + 4 * (length + 1)
    assert pdf_b64_to_text(pdf, settings=services.settings).count('Python') == 4
    services.settings.pdf_max_decoded_bytes -= 1
    with pytest.raises(ValueError, match='pdf_expansion_limit'):
        pdf_b64_to_text(pdf, settings=services.settings)


def test_chained_filter_expansion_is_cumulative(services):
    import base64 as encoding
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(base64.b64decode(resume_pdf('Python')))))
    original = writer.pages[0]['/Contents']
    stream = EncodedStreamObject()
    stream._data = encoding.a85encode(original._data) + b'~>'
    stream[NameObject('/Filter')] = ArrayObject([NameObject('/ASCII85Decode'), NameObject('/FlateDecode')])
    writer.pages[0][NameObject('/Contents')] = writer._add_object(stream)
    total = len(original._data) + len(original.get_data())
    output = io.BytesIO()
    writer.write(output)
    pdf = base64.b64encode(output.getvalue()).decode()
    services.settings.pdf_max_decoded_bytes = total
    assert pdf_b64_to_text(pdf, settings=services.settings) == 'Python'
    services.settings.pdf_max_decoded_bytes -= 1
    with pytest.raises(ValueError, match='pdf_expansion_limit'):
        pdf_b64_to_text(pdf, settings=services.settings)


def test_external_tool_filter_is_refused(services):
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(base64.b64decode(resume_pdf('Python')))))
    writer.pages[0]['/Contents'][NameObject('/Filter')] = NameObject('/JBIG2Decode')
    output = io.BytesIO()
    writer.write(output)
    with pytest.raises(ValueError, match='pdf_unsupported_filter'):
        pdf_b64_to_text(base64.b64encode(output.getvalue()).decode(), settings=services.settings)


def test_cumulative_distinct_stream_expansion(services):
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(base64.b64decode(resume_pdf('One')))))
    writer.append(PdfReader(io.BytesIO(base64.b64decode(resume_pdf('Two')))))
    length = sum(len(page['/Contents'].get_data()) for page in writer.pages)
    output = io.BytesIO()
    writer.write(output)
    pdf = base64.b64encode(output.getvalue()).decode()
    services.settings.pdf_max_decoded_bytes = length
    assert pdf_b64_to_text(pdf, settings=services.settings) == 'One\nTwo'
    services.settings.pdf_max_decoded_bytes -= 1
    with pytest.raises(ValueError, match='pdf_expansion_limit'):
        pdf_b64_to_text(pdf, settings=services.settings)


def test_verification_page_cap_precedes_stream_decoding(services):
    services.settings.pdf_max_decoded_bytes = 1
    pdf = adversarial_pdf('pages')
    with pytest.raises(ValueError, match='pdf_page_limit'):
        pdf_b64_to_document(pdf, max_pages=2, settings=services.settings)
    with pytest.raises(DocumentParseError, match='could not be read as a PDF'):
        parse_document(pdf, max_pages=2, settings=services.settings)


def test_direct_verification_encoded_cap_precedes_decoding(services):
    services.settings.doc_max_b64_chars = 8
    with pytest.raises(DocumentParseError, match='encoded size limit'):
        parse_document('!' * 9, max_pages=1, settings=services.settings)


def test_verification_metadata_page_count_and_blank_pdf_remain(services):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_metadata({'/Producer': 'Synthetic Tool', '/Creator': 'Synthetic Creator',
                         '/CreationDate': 'D:20260101000000Z', '/ModDate': 'D:20260102000000Z'})
    output = io.BytesIO()
    writer.write(output)
    parsed = parse_document(base64.b64encode(output.getvalue()).decode(), max_pages=1,
                            settings=services.settings)
    assert parsed.text == '' and parsed.page_count == 1
    assert parsed.metadata == {'producer': 'Synthetic Tool', 'creator': 'Synthetic Creator',
                               'created': 'D:20260101000000Z', 'modified': 'D:20260102000000Z'}
    assert len(parsed.digest) == 64


def test_output_limit_exact_and_over_include_metadata(services):
    pdf = resume_pdf('Python')
    text, _, meta = pdf_b64_to_document(pdf, settings=services.settings)
    services.settings.pdf_max_output_chars = len(text) + sum(len(v) for v in meta.values())
    assert pdf_b64_to_text(pdf, settings=services.settings) == text
    services.settings.pdf_max_output_chars -= 1
    with pytest.raises(ValueError, match='pdf_output_limit'):
        pdf_b64_to_text(pdf, settings=services.settings)


@pytest.mark.parametrize('helper', [pdf_b64_to_document, pdf_b64_to_text])
def test_unicode_metadata_accepts_exact_output_character_limit(services, helper):
    text = 'Readable'
    producer = '\U0001f642' * 512
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(base64.b64decode(resume_pdf(text)))))
    writer.add_metadata({'/Producer': producer})
    output = io.BytesIO()
    writer.write(output)
    pdf = base64.b64encode(output.getvalue()).decode()
    services.settings.pdf_max_output_chars = len(text) + len(producer)
    expected = (text, 1, {'producer': producer}) if helper is pdf_b64_to_document else text
    assert helper(pdf, settings=services.settings) == expected
    services.settings.pdf_max_output_chars -= 1
    with pytest.raises(ValueError, match='pdf_output_limit'):
        helper(pdf, settings=services.settings)


@pytest.mark.parametrize('name', ['max_pdf_b64_chars', 'pdf_max_pages', 'pdf_max_work_units',
    'pdf_max_depth', 'pdf_max_decoded_bytes', 'pdf_max_output_chars', 'pdf_worker_memory_mb',
    'pdf_parse_timeout_seconds'])
@pytest.mark.parametrize('value', [0, -1])
def test_limits_are_explicit_positive_settings(name, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{name: value})


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf')])
def test_deadline_must_be_finite(value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, pdf_parse_timeout_seconds=value)


def test_os_memory_limit_rejects_actual_allocation():
    import app.core.pdf as pdf_module
    worker = str(Path(pdf_module.__file__).with_name('pdf_worker.py'))
    code = """import runpy, sys
ns = runpy.run_path(sys.argv[1])
handle = ns['install_memory_limit'](64 * 1024 * 1024)
try:
    allocation = bytearray(256 * 1024 * 1024)
except MemoryError:
    print('allocation-refused')
else:
    raise SystemExit('memory-limit-failed')
"""
    result = subprocess.run([sys.executable, '-I', '-c', code, worker],
                            capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    assert result.stdout.strip() == b'allocation-refused'


def test_worker_memory_refusal_then_healthy_parse(services):
    services.settings.pdf_worker_memory_mb = 8
    with pytest.raises(ValueError, match='pdf_parse_failed|pdf_memory_limit'):
        pdf_b64_to_text(resume_pdf(), settings=services.settings)
    services.settings.pdf_worker_memory_mb = 256
    assert pdf_b64_to_text(resume_pdf('Recovered'), settings=services.settings) == 'Recovered'


def test_failed_memory_limit_installation_has_no_parser_fallback(services, monkeypatch, tmp_path):
    import app.core.pdf as pdf_module
    worker = Path(pdf_module.__file__).with_name('pdf_worker.py')
    source = worker.read_text(encoding='utf8').replace(
        'job_handle = install_memory_limit(limits["memory"])',
        'raise PdfLimitError("pdf_memory_limit_unavailable")')
    (tmp_path / 'pdf_worker.py').write_text(source, encoding='utf8')
    monkeypatch.setattr(pdf_module, '__file__', str(tmp_path / 'pdf.py'))
    with pytest.raises(ValueError, match='pdf_memory_limit_unavailable'):
        pdf_b64_to_text(resume_pdf(), settings=services.settings)


def test_real_stalled_parser_child_is_killed_waited_and_handles_closed(services, monkeypatch, tmp_path):
    import app.core.pdf as pdf_module
    worker = Path(pdf_module.__file__).with_name('pdf_worker.py')
    marker = tmp_path / 'entered-parser'
    # Instrument the actual worker after PdfReader creates a real document. The
    # process/deadline/kill/wait/handle behavior remains the production boundary.
    source = worker.read_text(encoding='utf8').replace(
        'reader = PdfReader(io.BytesIO(data), strict=limits["strict"])',
        'reader = PdfReader(io.BytesIO(data), strict=limits["strict"])\n'
        f'    open({str(marker)!r}, "w").close()\n    while True: pass')
    (tmp_path / 'pdf_worker.py').write_text(source, encoding='utf8')
    monkeypatch.setattr(pdf_module, '__file__', str(tmp_path / 'pdf.py'))
    children, files = [], []
    original = subprocess.Popen

    def capture(*args, **kwargs):
        process = original(*args, **kwargs)
        children.append(process)
        files.append(process.stdout)
        return process

    monkeypatch.setattr(pdf_module.subprocess, 'Popen', capture)
    services.settings.pdf_parse_timeout_seconds = 3
    start = time.monotonic()
    with pytest.raises(ValueError, match='pdf_timeout'):
        pdf_b64_to_text(resume_pdf(), settings=services.settings)
    assert marker.exists(), 'child timed out before reaching the controlled parser stall'
    assert time.monotonic() - start < 10
    assert children[0].poll() is not None and children[0].stdin.closed and files[0].closed
    monkeypatch.undo()
    assert pdf_b64_to_text(resume_pdf('Recovered'), settings=services.settings) == 'Recovered'


def test_unexpected_worker_stdout_has_bounded_parent_read_and_cleanup(services, monkeypatch, tmp_path):
    import app.core.pdf as pdf_module
    worker = Path(pdf_module.__file__).with_name('pdf_worker.py')
    source = worker.read_text(encoding='utf8').replace(
        'result = parse(data, limits)',
        'sys.stdout.write("x" * 1_000_000)\n        sys.stdout.flush()\n        result = parse(data, limits)')
    (tmp_path / 'pdf_worker.py').write_text(source, encoding='utf8')
    monkeypatch.setattr(pdf_module, '__file__', str(tmp_path / 'pdf.py'))
    children, reads = [], []
    original = subprocess.Popen
    class Reader:
        def __init__(self, pipe):
            self.pipe = pipe
        def read(self, size):
            data = self.pipe.read(size)
            reads.append(len(data))
            return data
        def close(self):
            self.pipe.close()
    def capture(*args, **kwargs):
        process = original(*args, **kwargs)
        process.stdout = Reader(process.stdout)
        children.append(process)
        return process
    monkeypatch.setattr(pdf_module.subprocess, 'Popen', capture)
    services.settings.pdf_max_output_chars = 8
    services.settings.pdf_parse_timeout_seconds = 3
    with pytest.raises(ValueError, match='pdf_timeout|pdf_output_limit|pdf_parse_failed'):
        pdf_b64_to_text(resume_pdf(), settings=services.settings)
    assert reads == [12 * 8 + 1024 + 1]
    assert children[0].poll() is not None
    assert children[0].stdin.closed and children[0].stdout.pipe.closed


@pytest.mark.parametrize('path', ['/evaluate', '/candidates', '/screening/candidates', '/screening/batches'])
@pytest.mark.parametrize('kind', ['pages', 'expansion', 'array', 'form-cycle'])
def test_resource_refusal_all_http_doors_without_writes_or_model_work(services, monkeypatch, path, kind):
    services.settings.pdf_max_pages = 2
    services.settings.pdf_max_decoded_bytes = 1024
    services.settings.pdf_max_work_units = 300
    async def forbidden(**kwargs):
        pytest.fail('refused PDF reached an external model')
    monkeypatch.setattr(services.llm, 'acomplete_json', forbidden)
    org = services.ledger.create_organization('Synthetic PDF Limit')
    key = services.ledger.issue_api_key(org.id)
    before = counts(services)
    payload = {'resume_pdf_b64': adversarial_pdf(kind)}
    reason = 'pdf_parse_failed'
    if path.endswith('/batches'):
        payload = {'items': [{'resume_text': 'Readable preceding item'}, payload]}
        reason = 'item 1: ' + reason
    with TestClient(create_app(services), headers={**ADMIN_HEADERS, 'X-Org-Key': key}) as http:
        response = http.post(path, json=payload)
    assert response.status_code == 422 and response.json() == {'detail': reason}
    assert counts(services) == before


@pytest.mark.parametrize('kind', ['pages', 'expansion', 'array', 'form-cycle'])
def test_verification_http_refusal_preserves_rows_and_safe_error(services, kind):
    from tests.test_verification_api import _candidate
    services.settings.pdf_max_pages = 2
    services.settings.pdf_max_decoded_bytes = 1024
    services.settings.pdf_max_work_units = 300
    cid, key = _candidate(services)
    before = services.verification._store.verifications_for_candidate(cid)
    with TestClient(create_app(services), headers={**ADMIN_HEADERS, 'X-Candidate-Key': key}) as http:
        response = http.post('/portal/documents', json={
            'doc_type': 'experience_letter', 'content_b64': adversarial_pdf(kind)})
    assert response.status_code == 400
    assert response.json() == {'detail': 'document could not be read as a PDF'}
    assert services.verification._store.verifications_for_candidate(cid) == before
