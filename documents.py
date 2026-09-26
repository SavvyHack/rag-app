"""Text extraction only: never execute scripts, follow HTML links, or load JSON code."""
import csv
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re

SUPPORTED = (".pdf", ".txt", ".md", ".markdown", ".html", ".htm", ".json", ".jsonl", ".ndjson",
             ".csv", ".tsv", ".yaml", ".yml", ".xml", ".log", ".rst")
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_TEXT_CHARS = 2_000_000


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "template", "head"}:
            self.hidden.append(tag)
        if not self.hidden and tag in {"p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "section"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.hidden and tag == self.hidden[-1]:
            self.hidden.pop()
        if not self.hidden and tag in {"p", "div", "li", "tr", "td", "th", "section", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def decode_text(raw):
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    if b"\x00" in raw:
        raise ValueError("This appears to be a binary file, not a supported text document.")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252")


def split_text(text, chunk_size=1200, chunk_overlap=180):
    """Bound long sentences, code, minified JSON, and ordinary paragraphs alike."""
    if not 0 <= chunk_overlap < chunk_size:
        raise ValueError("Overlap must be smaller than the chunk size.")
    text = text.replace("\x00", "").strip()
    chunks, start = [], 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            boundary = max(text.rfind("\n", start + chunk_size // 2, end),
                           text.rfind(" ", start + chunk_size // 2, end))
            if boundary > start + chunk_overlap:
                end = boundary
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end == len(text):
            break
        start = end - chunk_overlap
    return chunks


def extract_document(path):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError(f"Unsupported file type: {suffix or '(none)'}")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("File exceeds the 25 MB limit. Split it into smaller files.")
    raw = path.read_bytes()
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("File exceeds the 25 MB limit.")
    digest = hashlib.sha256(raw).hexdigest()
    sections = []
    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("This PDF is password protected. Import an unlocked copy.")
        size = 0
        for number, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            size += len(text)
            if size > MAX_TEXT_CHARS:
                raise ValueError("PDF contains too much text. Split it into smaller files.")
            if text.strip():
                sections.append((f"page {number}", text))
    else:
        text = decode_text(raw)
        if suffix in {".html", ".htm"}:
            parser = VisibleHTML()
            parser.feed(text)
            text = re.sub(r"[ \t]+", " ", "".join(parser.parts))
        elif suffix == ".json":
            text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
        elif suffix in {".jsonl", ".ndjson"}:
            text = "\n".join(json.dumps(json.loads(line), ensure_ascii=False) for line in text.splitlines() if line.strip())
        elif suffix in {".csv", ".tsv"}:
            rows = csv.reader(io.StringIO(text), delimiter="\t" if suffix == ".tsv" else ",")
            header = next(rows, [])
            lines = ["Columns: " + " | ".join(header)] if header else []
            for number, row in enumerate(rows, 2):
                lines.append(f"Row {number}: " + "; ".join(f"{header[i] if i < len(header) else 'Column ' + str(i + 1)}: {value}" for i, value in enumerate(row)))
            text = "\n".join(lines)
        # YAML and XML are retained as text; no unsafe deserializers/entities.
        sections = [("text", text)]
    if sum(len(text) for _, text in sections) > MAX_TEXT_CHARS:
        raise ValueError("Document exceeds 2 million text characters. Split it into smaller files.")
    chunks = [(location, chunk) for location, text in sections for chunk in split_text(text)]
    if not chunks:
        raise ValueError("No readable text found. Scanned PDFs need OCR before import." if suffix == ".pdf" else "The document contains no readable text.")
    if len(chunks) > 2500:
        raise ValueError("Too many document sections. Split the file into smaller files.")
    return digest, chunks
