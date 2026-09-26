"""/tenant/documents: create (paste/upload/url), edit, publish lifecycle,
limits and errors."""

from io import BytesIO

import pytest
from factories import make_tenant, tenant_headers

from app.api.tenant import documents as documents_api
from app.components.rag import hybrid_rag
from app.services import file_parsing


@pytest.fixture
async def api(client, session):
    tenant = await make_tenant(session)
    return client, tenant_headers(tenant.id)


async def paste(client, h, content: str = "Refunds within seven days.", **extra):
    response = await client.post(
        "/tenant/documents", headers=h, json={"title": "Policy", "draft_content": content, **extra}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_paste_publish_edit_republish(api) -> None:
    client, h = api
    doc = await paste(client, h, tags=["faq"])
    assert doc["status"] == "draft"

    published = await client.post(f"/tenant/documents/{doc['id']}/publish", headers=h)
    assert published.status_code == 200
    assert published.json()["status"] == "active" and published.json()["last_published_at"]

    edited = (
        await client.patch(
            f"/tenant/documents/{doc['id']}", headers=h, json={"draft_content": "New text"}
        )
    ).json()
    assert edited["status"] == "draft"
    assert (await client.post(f"/tenant/documents/{doc['id']}/publish", headers=h)).json()[
        "status"
    ] == "active"

    deactivated = await client.patch(f"/tenant/documents/{doc['id']}/deactivate", headers=h)
    assert deactivated.json()["status"] == "inactive"

    listed = (await client.get("/tenant/documents", params={"tag": "faq"}, headers=h)).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == doc["id"]

    assert (await client.delete(f"/tenant/documents/{doc['id']}", headers=h)).status_code == 204
    assert (await client.get(f"/tenant/documents/{doc['id']}", headers=h)).status_code == 404


async def test_create_validation(api) -> None:
    client, h = api
    assert (
        await client.post(
            "/tenant/documents", headers=h, json={"title": "Empty", "draft_content": " "}
        )
    ).status_code == 422
    url_doc = {"title": "Site", "content_source": "url", "draft_content": "x"}
    assert (await client.post("/tenant/documents", headers=h, json=url_doc)).status_code == 422


async def test_publish_errors(api, monkeypatch) -> None:
    client, h = api
    upload = (
        await client.post(
            "/tenant/documents", headers=h, json={"title": "Menu", "content_source": "upload"}
        )
    ).json()
    no_content = await client.post(f"/tenant/documents/{upload['id']}/publish", headers=h)
    assert no_content.status_code == 400

    doc = await paste(client, h)
    assert (await client.post(f"/tenant/documents/{doc['id']}/retry", headers=h)).status_code == 400

    async def broken(texts):
        raise RuntimeError("embeddings down")

    monkeypatch.setattr(hybrid_rag, "embed_texts", broken)
    failed = await client.post(f"/tenant/documents/{doc['id']}/publish", headers=h)
    assert failed.status_code == 502
    assert (await client.get(f"/tenant/documents/{doc['id']}", headers=h)).json()[
        "status"
    ] == "failed"

    monkeypatch.undo()
    retried = await client.post(f"/tenant/documents/{doc['id']}/retry", headers=h)
    assert retried.status_code == 200 and retried.json()["status"] == "active"


async def upload_placeholder(client, h) -> str:
    created = await client.post(
        "/tenant/documents", headers=h, json={"title": "Upload", "content_source": "upload"}
    )
    return created.json()["id"]


async def test_upload_txt_and_docx(api) -> None:
    client, h = api
    doc_id = await upload_placeholder(client, h)
    txt = await client.post(
        f"/tenant/documents/{doc_id}/upload",
        headers=h,
        files={"file": ("hours.txt", b"Open 9 to 5.", "text/plain")},
    )
    assert txt.status_code == 200
    assert (txt.json()["draft_content"], txt.json()["source_ref"]) == ("Open 9 to 5.", "hours.txt")

    from docx import Document

    buffer = BytesIO()
    word = Document()
    word.add_paragraph("Parking behind the shop.")
    word.save(buffer)
    docx = await client.post(
        f"/tenant/documents/{doc_id}/upload",
        headers=h,
        files={"file": ("info.DOCX", buffer.getvalue(), "application/octet-stream")},
    )
    assert docx.json()["draft_content"] == "Parking behind the shop."


async def test_upload_rejections(api, monkeypatch) -> None:
    client, h = api
    doc_id = await upload_placeholder(client, h)
    files = {"file": ("image.png", b"\x89PNG", "image/png")}
    assert (
        await client.post(f"/tenant/documents/{doc_id}/upload", headers=h, files=files)
    ).status_code == 400

    corrupt = {"file": ("broken.pdf", b"not a pdf", "application/pdf")}
    assert (
        await client.post(f"/tenant/documents/{doc_id}/upload", headers=h, files=corrupt)
    ).status_code == 400

    pasted = await paste(client, h)
    txt = {"file": ("a.txt", b"text", "text/plain")}
    assert (
        await client.post(f"/tenant/documents/{pasted['id']}/upload", headers=h, files=txt)
    ).status_code == 400

    monkeypatch.setattr(documents_api, "MAX_DOCUMENT_CHARS", 5)
    big = {"file": ("big.txt", b"more than five characters", "text/plain")}
    assert (
        await client.post(f"/tenant/documents/{doc_id}/upload", headers=h, files=big)
    ).status_code == 413

    monkeypatch.setattr(documents_api, "MAX_DOCUMENT_UPLOAD_MB", 0)
    assert (
        await client.post(f"/tenant/documents/{doc_id}/upload", headers=h, files=txt)
    ).status_code == 413


async def test_import_url(api, monkeypatch) -> None:
    client, h = api

    async def fake_fetch(url: str) -> str:
        return f"Content of {url}"

    monkeypatch.setattr(file_parsing, "fetch_url_text", fake_fetch)
    created = await client.post(
        "/tenant/documents/import-url",
        headers=h,
        json={"title": "About", "url": "https://example.com/about"},
    )
    assert created.status_code == 201
    body = created.json()
    assert (body["content_source"], body["source_ref"]) == ("url", "https://example.com/about")
    assert body["draft_content"] == "Content of https://example.com/about"

    async def failing_fetch(url: str) -> str:
        raise ConnectionError("unreachable")

    monkeypatch.setattr(file_parsing, "fetch_url_text", failing_fetch)
    failed = await client.post(
        "/tenant/documents/import-url", headers=h, json={"title": "x", "url": "https://example.com"}
    )
    assert failed.status_code == 502


async def test_expired_filter_and_lazy_sweep(api) -> None:
    client, h = api
    doc = await paste(client, h, active_until="2020-01-01T00:00:00Z")
    await client.post(f"/tenant/documents/{doc['id']}/publish", headers=h)
    # listing sweeps it: an expired active document shows as inactive
    listed = (await client.get("/tenant/documents", params={"expired": True}, headers=h)).json()
    assert [(d["id"], d["status"], d["is_expired"]) for d in listed["items"]] == [
        (doc["id"], "inactive", True)
    ]
