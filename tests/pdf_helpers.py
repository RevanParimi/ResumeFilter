"""Synthetic PDFs with real text/image streams; no candidate data or OCR."""

import base64
import io
import zlib

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, NumberObject, DecodedStreamObject


def resume_pdf(text="Synthetic Person", *, encrypted=False, image_only=False):
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    stream = DecodedStreamObject()
    if image_only:
        image = DecodedStreamObject()
        image.set_data(b"\x00\x00\x00")
        image.update({NameObject("/Type"): NameObject("/XObject"),
                      NameObject("/Subtype"): NameObject("/Image"),
                      NameObject("/Width"): NumberObject(1), NameObject("/Height"): NumberObject(1),
                      NameObject("/BitsPerComponent"): NumberObject(8),
                      NameObject("/ColorSpace"): NameObject("/DeviceRGB")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/XObject"):
            DictionaryObject({NameObject("/Im1"): writer._add_object(image)})})
        stream.set_data(b"q 100 0 0 100 0 0 cm /Im1 Do Q")
    else:
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"):
            DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        literal = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream.set_data(f"BT /F1 12 Tf 10 100 Td ({literal}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream.flate_encode())
    if encrypted:
        writer.encrypt("synthetic-password")
    output = io.BytesIO()
    writer.write(output)
    return base64.b64encode(output.getvalue()).decode("ascii")


def adversarial_pdf(kind, *, repeats=100, padding=8192, page_count=3):
    """Readable hostile structures, written as actual PDFs, never mocked readers."""
    writer = PdfWriter()
    source = PdfReader(io.BytesIO(base64.b64decode(resume_pdf("Python"))))
    page = writer.add_page(source.pages[0])
    if kind == "pages":
        for _ in range(page_count - 1):
            writer.add_page(source.pages[0])
        writer._pages.get_object()[NameObject("/Count")] = NumberObject(1)
    elif kind == "page-cycle":
        root = writer._pages.get_object()
        root[NameObject("/Kids")] = ArrayObject([writer._pages])
    elif kind == "parent-cycle":
        page[NameObject("/Parent")] = page.indirect_reference
    elif kind == "page-depth":
        child = page.indirect_reference
        for _ in range(repeats):
            node = DictionaryObject({NameObject("/Type"): NameObject("/Pages"),
                NameObject("/Kids"): ArrayObject([child]), NameObject("/Count"): NumberObject(1)})
            child = writer._add_object(node)
        writer._pages.get_object()[NameObject("/Kids")] = ArrayObject([child])
    elif kind in ("form-cycle", "forms", "form-depth"):
        res = page["/Resources"]
        child = None
        for _ in range(repeats if kind != "form-cycle" else 1):
            form = DecodedStreamObject()
            form[NameObject("/Type")] = NameObject("/XObject")
            form[NameObject("/Subtype")] = NameObject("/Form")
            form[NameObject("/BBox")] = ArrayObject([NumberObject(0)] * 4)
            own = DictionaryObject({NameObject("/Font"): res["/Font"]})
            if child is None:
                form.set_data(page["/Contents"].get_data())
            else:
                own[NameObject("/XObject")] = DictionaryObject({NameObject("/F"): child})
                form.set_data(b"/F Do\n" * (2 if kind == "forms" else 1))
            form[NameObject("/Resources")] = own
            child = writer._add_object(form)
        if kind == "form-cycle":
            own[NameObject("/XObject")] = DictionaryObject({NameObject("/F"): child})
            form.set_data(form.get_data() + b"\n/F Do\n")
        res[NameObject("/XObject")] = DictionaryObject({NameObject("/F"): child})
        stream = DecodedStreamObject()
        stream.set_data(b"/F Do\n")
        page[NameObject("/Contents")] = writer._add_object(stream)
    else:
        stream = DecodedStreamObject()
        stream.set_data(page["/Contents"].get_data() +
            (b" " * padding if kind in ("expansion", "raw-expansion") else b"q Q\n" * repeats if kind == "operations" else b""))
        if kind == "allocation-bomb":
            # Build a 256 MiB expansion with ~1 MiB builder memory, rather than
            # allocating the adversarial decoded stream in the test process.
            encoder = zlib.compressobj()
            chunks = [encoder.compress(stream.get_data())]
            for _ in range(256):
                chunks.append(encoder.compress(b" " * (1024 * 1024)))
            chunks.append(encoder.flush())
            from pypdf.generic import EncodedStreamObject
            stream = EncodedStreamObject()
            stream._data = b"".join(chunks)
            stream[NameObject("/Filter")] = NameObject("/FlateDecode")
        ref = writer._add_object(stream if kind in ("raw-expansion", "allocation-bomb") else stream.flate_encode())
        page[NameObject("/Contents")] = ArrayObject([ref] * repeats) if kind == "array" else ref
    output = io.BytesIO()
    writer.write(output)
    return base64.b64encode(output.getvalue()).decode("ascii")


def xref_stream_pdf(*, padding=0, cycle=False):
    """Actual PDF 1.5 xref decompression occurs during reader construction."""
    data = bytearray(b"%PDF-1.5\n")
    offsets = [0]
    bodies = [b"<< /Type /Catalog /Pages 2 0 R >>",
              b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
              b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << >> >>"]
    for number, body in enumerate(bodies, 1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref_offset = len(data)
    offsets.append(xref_offset)
    entries = b"\x00\x00\x00\x00\x00\xff\xff" + b"".join(
        b"\x01" + offset.to_bytes(4, "big") + b"\x00\x00" for offset in offsets[1:])
    stream = zlib.compress(entries + b" " * padding)
    previous = f" /Prev {xref_offset}" if cycle else ""
    data.extend(f"4 0 obj\n<< /Type /XRef /Size 5 /Root 1 0 R /W [1 4 2] /Filter /FlateDecode /Length {len(stream)}{previous} >>\nstream\n".encode())
    data.extend(stream + b"\nendstream\nendobj\n")
    data.extend(f"startxref\n{xref_offset}\n%%EOF\n".encode())
    return base64.b64encode(data).decode()
