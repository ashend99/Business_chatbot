"""Text extraction for document ingestion (Phase 2).

Supported sources: PDF/DOCX/TXT upload, and URL import. No OCR support --
scanned/image-only PDFs will extract empty or near-empty text (out of scope,
see plan).
"""

from io import BytesIO

import httpx
from bs4 import BeautifulSoup
from docx import Document as DocxDocument
from pypdf import PdfReader

from common import PROJECT_CONFIG

_url_import_config = PROJECT_CONFIG.get("documents", {}).get("url_import", {})
URL_FETCH_TIMEOUT_SECONDS = _url_import_config.get("timeout_seconds", 15)


def parse_pdf(data: bytes) -> str:
    reader = PdfReader(BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(p.strip() for p in pages if p.strip())


def parse_docx(data: bytes) -> str:
    doc = DocxDocument(BytesIO(data))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def parse_txt(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").strip()


async def fetch_url_text(url: str) -> str:
    """Fetch a URL and strip it down to plain textual content.

    Simple heuristic extraction (strip script/style/nav/header/footer, then
    collapse whitespace) -- no readability-style main-content detection,
    per the Phase 2 plan.
    """
    async with httpx.AsyncClient(timeout=URL_FETCH_TIMEOUT_SECONDS, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)
