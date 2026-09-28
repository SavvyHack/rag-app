"""Text extraction only: never execute scripts, follow HTML links, or load JSON code."""
import csv
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import zipfile
from xml.etree import ElementTree as ET

from ocr import recognize, ImportCancelled

SUPPORTED = (".pdf", ".txt", ".md", ".markdown", ".html", ".htm", ".json", ".jsonl", ".ndjson",
             ".csv", ".tsv", ".yaml", ".yml", ".xml", ".log", ".rst",
             ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".docx", ".xlsx", ".pptx",
             ".py", ".js", ".ts", ".tsx", ".jsx", ".css", ".sql", ".sh", ".ps1", ".toml")
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_TEXT_CHARS = 2_000_000
MAX_PDF_PAGES = 500


def office_sections(raw, suffix, cancel=None):
    """Read Office XML without executing macros, formulas, links, or embedded files."""
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if sum(i.file_size for i in archive.infolist()) > 50 * 1024 * 1024:
            raise ValueError('Office file expands beyond the 50 MB limit.')
        def xml(name):
            data = archive.read(name)
            if b'<!DOCTYPE' in data or b'<!ENTITY' in data:
                raise ValueError('Office XML entities are not supported.')
            return ET.fromstring(data)
        if suffix == '.docx':
            root = xml('word/document.xml')
            yield 'document', '\n'.join(''.join(p.itertext()) for p in root.findall('.//{*}p'))
        elif suffix == '.pptx':
            names = sorted((n for n in archive.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml', n)),
                           key=lambda n: int(re.search(r'slide(\d+)', n)[1]))
            for number, name in enumerate(names, 1):
                if cancel and cancel.is_set():
                    raise ImportCancelled()
                yield f'slide {number}', '\n'.join(''.join(p.itertext()) for p in xml(name).findall('.//{*}p'))
        else:
            strings = []
            if 'xl/sharedStrings.xml' in archive.namelist():
                strings = [''.join(s.itertext()) for s in xml('xl/sharedStrings.xml')]
            relations = {r.get('Id'): r.get('Target') for r in xml('xl/_rels/workbook.xml.rels')}
            for sheet in xml('xl/workbook.xml').findall('.//{*}sheet'):
                if cancel and cancel.is_set():
                    raise ImportCancelled()
                rid = sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
                target = relations.get(rid, '')
                target = target.lstrip('/') if target.startswith('/') else 'xl/' + target
                if target not in archive.namelist():
                    raise ValueError('Workbook contains an unsupported external sheet.')
                for row in xml(target).findall('.//{*}row'):
                    cells = []
                    for cell in row.findall('{*}c'):
                        value = cell.findtext('{*}v', '')
                        if cell.get('t') == 's':
                            value = strings[int(value)]
                        elif cell.get('t') == 'inlineStr':
                            value = ''.join(cell.find('{*}is').itertext())
                        formula = cell.findtext('{*}f')
                        if formula is not None:
                            value += f' (cached result; formula: {formula})'
                        if value:
                            cells.append(f"{cell.get('r', '')}: {value}")
                    if cells:
                        yield f"sheet {sheet.get('name')} · row {row.get('r')}", ' | '.join(cells)


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


def extract_document(path, progress=None, cancel=None):
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
    if cancel and cancel.is_set():
        raise ImportCancelled()
    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("This PDF is password protected. Import an unlocked copy.")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise ValueError('PDF exceeds 500 pages. Split it into smaller files.')
        size, scanned, texts = 0, [], {}
        for number, page in enumerate(reader.pages, 1):
            if cancel and cancel.is_set():
                raise ImportCancelled()
            if progress:
                progress(f'Reading page {number}/{len(reader.pages)}…')
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ''
            # Sparse text (e.g. a page number) can accompany a full-page scan.
            # Image-bearing pages also get OCR, so a text heading cannot hide a scan.
            resources = page.get('/Resources', {})
            resources = resources.get_object() if hasattr(resources, 'get_object') else resources
            objects = resources.get('/XObject', {})
            objects = objects.get_object() if hasattr(objects, 'get_object') else objects
            has_images = any(obj.get_object().get('/Subtype') in {'/Image', '/Form'} for obj in objects.values())
            if len(re.sub(r'\W', '', text)) < 40 or has_images:
                scanned.append(number)
            texts[number] = text
            size += len(text)
            if size > MAX_TEXT_CHARS:
                raise ValueError("PDF contains too much text. Split it into smaller files.")
        recognized = recognize(path, scanned, progress, cancel) if scanned else {}
        for number, text in texts.items():
            ocr = recognized.get(number, '').strip()
            if ocr:
                # OCR sees the rendered whole page; retain any text it missed without
                # duplicating the whole native text layer.
                normalized = re.sub(r'\s+', '', ocr).casefold()
                missing = [line for line in text.splitlines() if line.strip() and re.sub(r'\s+', '', line).casefold() not in normalized]
                text = ocr + ('\n' + '\n'.join(missing) if missing else '')
            if text.strip():
                sections.append((f"page {number}" + (' (OCR)' if ocr else ''), text))
    elif suffix in {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'}:
        sections = [('image (OCR)', recognize(path, progress=progress, cancel=cancel)[1])]
    elif suffix in {'.docx', '.xlsx', '.pptx'}:
        size = 0
        for location, text in office_sections(raw, suffix, cancel):
            size += len(text)
            if size > MAX_TEXT_CHARS:
                raise ValueError('Office document exceeds 2 million text characters.')
            sections.append((location, text))
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
        raise ValueError("No readable text found after automatic OCR. The pages may be blank or the scan unclear." if suffix in {'.pdf', '.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'} else "The document contains no readable text.")
    if len(chunks) > 2500:
        raise ValueError("Too many document sections. Split the file into smaller files.")
    return digest, chunks
