"""Standalone PDF worker. No app construction, credentials, stores or network.

Invoked by pdf.py with Python -I. Memory containment precedes the pypdf import
and every PDF allocation. Logical preflight budgets precede text extraction.
"""

from __future__ import annotations

import io
import json
import logging
import sys
import zlib


class PdfLimitError(BaseException):
    # pypdf catches Exception inside form extraction and recovery. A containment
    # refusal must reach our outer boundary instead of becoming partial text.
    pass


def install_memory_limit(size: int):
    """Return a live Windows Job handle, or install Linux RLIMIT_AS.

    Windows limits private committed memory, Linux the entire address space.
    Unsupported/failed limits must refuse; never run an uncontained parser.
    """
    if sys.platform == "linux":
        import resource
        _, hard = resource.getrlimit(resource.RLIMIT_AS)
        ceiling = size if hard == resource.RLIM_INFINITY else min(size, hard)
        resource.setrlimit(resource.RLIMIT_AS, (ceiling, ceiling))
        return None
    if sys.platform != "win32":
        raise PdfLimitError("pdf_memory_limit_unavailable")
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [("ProcessTime", ctypes.c_int64), ("JobTime", ctypes.c_int64),
                    ("Flags", wintypes.DWORD), ("MinWorkingSet", ctypes.c_size_t),
                    ("MaxWorkingSet", ctypes.c_size_t), ("ActiveProcesses", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("Priority", wintypes.DWORD),
                    ("Scheduling", wintypes.DWORD)]

    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in
                    ("ReadOps", "WriteOps", "OtherOps", "ReadBytes", "WriteBytes", "OtherBytes")]

    class Extended(ctypes.Structure):
        _fields_ = [("Basic", Basic), ("IO", IO), ("ProcessMemory", ctypes.c_size_t),
                    ("JobMemory", ctypes.c_size_t), ("PeakProcess", ctypes.c_size_t),
                    ("PeakJob", ctypes.c_size_t)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                               ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise PdfLimitError("pdf_memory_limit_unavailable")
    limits = Extended()
    # PROCESS_MEMORY | KILL_ON_JOB_CLOSE. Keep the handle until process exit.
    limits.Basic.Flags = 0x100 | 0x2000
    limits.ProcessMemory = size
    if (not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits))
            or not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess())):
        kernel.CloseHandle(handle)
        raise PdfLimitError("pdf_memory_limit_unavailable")
    return handle


class Budget:
    def __init__(self, limits):
        self.limits = limits
        self.work = 0
        self.decoded = 0

    def visit(self, count=1):
        self.work += count
        if self.work > self.limits["work"]:
            raise PdfLimitError("pdf_work_limit")

    def expand(self, count):
        self.decoded += count
        if self.decoded > self.limits["decoded"]:
            raise PdfLimitError("pdf_expansion_limit")

    def depth(self, depth):
        if depth > self.limits["depth"]:
            raise PdfLimitError("pdf_depth_limit")


