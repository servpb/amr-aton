"""Unit tests for Gmail Read-Only tools and OAuth2 integration (Phase 4)."""

import base64
import io
import json
from unittest.mock import MagicMock, patch

import pytest

from src.config import PROJECT_ROOT, settings
from src.integrations.gmail_service import (
    GMAIL_READONLY_SCOPES,
    GmailConnectionService,
    classify_gmail_http_error,
    validate_client_credentials_file,
    validate_credentials_scopes,
)
from src.tools import ALL_ATON_TOOLS, dispatch_tool
from src.tools.gmail import (
    GMAIL_FUNCTION_DECLARATIONS,
    _decode_base64_data,
    _extract_plain_text,
    authenticate_gmail,
    check_gmail_connection,
    dispatch_gmail_tool,
    get_email_content,
    list_unread_emails,
    remove_gmail_account,
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
    with patch("src.tools.gmail._get_credentials", return_value=None), \
         patch.object(GmailConnectionService, "get_all_configured_accounts", return_value=[]):
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
         patch.object(GmailConnectionService, "get_all_configured_accounts", return_value=[]), \
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
         patch.object(GmailConnectionService, "get_all_configured_accounts", return_value=[]), \
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
    with patch("src.tools.gmail._get_credentials", return_value=None), \
         patch.object(GmailConnectionService, "get_all_configured_accounts", return_value=[]):
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
         patch.object(GmailConnectionService, "get_all_configured_accounts", return_value=[]), \
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
    """Verify ALL_ATON_TOOLS includes all 4 Gmail tools."""
    assert len(ALL_ATON_TOOLS) >= 21
    names = [t["name"] for t in ALL_ATON_TOOLS]
    assert "list_unread_emails" in names
    assert "get_email_content" in names
    assert "authenticate_gmail" in names
    assert "check_gmail_connection" in names


def test_dynamic_project_root_and_settings_paths():
    """Verify PROJECT_ROOT and settings path helpers resolve to actual project root."""
    assert (PROJECT_ROOT / "pyproject.toml").exists()
    creds_file = settings.get_gmail_credentials_file()
    token_file = settings.get_gmail_token_file()
    assert creds_file.parent == PROJECT_ROOT
    assert token_file.parent == PROJECT_ROOT


def test_validate_client_credentials_file(tmp_path):
    """Verify validation of missing, malformed, web-type, and valid desktop credentials.json."""
    missing = tmp_path / "credentials.json"
    ok, code, msg = validate_client_credentials_file(missing)
    assert not ok
    assert code == "missing_credentials_file"

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not_json", encoding="utf-8")
    ok, code, _ = validate_client_credentials_file(bad_json)
    assert not ok
    assert code == "invalid_credentials_json"

    web_json = tmp_path / "web_creds.json"
    web_json.write_text(json.dumps({"web": {"client_id": "abc", "client_secret": "xyz"}}), encoding="utf-8")
    ok, code, msg = validate_client_credentials_file(web_json)
    assert not ok
    assert code == "wrong_client_type_web"
    assert "Desktop" in msg or "computador" in msg

    desktop_json = tmp_path / "desktop_creds.json"
    desktop_json.write_text(
        json.dumps({"installed": {"client_id": "id123", "client_secret": "sec456"}}),
        encoding="utf-8",
    )
    ok, code, _ = validate_client_credentials_file(desktop_json)
    assert ok
    assert code == "ok"


def test_scope_validation_and_incompatible_token_invalidation(tmp_path):
    """Verify tokens without confirmed Gmail scopes are rejected and invalidated locally."""
    creds_path = tmp_path / "credentials.json"
    token_path = tmp_path / "token.json"
    creds_path.write_text(
        json.dumps({"installed": {"client_id": "id123", "client_secret": "sec456"}}),
        encoding="utf-8",
    )
    # Token with only Calendar scope (missing gmail.readonly)
    token_path.write_text(
        json.dumps(
            {
                "token": "tok_abc",
                "refresh_token": "ref_xyz",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": "id123",
                "client_secret": "sec456",
                "scopes": ["https://www.googleapis.com/auth/calendar.readonly"],
            }
        ),
        encoding="utf-8",
    )

    service = GmailConnectionService(credentials_path=creds_path, token_path=token_path)
    creds, status_code, msg = service.get_valid_credentials()
    assert creds is None
    assert status_code == "insufficient_scopes"
    assert not token_path.exists()  # Incompatible token was invalidated


def test_revoked_token_invalidated_once_without_repeated_refresh(tmp_path):
    """Verify that when a token refresh fails with RefreshError, the token is deleted so check_connection does not retry."""
    from google.auth.exceptions import RefreshError

    creds_path = tmp_path / "credentials.json"
    token_path = tmp_path / "token.json"
    creds_path.write_text(
        json.dumps({"installed": {"client_id": "id123", "client_secret": "sec456"}}),
        encoding="utf-8",
    )
    token_path.write_text(
        json.dumps(
            {
                "token": "expired_tok",
                "refresh_token": "revoked_ref",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": "id123",
                "client_secret": "sec456",
                "scopes": GMAIL_READONLY_SCOPES,
                "expiry": "2020-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    service = GmailConnectionService(credentials_path=creds_path, token_path=token_path)

    with patch("google.oauth2.credentials.Credentials.refresh", side_effect=RefreshError("invalid_grant")) as mock_refresh:
        # First call attempts refresh, detects invalid_grant, and deletes token.json
        res1 = service.check_connection()
        assert res1["status"] == "token_revoked"
        assert not token_path.exists()
        assert mock_refresh.call_count == 1

        # Second call sees token.json was already invalidated and does NOT retry refresh
        res2 = service.check_connection()
        assert res2["status"] == "not_authenticated"
        assert mock_refresh.call_count == 1


def test_interactive_browser_authentication_flow(tmp_path):
    """Verify authenticate_interactive runs InstalledAppFlow, saves token, and verifies profile."""
    creds_path = tmp_path / "credentials.json"
    token_path = tmp_path / "token.json"
    creds_path.write_text(
        json.dumps({"installed": {"client_id": "id123", "client_secret": "sec456"}}),
        encoding="utf-8",
    )

    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_creds.expired = False
    mock_creds.token = "fresh_access_token"
    mock_creds.scopes = list(GMAIL_READONLY_SCOPES)
    mock_creds.granted_scopes = list(GMAIL_READONLY_SCOPES)
    mock_creds.has_scopes.return_value = True
    mock_creds.to_json.return_value = json.dumps(
        {
            "token": "fresh_access_token",
            "refresh_token": "fresh_refresh_token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "id123",
            "client_secret": "sec456",
            "scopes": list(GMAIL_READONLY_SCOPES),
        }
    )

    mock_flow = MagicMock()
    mock_flow.run_local_server.return_value = mock_creds

    service = GmailConnectionService(credentials_path=creds_path, token_path=token_path)

    with patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file", return_value=mock_flow), \
         patch.object(service, "check_connection", return_value={"status": "connected", "email_address": "usuario@gmail.com"}):
        result = service.authenticate_interactive(open_browser=True)
        assert result["status"] == "authenticated"
        assert result["email_address"] == "usuario@gmail.com"
        assert token_path.exists()
        mock_flow.run_local_server.assert_called_once()


def test_classify_gmail_http_error_distinguishes_403_reasons():
    """Verify HTTP 403 reasons (accessNotConfigured vs insufficientPermissions vs quota vs generic) and 401."""
    import urllib.error

    def make_http_err(code: int, payload: dict) -> urllib.error.HTTPError:
        fp = io.BytesIO(json.dumps(payload).encode("utf-8"))
        return urllib.error.HTTPError("https://gmail.googleapis.com", code, "Error", {}, fp)

    # 1. 403 accessNotConfigured -> api_disabled
    err_disabled = make_http_err(
        403,
        {
            "error": {
                "code": 403,
                "message": "Gmail API has not been used in project 123 before or it is disabled.",
                "errors": [{"reason": "accessNotConfigured"}],
            }
        },
    )
    slug, msg, inv = classify_gmail_http_error(err_disabled)
    assert slug == "api_disabled"
    assert not inv
    assert "Google Cloud Console" in msg

    # 2. 403 insufficientPermissions -> insufficient_scopes (invalidates token)
    err_scope = make_http_err(
        403,
        {
            "error": {
                "code": 403,
                "message": "Request had insufficient authentication scopes.",
                "errors": [{"reason": "insufficientPermissions"}],
            }
        },
    )
    slug, _, inv = classify_gmail_http_error(err_scope)
    assert slug == "insufficient_scopes"
    assert inv is True

    # 3. 403 rateLimitExceeded -> quota_exceeded (NOT api_disabled)
    err_quota = make_http_err(
        403,
        {
            "error": {
                "code": 403,
                "message": "User-rate limit exceeded.",
                "errors": [{"reason": "userRateLimitExceeded"}],
            }
        },
    )
    slug, _, inv = classify_gmail_http_error(err_quota)
    assert slug == "quota_exceeded"
    assert inv is False

    # 4. 403 generic forbidden -> forbidden (NOT api_disabled)
    err_generic = make_http_err(
        403,
        {
            "error": {
                "code": 403,
                "message": "Domain policy disabled access.",
                "errors": [{"reason": "domainPolicy"}],
            }
        },
    )
    slug, _, inv = classify_gmail_http_error(err_generic)
    assert slug == "forbidden"
    assert inv is False

    # 5. 401 Unauthorized -> token_revoked (invalidates token)
    err_401 = make_http_err(
        401,
        {"error": {"code": 401, "status": "UNAUTHENTICATED", "message": "Invalid Credentials"}},
    )
    slug, _, inv = classify_gmail_http_error(err_401)
    assert slug == "token_revoked"
    assert inv is True


def test_collision_safe_token_file_resolution(tmp_path):
    """Verify full 64-char SHA-256 naming and collision avoidance without overwriting another account."""
    import hashlib

    creds_path = tmp_path / "credentials.json"
    token_path = tmp_path / "token.json"
    tokens_dir = tmp_path / "tokens"
    tokens_dir.mkdir(parents=True, exist_ok=True)

    service = GmailConnectionService(
        credentials_path=creds_path,
        token_path=token_path,
        tokens_dir=tokens_dir,
    )

    email_a = "cursopb@gmail.com"
    sha_a = hashlib.sha256(email_a.encode("utf-8")).hexdigest()
    assert len(sha_a) == 64

    # Normal resolution uses full 64-char SHA-256
    acc_id, acc_path = service._resolve_collision_safe_token_file(email_a, {})
    assert acc_id == f"gmail_acct_{sha_a}"
    assert acc_path == tokens_dir / f"gmail_acct_{sha_a}.json"

    # Simulate an improbable hash collision where another email already occupies gmail_acct_<sha_a>.json on disk
    acc_path.write_text(json.dumps({"account_email": "outro_email@gmail.com"}), encoding="utf-8")
    colliding_index = {
        "outro_email@gmail.com": {
            "account_id": f"gmail_acct_{sha_a}",
            "token_file": f"gmail_acct_{sha_a}.json",
        }
    }

    safe_id, safe_path = service._resolve_collision_safe_token_file(email_a, colliding_index)
    assert safe_id == f"gmail_acct_{sha_a}_1"
    assert safe_path == tokens_dir / f"gmail_acct_{sha_a}_1.json"
    # Original file remains untouched
    assert json.loads(acc_path.read_text(encoding="utf-8"))["account_email"] == "outro_email@gmail.com"


def test_atomic_legacy_token_migration_and_preservation_on_error(tmp_path):
    """Verify legacy token.json is preserved on API failure and atomically migrated once profile is confirmed."""
    creds_path = tmp_path / "credentials.json"
    token_path = tmp_path / "token.json"
    tokens_dir = tmp_path / "tokens"

    creds_path.write_text(
        json.dumps({"installed": {"client_id": "id123", "client_secret": "sec456"}}),
        encoding="utf-8",
    )
    token_path.write_text(
        json.dumps(
            {
                "token": "valid_legacy_tok",
                "refresh_token": "valid_legacy_ref",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": "id123",
                "client_secret": "sec456",
                "scopes": list(GMAIL_READONLY_SCOPES),
                "expiry": "2099-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    service = GmailConnectionService(
        credentials_path=creds_path,
        token_path=token_path,
        tokens_dir=tokens_dir,
    )

    # 1. If profile query fails (e.g. offline), legacy token.json MUST be preserved
    with patch.object(service, "_fetch_profile_with_token", return_value=(None, "network_error", "Offline")):
        migrated = service.migrate_legacy_token_if_needed()
        assert migrated is None
        assert token_path.exists()
        assert not service.index_path.exists()

    # 2. When profile query confirms actual emailAddress, migrate atomically and delete legacy token.json
    with patch.object(
        service,
        "_fetch_profile_with_token",
        return_value=({"emailAddress": "servpb@gmail.com", "messagesTotal": 42}, "success", "OK"),
    ):
        migrated = service.migrate_legacy_token_if_needed()
        assert migrated == "servpb@gmail.com"
        assert not token_path.exists()
        assert service.index_path.exists()
        accounts = service._load_accounts_index()
        assert "servpb@gmail.com" in accounts
        migrated_file = tokens_dir / accounts["servpb@gmail.com"]["token_file"]
        assert migrated_file.exists()


def test_authenticate_interactive_expected_email_mismatch(tmp_path):
    """Verify authenticate_interactive rejects and does not save when authorized email differs from expected_email."""
    creds_path = tmp_path / "credentials.json"
    token_path = tmp_path / "token.json"
    tokens_dir = tmp_path / "tokens"
    creds_path.write_text(
        json.dumps({"installed": {"client_id": "id123", "client_secret": "sec456"}}),
        encoding="utf-8",
    )

    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_creds.expired = False
    mock_creds.token = "tok_wrong_user"
    mock_creds.scopes = list(GMAIL_READONLY_SCOPES)
    mock_creds.granted_scopes = list(GMAIL_READONLY_SCOPES)
    mock_creds.has_scopes.return_value = True
    mock_creds.to_json.return_value = json.dumps(
        {
            "token": "tok_wrong_user",
            "refresh_token": "ref_wrong_user",
            "scopes": list(GMAIL_READONLY_SCOPES),
        }
    )

    mock_flow = MagicMock()
    mock_flow.run_local_server.return_value = mock_creds

    service = GmailConnectionService(
        credentials_path=creds_path,
        token_path=token_path,
        tokens_dir=tokens_dir,
    )

    with patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file", return_value=mock_flow), \
         patch.object(
             service,
             "_fetch_profile_with_token",
             return_value=({"emailAddress": "servpb@gmail.com"}, "success", "OK"),
         ):
        res = service.authenticate_interactive(open_browser=True, expected_email="cursopb@gmail.com")
        assert res["status"] == "account_mismatch"
        assert res["expected_email"] == "cursopb@gmail.com"
        assert res["authorized_email"] == "servpb@gmail.com"
        # Ensure nothing was saved to index
        assert service._load_accounts_index() == {}


def test_multi_account_list_unread_emails_fault_isolation_and_total_cap():
    """Verify unified list_unread_emails isolates per-account failures, tags account, sorts by recency, and caps total to max_results."""
    mock_service = MagicMock()
    mock_service.get_all_configured_accounts.return_value = [
        "servpb@gmail.com",
        "cursopb@gmail.com",
        "revogada@gmail.com",
    ]

    creds_ok_1 = MagicMock(valid=True, token="tok_1")
    creds_ok_2 = MagicMock(valid=True, token="tok_2")

    def fake_get_creds(account=None):
        if account == "servpb@gmail.com":
            return creds_ok_1
        if account == "cursopb@gmail.com":
            return creds_ok_2
        return None  # revogada@gmail.com fails authentication

    def fake_fetch(creds, max_results, query, account_label=None):
        if account_label == "servpb@gmail.com":
            return (
                [
                    {
                        "id": "m1",
                        "from": "Alice",
                        "full_from": "Alice <alice@test.com>",
                        "subject": "Assunto Antigo",
                        "date": "28 Oct",
                        "snippet": "...",
                        "internal_date": 1000,
                        "account": "servpb@gmail.com",
                    },
                    {
                        "id": "m2",
                        "from": "Bob",
                        "full_from": "Bob <bob@test.com>",
                        "subject": "Assunto Mais Recente",
                        "date": "29 Oct",
                        "snippet": "...",
                        "internal_date": 3000,
                        "account": "servpb@gmail.com",
                    },
                ],
                "success",
                "",
            )
        if account_label == "cursopb@gmail.com":
            return (
                [
                    {
                        "id": "m3",
                        "from": "Carlos",
                        "full_from": "Carlos <carlos@test.com>",
                        "subject": "Assunto Intermediario",
                        "date": "29 Oct",
                        "snippet": "...",
                        "internal_date": 2000,
                        "account": "cursopb@gmail.com",
                    }
                ],
                "success",
                "",
            )
        return [], "error", "Falha"

    with patch("src.tools.gmail.get_gmail_service", return_value=mock_service), \
         patch("src.tools.gmail._get_credentials", side_effect=fake_get_creds), \
         patch("src.tools.gmail._fetch_messages_for_credential", side_effect=fake_fetch):
        res = list_unread_emails(max_results=2)
        assert res["status"] == "success"
        # Total cap is 2 even though 3 messages exist across the 2 active accounts
        assert res["count"] == 2
        assert len(res["emails"]) == 2
        # Sorted by internal_date descending: m2 (3000) then m3 (2000)
        assert res["emails"][0]["id"] == "m2"
        assert res["emails"][0]["account"] == "servpb@gmail.com"
        assert res["emails"][1]["id"] == "m3"
        assert res["emails"][1]["account"] == "cursopb@gmail.com"
        # Fault isolation recorded revogada@gmail.com without losing servpb and cursopb
        assert len(res["failed_accounts"]) == 1
        assert res["failed_accounts"][0]["account"] == "revogada@gmail.com"
        assert "revogada@gmail.com" in res["message"]


def test_multi_account_get_email_content_unique_and_ambiguous():
    """Verify get_email_content searches across accounts when account=None and detects ambiguity."""
    import urllib.error

    mock_service = MagicMock()
    mock_service.get_all_configured_accounts.return_value = [
        "servpb@gmail.com",
        "cursopb@gmail.com",
    ]
    creds_1 = MagicMock(valid=True, token="tok_1")
    creds_2 = MagicMock(valid=True, token="tok_2")

    b64_body = base64.urlsafe_b64encode(b"Conteudo exclusivo").decode("utf-8")
    msg_payload = {
        "id": "msg_shared",
        "snippet": "Conteudo...",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "Suporte <suporte@teste.com>"},
                {"name": "Subject", "value": "Teste Multi-Conta"},
            ],
            "body": {"data": b64_body},
        },
    }

    # Case 1: Found in only 1 account (404 in the first, 200 in the second)
    err_404 = urllib.error.HTTPError("https://gmail.googleapis.com", 404, "Not Found", {}, io.BytesIO(b"{}"))
    resp_200 = io.BytesIO(json.dumps(msg_payload).encode("utf-8"))

    with patch("src.tools.gmail.get_gmail_service", return_value=mock_service), \
         patch("src.tools.gmail._get_credentials", side_effect=[creds_1, creds_2]), \
         patch("urllib.request.urlopen", side_effect=[err_404, resp_200]):
        res = get_email_content("msg_unique")
        assert res["status"] == "success"
        assert res["account"] == "cursopb@gmail.com"
        assert "Conteudo exclusivo" in res["body"]

    # Case 2: Found in BOTH accounts -> returns ambiguous_account
    resp_200_a = io.BytesIO(json.dumps(msg_payload).encode("utf-8"))
    resp_200_b = io.BytesIO(json.dumps(msg_payload).encode("utf-8"))

    with patch("src.tools.gmail.get_gmail_service", return_value=mock_service), \
         patch("src.tools.gmail._get_credentials", side_effect=[creds_1, creds_2]), \
         patch("urllib.request.urlopen", side_effect=[resp_200_a, resp_200_b]):
        res_amb = get_email_content("msg_shared")
        assert res_amb["status"] == "ambiguous_account"
        assert set(res_amb["matching_accounts"]) == {"servpb@gmail.com", "cursopb@gmail.com"}


def test_remove_gmail_account_local_and_remote_revoke(tmp_path):
    """Verify remove_account removes local token & index entry and supports optional remote revocation."""
    creds_path = tmp_path / "credentials.json"
    token_path = tmp_path / "token.json"
    tokens_dir = tmp_path / "tokens"
    service = GmailConnectionService(
        credentials_path=creds_path,
        token_path=token_path,
        tokens_dir=tokens_dir,
    )

    mock_creds = MagicMock()
    mock_creds.to_json.return_value = json.dumps(
        {
            "token": "tok_123",
            "refresh_token": "ref_123",
            "scopes": list(GMAIL_READONLY_SCOPES),
        }
    )

    saved_file = service._save_account_token(mock_creds, "cursopb@gmail.com")
    assert saved_file.exists()
    assert "cursopb@gmail.com" in service._load_accounts_index()

    # Local-only removal (revoke_remote=False)
    res_local = service.remove_account("cursopb@gmail.com", revoke_remote=False)
    assert res_local["status"] == "removed"
    assert res_local["removed_account"] == "cursopb@gmail.com"
    assert res_local["remote_revoked"] is False
    assert not saved_file.exists()
    assert "cursopb@gmail.com" not in service._load_accounts_index()
    assert "não revoga a autorização na sua Conta Google" in res_local["message"]


