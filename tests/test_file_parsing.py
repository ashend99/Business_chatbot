from io import BytesIO

import pytest
from docx import Document as DocxDocument
from reportlab.pdfgen import canvas

from app.services import file_parsing


def _make_pdf_bytes(lines: list[str]) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    y = 750
    for line in lines:
        pdf.drawString(72, y, line)
        y -= 20
    pdf.save()
    return buffer.getvalue()


def _make_docx_bytes(paragraphs: list[str]) -> bytes:
    buffer = BytesIO()
    doc = DocxDocument()
    for text in paragraphs:
        doc.add_paragraph(text)
    doc.save(buffer)
    return buffer.getvalue()


def test_parse_pdf_extracts_text():
    data = _make_pdf_bytes(["Business hours are 9am to 5pm.", "We are closed on public holidays."])
    text = file_parsing.parse_pdf(data)
    assert "Business hours are 9am to 5pm." in text
    assert "closed on public holidays" in text


def test_parse_docx_extracts_paragraphs():
    data = _make_docx_bytes(["Refund policy", "Refunds are available within 30 days."])
    text = file_parsing.parse_docx(data)
    assert "Refund policy" in text
    assert "Refunds are available within 30 days." in text


def test_parse_txt_decodes_utf8():
    data = "Café hours: 9am–5pm.".encode()
    assert file_parsing.parse_txt(data) == "Café hours: 9am–5pm."


def test_parse_txt_replaces_invalid_bytes_instead_of_raising():
    data = b"\xff\xfehello"
    # must not raise -- malformed uploads should degrade, not crash the endpoint
    result = file_parsing.parse_txt(data)
    assert "hello" in result


@pytest.mark.asyncio
async def test_fetch_url_text_strips_script_and_style(monkeypatch):
    html = """
    <html>
      <head><style>body { color: red; }</style></head>
      <body>
        <nav>Site nav</nav>
        <script>alert('hi')</script>
        <main><p>Welcome to our shop.</p><p>We sell great coffee.</p></main>
        <footer>Copyright</footer>
      </body>
    </html>
    """

    class FakeResponse:
        text = html

        def raise_for_status(self):
            return None

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url):
            return FakeResponse()

    monkeypatch.setattr(file_parsing.httpx, "AsyncClient", FakeAsyncClient)

    text = await file_parsing.fetch_url_text("https://example.com")

    assert "Welcome to our shop." in text
    assert "We sell great coffee." in text
    assert "alert" not in text
    assert "color: red" not in text
    assert "Site nav" not in text
    assert "Copyright" not in text