def bound_decoders(budget):
    """Bound Flate output before allocation; budget every filter's output.

    Other filters/predictor/object allocations remain inside the OS limit.
    Disable decoders that can launch external tools (JBIG2). Images are never
    decoded for text extraction, so ordinary image-only PDFs still work.
    """
    from pypdf import filters
    from pypdf.generic import ArrayObject, EncodedStreamObject, NameObject, NullObject
    original = filters.decode_stream_data
    safe = {"/FlateDecode", "/Fl", "/ASCIIHexDecode", "/AHx", "/ASCII85Decode", "/A85",
            "/LZWDecode", "/LZW", "/RunLengthDecode", "/RL"}

    def decompress(data):
        remaining = budget.limits["decoded"] - budget.decoded
        decoder = zlib.decompressobj()
        result = decoder.decompress(data, remaining + 1)
        if len(result) > remaining or decoder.unconsumed_tail:
            raise PdfLimitError("pdf_expansion_limit")
        if not decoder.eof:
            raise PdfLimitError("pdf_parse_failed")
        return result

    def decode(stream):
        names = stream.get("/Filter", ArrayObject()).get_object()
        if not isinstance(names, ArrayObject):
            names = [names]
        params = stream.get("/DecodeParms", NullObject()).get_object()
        if not isinstance(params, ArrayObject):
            params = [params] * len(names)
        budget.visit(len(names))
        data = stream._data
        if not names:
            budget.expand(len(data))
        for index, name in enumerate(names):
            if name not in safe:
                raise PdfLimitError("pdf_unsupported_filter")
            remaining = budget.limits["decoded"] - budget.decoded
            # Available pypdf limits supplement the OS limit. Do not depend on
            # them for Flate containment or permit a zero/unlimited decoder cap.
            for attr in ("LZW_MAX_OUTPUT_LENGTH", "RUN_LENGTH_MAX_OUTPUT_LENGTH",
                         "FLATE_MAX_BUFFER_SIZE", "FLATE_MAX_ROW_LENGTH", "FLATE_MAX_COLUMNS"):
                if hasattr(filters, attr):
                    setattr(filters, attr, min(getattr(filters, attr), remaining + 1))
            one = EncodedStreamObject()
            one._data = data
            one[NameObject("/Filter")] = name
            if index < len(params):
                one[NameObject("/DecodeParms")] = params[index]
            data = original(one)
            budget.expand(len(data))
        return data

    filters.decompress = decompress
    filters.decode_stream_data = decode


def preflight(reader, budget):
    from pypdf.generic import (ArrayObject, ContentStream, DictionaryObject,
                               EncodedStreamObject, NullObject, StreamObject)

    def resolve(value):
        budget.visit()
        return value.get_object()

    # Count actual leaves before PdfReader.pages recursively flattens the tree.
    pending = [(reader.root_object["/Pages"], 1)]
    seen = set()
    page_count = 0
    while pending:
        value, depth = pending.pop()
        budget.depth(depth)
        node = resolve(value)
        if not isinstance(node, DictionaryObject) or id(node) in seen:
            raise PdfLimitError("pdf_page_tree_invalid")
        seen.add(id(node))
        if node.get("/Type") == "/Pages" or "/Kids" in node:
            kids = resolve(node.get("/Kids", ArrayObject()))
            if not isinstance(kids, ArrayObject):
                raise PdfLimitError("pdf_page_tree_invalid")
            budget.visit(len(kids))
            pending.extend((kid, depth + 1) for kid in kids)
        else:
            page_count += 1
            if page_count > budget.limits["pages"]:
                raise PdfLimitError("pdf_page_limit")

    # Inspect all reachable objects and resources, including font/CMap streams.
    # Parent/resource backreferences are normal here; invoked form cycles below
    # are refused separately. Charge container edges before growing the stack.
    pending = [(reader.trailer, 1)]
    seen.clear()
    while pending:
        value, depth = pending.pop()
        budget.depth(depth)
        node = resolve(value)
        if id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, StreamObject) and node.get("/Subtype") != "/Image":
            data = node.get_data()
            if not isinstance(node, EncodedStreamObject):
                budget.expand(len(data))
        if isinstance(node, DictionaryObject):
            budget.visit(len(node))
            pending.extend((child, depth + 1) for child in node.values())
        elif isinstance(node, ArrayObject):
            budget.visit(len(node))
            pending.extend((child, depth + 1) for child in node)

    def resources(obj):
        # pypdf can follow /Parent for inherited resources before extracting.
        current, parents, depth = obj, set(), 0
        found = None
        while isinstance(current, DictionaryObject):
            budget.visit()
            depth += 1
            budget.depth(depth)
            if id(current) in parents:
                raise PdfLimitError("pdf_parent_cycle")
            parents.add(id(current))
            if found is None and "/Resources" in current:
                found = resolve(current["/Resources"])
            if "/Parent" not in current:
                break
            current = resolve(current["/Parent"])
        return found if isinstance(found, DictionaryObject) else DictionaryObject()

    def content(obj, form):
        value = obj if form else resolve(obj.get("/Contents", NullObject()))
        if isinstance(value, NullObject):
            return []
        if isinstance(value, ArrayObject):
            # Repeated references amplify concatenation even when unique decoded
            # streams fit. Check the entire allocation before ContentStream.
            budget.visit(len(value))
            size = 0
            for item in value:
                stream = resolve(item)
                if isinstance(stream, NullObject):
                    continue
                if not isinstance(stream, StreamObject):
                    raise PdfLimitError("pdf_contents_invalid")
                data = stream.get_data()
                size += len(data) + (0 if data.endswith(b"\n") else 1)
                if size > budget.limits["decoded"] - budget.decoded:
                    raise PdfLimitError("pdf_expansion_limit")
            budget.expand(size)
        return ContentStream(value, reader, "bytes").operations

    memo, active = {}, set()

    def cost(obj, form=False, depth=1):
        budget.depth(depth)
        budget.visit()
        key = id(obj)
        if key in active:
            raise PdfLimitError("pdf_form_cycle")
        if key in memo:
            return memo[key]
        active.add(key)
        res = resources(obj)
        ops = content(obj, form)
        total = 1 + len(ops)
        fonts = resolve(res.get("/Font", DictionaryObject()))
        total += len(fonts) if isinstance(fonts, DictionaryObject) else 0
        xobjects = resolve(res.get("/XObject", DictionaryObject()))
        for operands, operator in ops:
            if operator == b"Do" and operands and operands[0] in xobjects:
                target = resolve(xobjects[operands[0]])
                if isinstance(target, StreamObject) and target.get("/Subtype") != "/Image":
                    total += cost(target, True, depth + 1)
            if total > budget.limits["work"] - budget.work:
                raise PdfLimitError("pdf_work_limit")
        active.remove(key)
        memo[key] = total
        return total

    pages = list(reader.pages)
    if len(pages) != page_count:
        raise PdfLimitError("pdf_page_tree_invalid")
    for page in pages:
        budget.visit(cost(page))
    return pages


