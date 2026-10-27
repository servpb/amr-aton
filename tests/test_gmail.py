"""Unit tests for Gmail Read-Only tools and OAuth2 integration (Phase 4)."""

import base64
import io
import json
from unittest.mock import MagicMock, patch

import pytest

from src.tools import ALL_ATON_TOOLS, dispatch_tool
from src.tools.gmail import (
    GMAIL_FUNCTION_DECLARATIONS,
    _decode_base64_data,
    _extract_plain_text,
    dispatch_gmail_tool,
    get_email_content,
    list_unread_emails,
)


def test_decode_base64_data():
    """Test URL-safe base64 decoding helper."""
    assert _decode_base64_data("") == ""
    # Encode 'Olá Mundo!' in url-safe base64
    sample = "T2zDoSBNdW5kbyE"  # Without padding
    decoded = _decode_base64_data(sample)
    assert decoded == "Olá Mundo!"


def test_extract_plain_text():
    """Test extracting body text from simple and multipart payloads."""
    # 1. Direct body plain text
    b64_hello = base64.urlsafe_b64encode(b"Ola Aton").decode("utf-8")
    payload1 = {"mimeType": "text/plain", "body": {"data": b64_hello}}
    assert _extract_plain_text(payload1) == "Ola Aton"

    # 2. HTML body with tags to strip
    b64_html = base64.urlsafe_b64encode(b"<p>Reuniao <b>importante</b> as 14h</p>").decode("utf-8")
    payload2 = {"mimeType": "text/html", "body": {"data": b64_html}}
    assert "Reuniao importante as 14h" in _extract_plain_text(payload2)

    # 3. Multipart with parts
    payload3 = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/html", "body": {"data": b64_html}},
            {"mimeType": "text/plain", "body": {"data": b64_hello}},
        ],
    }
    assert _extract_plain_text(payload3) == "Ola Aton"


def test_list_unread_emails_unauthenticated():
    """Verify behavior when no credentials exist."""
    with patch("src.tools.gmail._get_credentials", return_value=None):
        res = list_unread_emails()
        assert res["status"] == "not_authenticated"
        assert "Gmail ainda não está autenticado" in res["message"]
        assert res["emails"] == []


def test_list_unread_emails_empty():
    """Verify behavior when inbox has no unread messages."""
    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_creds.token = "mock_token"

    mock_resp = io.BytesIO(json.dumps({"messages": []}).encode("utf-8"))

    with patch("src.tools.gmail._get_credentials", return_value=mock_creds), \
         patch("urllib.request.urlopen", return_value=mock_resp):
        res = list_unread_emails()
        assert res["status"] == "success"
        assert res["count"] == 0
        assert "não tem nenhum novo e-mail" in res["message"]


def test_list_unread_emails_success():
    """Verify listing unread messages with headers metadata."""
    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_creds.token = "mock_token"

    list_response = {"messages": [{"id": "msg_001"}, {"id": "msg_002"}]}
    msg1_detail = {
        "id": "msg_001",
        "snippet": "Por favor confirme sua presenca...",
        "payload": {
            "headers": [
                {"name": "From", "value": "Diretoria <diretoria@empresa.com>"},
                {"name": "Subject", "value": "Reunião Geral"},
                {"name": "Date", "value": "Wed, 28 Oct 2026 10:00:00 -0300"},
            ]
        },
    }
    msg2_detail = {
        "id": "msg_002",
        "snippet": "Seu boleto esta disponivel...",
        "payload": {
            "headers": [
                {"name": "From", "value": "Financeiro <financeiro@banco.com>"},
                {"name": "Subject", "value": "Fatura do Mês"},
                {"name": "Date", "value": "Wed, 28 Oct 2026 11:30:00 -0300"},
            ]
        },
    }

    # Responses sequence: 1 for list, 2 for message details
    mock_resps = [
        io.BytesIO(json.dumps(list_response).encode("utf-8")),
        io.BytesIO(json.dumps(msg1_detail).encode("utf-8")),
        io.BytesIO(json.dumps(msg2_detail).encode("utf-8")),
    ]

    with patch("src.tools.gmail._get_credentials", return_value=mock_creds), \
         patch("urllib.request.urlopen", side_effect=mock_resps):
        res = list_unread_emails(max_results=2)
        assert res["status"] == "success"
        assert res["count"] == 2
        assert len(res["emails"]) == 2
        assert res["emails"][0]["from"] == "Diretoria"
        assert res["emails"][0]["subject"] == "Reunião Geral"
        assert res["emails"][1]["subject"] == "Fatura do Mês"
        assert "Você tem 2 novos e-mails não lidos" in res["message"]


def test_get_email_content_unauthenticated():
    """Verify get_email_content unauthenticated behavior."""
    with patch("src.tools.gmail._get_credentials", return_value=None):
        res = get_email_content("msg_123")
        assert res["status"] == "not_authenticated"


def test_get_email_content_success():
    """Verify reading full email content and generating preview."""
    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_creds.token = "mock_token"

    body_bytes = b"Prezado senhor, o projeto Aton foi aprovado com louvor pela equipe."
    b64_body = base64.urlsafe_b64encode(body_bytes).decode("utf-8")

    sample_email = {
        "id": "msg_123",
        "snippet": "Prezado senhor...",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "Ana Gerente <ana@empresa.com>"},
                {"name": "Subject", "value": "Aprovação do Projeto"},
                {"name": "Date", "value": "Wed, 28 Oct 2026 14:00:00 -0300"},
            ],
            "body": {"data": b64_body},
        },
    }

    mock_resp = io.BytesIO(json.dumps(sample_email).encode("utf-8"))

    with patch("src.tools.gmail._get_credentials", return_value=mock_creds), \
         patch("urllib.request.urlopen", return_value=mock_resp):
        res = get_email_content("msg_123")
        assert res["status"] == "success"
        assert res["from"] == "Ana Gerente"
        assert res["subject"] == "Aprovação do Projeto"
        assert "projeto Aton foi aprovado" in res["body"]
        assert "E-mail de Ana Gerente sobre 'Aprovação do Projeto'" in res["message"]


def test_dispatch_gmail_tools():
    """Test unified dispatcher routing for Gmail tools."""
    with patch("src.tools.gmail.list_unread_emails", return_value={"status": "ok"}) as mock_list:
        res = dispatch_tool("list_unread_emails", {"max_results": 3})
        assert res["status"] == "ok"
        mock_list.assert_called_once()

    with patch("src.tools.gmail.get_email_content", return_value={"status": "ok"}) as mock_get:
        res = dispatch_tool("get_email_content", {"email_id": "msg_xyz"})
        assert res["status"] == "ok"
        mock_get.assert_called_once_with(email_id="msg_xyz")

    # Error when email_id missing
    res_err = dispatch_gmail_tool("get_email_content", {})
    assert res_err["status"] == "error"

    # Unknown tool
    res_unknown = dispatch_gmail_tool("unknown_gmail_action", {})
    assert res_unknown["status"] == "error"


def test_all_aton_tools_count_with_gmail():
    """Verify ALL_ATON_TOOLS includes at least 21 tools."""
    assert len(ALL_ATON_TOOLS) >= 21
    names = [t["name"] for t in ALL_ATON_TOOLS]
    assert "list_unread_emails" in names
    assert "get_email_content" in names