def parse(data, limits):
    from pypdf import PdfReader
    from pypdf._page import PageObject
    original_form = PageObject.extract_xform_text

    def extract_form(*args, **kwargs):
        try:
            return original_form(*args, **kwargs)
        except MemoryError:
            raise PdfLimitError("pdf_memory_limit") from None

    PageObject.extract_xform_text = extract_form
    budget = Budget(limits)
    bound_decoders(budget)
    reader = PdfReader(io.BytesIO(data), strict=limits["strict"])
    if reader.is_encrypted:
        raise PdfLimitError("pdf_parse_failed")
    pages = preflight(reader, budget)
    raw = reader.metadata or {}
    meta = {key: str(raw[name]) for key, name in
            (("producer", "/Producer"), ("creator", "/Creator"),
             ("created", "/CreationDate"), ("modified", "/ModDate")) if raw.get(name)}
    length = sum(len(value) for value in meta.values())
    if length > limits["output"]:
        raise PdfLimitError("pdf_output_limit")
    texts = []
    for page in pages:
        text = page.extract_text() or ""
        length += len(text) + bool(texts)
        if length > limits["output"]:
            raise PdfLimitError("pdf_output_limit")
        texts.append(text)
    return dict(text="\n".join(texts), pages=len(pages), meta=meta)


def main():
    logging.disable(logging.CRITICAL)
    try:
        limits = json.loads(sys.argv[1])
        # Retain the Job handle through process exit; never close it while parsing.
        job_handle = install_memory_limit(limits["memory"])
        data = sys.stdin.buffer.read(limits["input"] + 1)
        if len(data) != limits["input"]:
            raise PdfLimitError("pdf_input_limit")
        result = parse(data, limits)
    except PdfLimitError as exc:
        result = {"error": str(exc)}
    except Exception:
        result = {"error": "pdf_parse_failed"}
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
