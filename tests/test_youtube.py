"""Unit and integration tests for Multi-Account & Multi-Channel YouTube Service and Tools."""

import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch
import urllib.error

import pytest

from src.audio.wake_word import WakeWordDetector
from src.integrations.youtube_service import (
    ConfirmationState,
    KNOWN_TARGET_CHANNEL_IDS,
    YOUTUBE_MANAGE_SCOPES,
    YOUTUBE_READONLY_SCOPES,
    YouTubeConfirmationManager,
    YouTubeConnectionService,
    classify_youtube_http_error,
)
import src.tools.youtube as youtube_tools


# =============================================================================
# Helpers & Fixtures
# =============================================================================


def _make_valid_client_secrets(path: Path) -> Path:
    payload = {
        "installed": {
            "client_id": "1234567890-mock.apps.googleusercontent.com",
            "project_id": "aton-mock-project",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_secret": "GOCSPX-mocksecret",
            "redirect_uris": ["http://localhost"],
        }
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _seed_channel_entry(
    service: YouTubeConnectionService,
    account_email: str,
    channel_id: str,
    channel_title: str,
    access_mode: str = "manage",
    custom_url: str = "@canal",
    uploads_playlist_id: str = "UU_UPLOADS_123",
) -> str:
    scopes = YOUTUBE_MANAGE_SCOPES if access_mode == "manage" else YOUTUBE_READONLY_SCOPES
    mock_creds = MagicMock()
    mock_creds.token = f"access-tok-{account_email}-{channel_id}"
    mock_creds.refresh_token = f"refresh-tok-{account_email}-{channel_id}"
    mock_creds.scopes = list(scopes)
    mock_creds.valid = True
    mock_creds.expired = False
    mock_creds.to_json.return_value = json.dumps({
        "token": mock_creds.token,
        "refresh_token": mock_creds.refresh_token,
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "123.apps.googleusercontent.com",
        "client_secret": "secret",
        "scopes": list(scopes),
        "expiry": "2099-01-01T00:00:00Z",
    })

    entry_key, _ = service._save_channel_entry_token(
        creds=mock_creds,
        account_email=account_email,
        channel_info={
            "channel_id": channel_id,
            "title": channel_title,
            "custom_url": custom_url,
            "uploads_playlist_id": uploads_playlist_id,
            "subscriber_count": 1500,
            "video_count": 42,
            "view_count": 98000,
        },
        access_mode=access_mode,
        scopes=list(scopes),
    )
    return str(entry_key)


def _make_http_error(code: int, reason: str, message: str, url: str = "https://www.googleapis.com/youtube/v3/videos") -> urllib.error.HTTPError:
    body = json.dumps({
        "error": {
            "code": code,
            "message": message,
            "errors": [{"reason": reason, "message": message}],
        }
    }).encode("utf-8")
    return urllib.error.HTTPError(url=url, code=code, msg=message, hdrs=None, fp=io.BytesIO(body))


# =============================================================================
# 1. Multi-Account & Multi-Channel Storage Without Overwriting + Gmail Isolation
# =============================================================================


def test_same_account_multiple_channels_stored_separately_and_gmail_untouched(tmp_path: Path):
    creds_file = _make_valid_client_secrets(tmp_path / "credentials.json")
    tokens_dir = tmp_path / "tokens"
    tokens_dir.mkdir()

    # Pre-existing Gmail index & token must remain 100% untouched
    gmail_index = tokens_dir / "accounts_index.json"
    gmail_token = tokens_dir / "gmail_acct_existing.json"
    gmail_index.write_text('{"accounts": {"servpb@gmail.com": {"token_file": "gmail_acct_existing.json"}}}', encoding="utf-8")
    gmail_token.write_text('{"token": "gmail-secret"}', encoding="utf-8")

    service = YouTubeConnectionService(credentials_path=creds_file, tokens_dir=tokens_dir)

    # Authorize 2 different Brand Account channels under cursopb@gmail.com + 2 channels under servpb@gmail.com
    k1 = _seed_channel_entry(service, "cursopb@gmail.com", "UC_CURSO_1", "Canal Curso Principal")
    k2 = _seed_channel_entry(service, "cursopb@gmail.com", "UC_CURSO_2", "Canal Curso Marca B")
    k3 = _seed_channel_entry(service, "servpb@gmail.com", "UC_SERV_1", "Canal Serv Principal")
    k4 = _seed_channel_entry(service, "servpb@gmail.com", "UCYCmXtIR-tbWCyrwbLdczyA", "Alta Restauração")

    assert k1 != k2 != k3 != k4

    all_channels = service.get_all_configured_channels()
    assert len(all_channels) == 4

    token_files = {c["token_file"] for c in all_channels}
    assert len(token_files) == 4
    for tf in token_files:
        assert tf.startswith("youtube_acct_")
        assert (tokens_dir / tf).exists()

    # Verify Gmail files were completely untouched
    assert json.loads(gmail_index.read_text(encoding="utf-8"))["accounts"]["servpb@gmail.com"]["token_file"] == "gmail_acct_existing.json"
    assert json.loads(gmail_token.read_text(encoding="utf-8"))["token"] == "gmail-secret"


def test_expected_email_mismatch_cancels_without_overwriting(tmp_path: Path):
    creds_file = _make_valid_client_secrets(tmp_path / "credentials.json")
    tokens_dir = tmp_path / "tokens"
    service = YouTubeConnectionService(credentials_path=creds_file, tokens_dir=tokens_dir)

    # Existing valid channel under cursopb@gmail.com
    _seed_channel_entry(service, "cursopb@gmail.com", "UC_CURSO_1", "Canal Curso Original")

    mock_creds = MagicMock()
    mock_creds.token = "new-tok"
    mock_creds.scopes = list(YOUTUBE_MANAGE_SCOPES)

    with patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file") as mock_flow_cls, \
         patch.object(service, "_fetch_userinfo_email", return_value=("outraconta@gmail.com", "success", "OK")):
        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = mock_creds
        mock_flow_cls.return_value = mock_flow

        res = service.authenticate_interactive(
            open_browser=False,
            expected_email="cursopb@gmail.com",
            mode="manage",
        )

    assert res["status"] == "account_mismatch"
    assert res["expected_email"] == "cursopb@gmail.com"
    assert res["authorized_email"] == "outraconta@gmail.com"

    # Original channel token is still intact and no new entry was added
    channels = service.get_all_configured_channels()
    assert len(channels) == 1
    assert channels[0]["account_email"] == "cursopb@gmail.com"
    assert channels[0]["channel_title"] == "Canal Curso Original"


# =============================================================================
# 2. Safe Mode Transition (No Automatic Remote Revoke on Downgrade) & Removal
# =============================================================================


def test_downgrade_manage_to_readonly_does_not_auto_revoke_remote_token(tmp_path: Path):
    creds_file = _make_valid_client_secrets(tmp_path / "credentials.json")
    tokens_dir = tmp_path / "tokens"
    service = YouTubeConnectionService(credentials_path=creds_file, tokens_dir=tokens_dir)

    _seed_channel_entry(service, "cursopb@gmail.com", "UC_CURSO_1", "Canal Curso", access_mode="manage")

    mock_readonly_creds = MagicMock()
    mock_readonly_creds.token = "readonly-access-token"
    mock_readonly_creds.refresh_token = "readonly-refresh-token"
    mock_readonly_creds.scopes = list(YOUTUBE_READONLY_SCOPES)
    mock_readonly_creds.to_json.return_value = json.dumps({
        "token": "readonly-access-token",
        "refresh_token": "readonly-refresh-token",
        "scopes": list(YOUTUBE_READONLY_SCOPES),
        "expiry": "2099-01-01T00:00:00Z",
    })

    discovered = [{
        "channel_id": "UC_CURSO_1",
        "title": "Canal Curso",
        "custom_url": "@canalcurso",
        "uploads_playlist_id": "UU_CURSO_1",
        "subscriber_count": 2000,
        "video_count": 50,
        "view_count": 100000,
    }]

    with patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file") as mock_flow_cls, \
         patch.object(service, "_fetch_userinfo_email", return_value=("cursopb@gmail.com", "success", "OK")), \
         patch.object(service, "_discover_mine_channels_with_token", return_value=(discovered, "success", "OK")), \
         patch("urllib.request.urlopen") as mock_urlopen:
        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = mock_readonly_creds
        mock_flow_cls.return_value = mock_flow

        res = service.authenticate_interactive(
            open_browser=False,
            expected_email="cursopb@gmail.com",
            mode="readonly",
        )

    assert res["status"] == "authenticated"
    assert res["access_mode"] == "readonly"
    assert "sem acionar" in res["message"] or "não é acionada automaticamente" in res["message"]
    # Ensure oauth2.googleapis.com/revoke was NEVER called during downgrade
    mock_urlopen.assert_not_called()

    channels = service.get_all_configured_channels()
    assert len(channels) == 1
    assert channels[0]["access_mode"] == "readonly"


def test_explicit_remove_account_local_and_remote_revoke(tmp_path: Path):
    creds_file = _make_valid_client_secrets(tmp_path / "credentials.json")
    tokens_dir = tmp_path / "tokens"
    service = YouTubeConnectionService(credentials_path=creds_file, tokens_dir=tokens_dir)

    _seed_channel_entry(service, "cursopb@gmail.com", "UC_CURSO_1", "Canal Curso 1")
    _seed_channel_entry(service, "servpb@gmail.com", "UC_SERV_1", "Canal Serv 1")

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        res = service.remove_account_or_channel("UC_CURSO_1", revoke_remote=True)

    assert res["status"] == "removed"
    assert res["remote_revoked"] is True
    assert res["remaining_count"] == 1
    assert mock_urlopen.call_count == 1


# =============================================================================
# 3. Target Channel UCYCmXtIR-tbWCyrwbLdczyA Discovery & Public Check
# =============================================================================


def test_target_channel_check_when_not_authorized_vs_authorized(tmp_path: Path):
    creds_file = _make_valid_client_secrets(tmp_path / "credentials.json")
    tokens_dir = tmp_path / "tokens"
    service = YouTubeConnectionService(credentials_path=creds_file, tokens_dir=tokens_dir)

    _seed_channel_entry(service, "cursopb@gmail.com", "UC_OTHER_999", "Outro Canal")

    # Mock channels.list(mine=True) returning only UC_OTHER_999, and public lookup returning UCYCmXtIR-tbWCyrwbLdczyA
    def fake_request_data_api(endpoint, entry_key, **kwargs):
        q = kwargs.get("query_params", {})
        if q.get("mine") == "true":
            return {
                "items": [{
                    "id": "UC_OTHER_999",
                    "snippet": {"title": "Outro Canal", "customUrl": "@outro"},
                    "statistics": {"subscriberCount": "100", "videoCount": "10", "viewCount": "1000"},
                    "contentDetails": {"relatedPlaylists": {"uploads": "UU_OTHER_999"}},
                }]
            }, "success", "OK"
        if q.get("id") == KNOWN_TARGET_CHANNEL_IDS[0]:
            return {
                "items": [{
                    "id": KNOWN_TARGET_CHANNEL_IDS[0],
                    "snippet": {"title": "Canal Alvo Público", "customUrl": "@canalalvo"},
                    "statistics": {"subscriberCount": "5500", "videoCount": "88", "viewCount": "250000"},
                }]
            }, "success", "OK"
        return {"items": []}, "success", "OK"

    with patch.object(service, "request_data_api", side_effect=fake_request_data_api):
        report_unauth = service.check_connection_and_channels()

    assert report_unauth["status"] == "connected"
    assert report_unauth["target_channel_check"]["channel_id"] == KNOWN_TARGET_CHANNEL_IDS[0]
    assert report_unauth["target_channel_check"]["authorized"] is False
    assert report_unauth["target_channel_check"]["public_title"] == "Canal Alvo Público"
    assert "NÃO está autorizado" in report_unauth["target_channel_check"]["message"]

    # Now authorize UCYCmXtIR-tbWCyrwbLdczyA under servpb@gmail.com
    _seed_channel_entry(service, "servpb@gmail.com", KNOWN_TARGET_CHANNEL_IDS[0], "Canal Alvo Autorizado")

    def fake_request_data_api_both(endpoint, entry_key, **kwargs):
        if KNOWN_TARGET_CHANNEL_IDS[0] in entry_key:
            return {
                "items": [{
                    "id": KNOWN_TARGET_CHANNEL_IDS[0],
                    "snippet": {"title": "Canal Alvo Autorizado", "customUrl": "@canalalvo"},
                    "statistics": {"subscriberCount": "5500", "videoCount": "88", "viewCount": "250000"},
                }]
            }, "success", "OK"
        return {
            "items": [{
                "id": "UC_OTHER_999",
                "snippet": {"title": "Outro Canal", "customUrl": "@outro"},
                "statistics": {"subscriberCount": "100", "videoCount": "10", "viewCount": "1000"},
            }]
        }, "success", "OK"

    with patch.object(service, "request_data_api", side_effect=fake_request_data_api_both):
        report_auth = service.check_connection_and_channels()

    assert report_auth["target_channel_check"]["authorized"] is True
    assert report_auth["target_channel_check"]["account_email"] == "servpb@gmail.com"


# =============================================================================
# 4. Data API v3 Totals vs Analytics API v2 Report & Error Classification
# =============================================================================


def test_get_youtube_channel_stats_separates_data_and_analytics_and_handles_partial_failure(tmp_path: Path, monkeypatch):
    creds_file = _make_valid_client_secrets(tmp_path / "credentials.json")
    tokens_dir = tmp_path / "tokens"
    service = YouTubeConnectionService(credentials_path=creds_file, tokens_dir=tokens_dir)
    _seed_channel_entry(service, "servpb@gmail.com", "UCYCmXtIR-tbWCyrwbLdczyA", "Alta Restauração")
    monkeypatch.setattr(youtube_tools, "get_youtube_service", lambda: service)

    data_api_payload = {
        "items": [{
            "id": "UCYCmXtIR-tbWCyrwbLdczyA",
            "snippet": {"title": "Alta Restauração", "customUrl": "@altarestauracao"},
            "statistics": {
                "subscriberCount": "12400",
                "hiddenSubscriberCount": False,
                "viewCount": "890000",
                "videoCount": "135",
            },
        }]
    }
    analytics_payload = {
        "columnHeaders": [
            {"name": "views"},
            {"name": "estimatedMinutesWatched"},
            {"name": "averageViewDuration"},
            {"name": "subscribersGained"},
            {"name": "subscribersLost"},
            {"name": "likes"},
            {"name": "comments"},
        ],
        "rows": [[15200, 64000, 252, 310, 18, 1450, 92]],
    }

    with patch.object(service, "request_data_api", return_value=(data_api_payload, "success", "OK")), \
         patch.object(service, "request_analytics_api", return_value=(analytics_payload, "success", "OK")):
        res = youtube_tools.get_youtube_channel_stats(
            channel="UCYCmXtIR-tbWCyrwbLdczyA",
            start_date="2026-10-01",
            end_date="2026-10-28",
        )

    assert res["status"] == "success"
    assert res["timezone"] == "America/Sao_Paulo"
    assert res["period"] == {"start_date": "2026-10-01", "end_date": "2026-10-28"}
    assert res["data_api_totals"]["subscriber_count"] == 12400
    assert res["data_api_totals"]["total_view_count"] == 890000
    assert res["analytics_api_report"]["available"] is True
    assert res["analytics_api_report"]["metrics"]["views"] == 15200
    # 'shares' was omitted in mock headers -> must appear in unavailable_metrics
    assert "shares" in res["analytics_api_report"]["unavailable_metrics"]
    assert "atraso de processamento variável" in res["analytics_api_report"]["latency_notice"]

    # Now simulate Analytics 403 forbidden while Data API v3 succeeds
    with patch.object(service, "request_data_api", return_value=(data_api_payload, "success", "OK")), \
         patch.object(
             service,
             "request_analytics_api",
             return_value=(None, "analytics_permission_denied", "Sem permissão de proprietário para relatórios."),
         ):
        res_partial = youtube_tools.get_youtube_channel_stats(channel="UCYCmXtIR-tbWCyrwbLdczyA")

    assert res_partial["status"] == "success"
    assert res_partial["data_api_totals"]["subscriber_count"] == 12400
    assert res_partial["analytics_api_report"]["available"] is False
    assert res_partial["analytics_api_report"]["error_code"] == "analytics_permission_denied"


def test_classify_youtube_http_errors_distinguishes_data_vs_analytics_and_quota():
    err_data_disabled = _make_http_error(403, "accessNotConfigured", "YouTube Data API v3 has not been used in project")
    slug1, msg1, inv1 = classify_youtube_http_error(err_data_disabled, api_source="data_v3")
    assert slug1 == "youtube_data_api_disabled"
    assert "YouTube Data API v3" in msg1
    assert inv1 is False

    err_ana_disabled = _make_http_error(403, "accessNotConfigured", "YouTube Analytics API has not been used")
    slug2, msg2, inv2 = classify_youtube_http_error(err_ana_disabled, api_source="analytics_v2")
    assert slug2 == "youtube_analytics_api_disabled"
    assert "YouTube Analytics API v2" in msg2
    assert inv2 is False

    err_quota = _make_http_error(403, "quotaExceeded", "The request cannot be completed because you have exceeded your quota.")
    slug3, msg3, inv3 = classify_youtube_http_error(err_quota, api_source="data_v3", operation_name="videos.insert")
    assert slug3 == "youtube_quota_exceeded"
    assert "1600" in msg3
    assert inv3 is False


# =============================================================================
# 5. Read-Only Comments Scope & Video Channel Ownership / Ambiguity Checks
# =============================================================================


def test_list_youtube_comments_works_with_readonly_scope(tmp_path: Path, monkeypatch):
    creds_file = _make_valid_client_secrets(tmp_path / "credentials.json")
    tokens_dir = tmp_path / "tokens"
    service = YouTubeConnectionService(credentials_path=creds_file, tokens_dir=tokens_dir)
    _seed_channel_entry(
        service,
        "cursopb@gmail.com",
        "UC_CURSO_1",
        "Canal Curso Leitura",
        access_mode="readonly",
    )
    monkeypatch.setattr(youtube_tools, "get_youtube_service", lambda: service)

    def fake_urlopen(req, timeout=15):
        url = req.full_url
        resp = MagicMock()
        resp.__enter__.return_value = resp
        if "/youtube/v3/videos" in url:
            resp.read.return_value = json.dumps({
                "items": [{
                    "id": "VID_123",
                    "snippet": {"title": "Aula 01", "channelId": "UC_CURSO_1", "channelTitle": "Canal Curso Leitura"},
                    "status": {"privacyStatus": "public"},
                    "statistics": {"viewCount": "500"},
                }]
            }).encode("utf-8")
        elif "/youtube/v3/commentThreads" in url:
            resp.read.return_value = json.dumps({
                "items": [{
                    "id": "THREAD_1",
                    "snippet": {
                        "totalReplyCount": 1,
                        "topLevelComment": {
                            "id": "COMM_1",
                            "snippet": {
                                "authorDisplayName": "Aluno João",
                                "textDisplay": "Excelente aula!",
                                "likeCount": 5,
                                "publishedAt": "2026-10-28T12:00:00Z",
                            },
                        },
                    },
                }]
            }).encode("utf-8")
        return resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        res = youtube_tools.list_youtube_comments(video_id="VID_123", channel="UC_CURSO_1")

    assert res["status"] == "success"
    assert res["count"] == 1
    assert res["comments"][0]["author"] == "Aluno João"


def test_video_ownership_channel_mismatch_and_ambiguous_channel(tmp_path: Path, monkeypatch):
    creds_file = _make_valid_client_secrets(tmp_path / "credentials.json")
    tokens_dir = tmp_path / "tokens"
    service = YouTubeConnectionService(credentials_path=creds_file, tokens_dir=tokens_dir)

    # Connect two channels
    _seed_channel_entry(service, "cursopb@gmail.com", "UC_CANAL_A", "Canal A")
    _seed_channel_entry(service, "servpb@gmail.com", "UC_CANAL_B", "Canal B")
    monkeypatch.setattr(youtube_tools, "get_youtube_service", lambda: service)

    # Video belongs to UC_CANAL_B, but caller attempts to update it specifying UC_CANAL_A
    video_b_payload = {
        "items": [{
            "id": "VID_OF_B",
            "snippet": {"title": "Vídeo do Canal B", "channelId": "UC_CANAL_B", "channelTitle": "Canal B"},
            "status": {"privacyStatus": "public"},
        }]
    }
    with patch.object(service, "request_data_api", return_value=(video_b_payload, "success", "OK")):
        mismatch_res = youtube_tools.update_youtube_video_metadata(
            video_id="VID_OF_B",
            channel="UC_CANAL_A",
            title="Tentativa no Canal Errado",
        )
    assert mismatch_res["status"] == "channel_mismatch"
    assert "UC_CANAL_B" in mismatch_res["message"]

    # Now connect UC_CANAL_B under a second account as well (two accounts managing the same Brand Account channel)
    _seed_channel_entry(service, "cursopb@gmail.com", "UC_CANAL_B", "Canal B")
    with patch.object(service, "request_data_api", return_value=(video_b_payload, "success", "OK")):
        ambig_res = youtube_tools.update_youtube_video_metadata(
            video_id="VID_OF_B",
            channel=None,
            title="Sem Canal Especificado",
        )
    assert ambig_res["status"] == "ambiguous_channel"


# =============================================================================
# 6. Server-Side Confirmation State Machine (All Edge Cases)
# =============================================================================


def test_confirmation_blocks_immediate_model_second_call_without_user_affirmation(tmp_path: Path, monkeypatch):
    creds_file = _make_valid_client_secrets(tmp_path / "credentials.json")
    tokens_dir = tmp_path / "tokens"
    service = YouTubeConnectionService(credentials_path=creds_file, tokens_dir=tokens_dir)
    _seed_channel_entry(service, "cursopb@gmail.com", "UC_CURSO_1", "Canal Curso")
    monkeypatch.setattr(youtube_tools, "get_youtube_service", lambda: service)

    # Step 1: Model requests comment reply without token -> gets proposal & confirmation_token
    step1 = youtube_tools.reply_to_youtube_comment(
        comment_id="COMM_99",
        reply_text="Obrigado pelo comentário!",
        channel="UC_CURSO_1",
    )
    assert step1["status"] == "confirmation_required"
    token = step1["confirmation_token"]

    # Step 2 (Attack / Hallucination): Model immediately calls Step 2 with the token BEFORE user says "Sim"
    step2_premature = youtube_tools.reply_to_youtube_comment(
        comment_id="COMM_99",
        reply_text="Obrigado pelo comentário!",
        channel="UC_CURSO_1",
        confirmation_token=token,
    )
    assert step2_premature["status"] == "unverified_user_confirmation"

    # Now server marks summary presented and records a genuine user affirmative turn AFTER summary presentation
    service.confirmations.mark_summary_presented(token)
    affirmed, aff_code, _ = service.confirmations.record_user_affirmative_turn(source="voice")
    assert affirmed is True
    assert aff_code == "user_affirmed"

    with patch.object(service, "request_data_api", return_value=({"id": "REPLY_1"}, "success", "OK")):
        step2_ok = youtube_tools.reply_to_youtube_comment(
            comment_id="COMM_99",
            reply_text="Obrigado pelo comentário!",
            channel="UC_CURSO_1",
            confirmation_token=token,
        )
    assert step2_ok["status"] == "replied"
    assert step2_ok["reply_comment_id"] == "REPLY_1"

    # Reusing the same token a second time must fail (CONSUMED terminal state)
    step3_reuse = youtube_tools.reply_to_youtube_comment(
        comment_id="COMM_99",
        reply_text="Obrigado pelo comentário!",
        channel="UC_CURSO_1",
        confirmation_token=token,
    )
    assert step3_reuse["status"] == "token_consumed"


def test_speech_interruption_invalidates_confirmation_permanently():
    mgr = YouTubeConfirmationManager()
    rec = mgr.create_proposal(
        operation="reply_to_youtube_comment",
        channel_id="UC_1",
        channel_title="Canal 1",
        account_email="cursopb@gmail.com",
        payload={"comment_id": "C1", "reply_text": "Oi"},
        summary_pt_br="Resumo de teste",
    )
    mgr.notify_voice_playback_started()
    # User interrupts Aton while reading the summary
    mgr.mark_speech_interrupted()
    assert rec.state == ConfirmationState.SPEECH_INTERRUPTED

    # Even if playback completes or user says "Sim" afterwards, it cannot transition to USER_AFFIRMED
    mgr.notify_voice_playback_completed_cleanly()
    ok_aff, code_aff, _ = mgr.record_user_affirmative_turn(source="voice")
    assert ok_aff is False
    assert code_aff == "no_active_proposal"

    ok_ver, code_ver, _ = mgr.verify_and_consume(
        rec.confirmation_token,
        "reply_to_youtube_comment",
        {"comment_id": "C1", "reply_text": "Oi"},
    )
    assert ok_ver is False
    assert code_ver == "token_speech_interrupted"


def test_new_proposal_supersedes_already_user_affirmed_token():
    mgr = YouTubeConfirmationManager()
    rec1 = mgr.create_proposal(
        operation="reply_to_youtube_comment",
        channel_id="UC_1",
        channel_title="Canal 1",
        account_email="cursopb@gmail.com",
        payload={"comment_id": "C1", "reply_text": "Primeira resposta"},
        summary_pt_br="Resumo 1",
    )
    mgr.mark_summary_presented(rec1.confirmation_token)
    ok1, _, _ = mgr.record_user_affirmative_turn(source="voice")
    assert ok1 is True
    assert rec1.state == ConfirmationState.USER_AFFIRMED

    # Before rec1 is consumed, a second proposal rec2 is created -> rec1 MUST become SUPERSEDED
    rec2 = mgr.create_proposal(
        operation="reply_to_youtube_comment",
        channel_id="UC_1",
        channel_title="Canal 1",
        account_email="cursopb@gmail.com",
        payload={"comment_id": "C2", "reply_text": "Segunda resposta"},
        summary_pt_br="Resumo 2",
    )
    assert rec1.state == ConfirmationState.SUPERSEDED

    # Attempting to execute rec1 with its old token must now fail with token_superseded
    ok_old, code_old, _ = mgr.verify_and_consume(
        rec1.confirmation_token,
        "reply_to_youtube_comment",
        {"comment_id": "C1", "reply_text": "Primeira resposta"},
    )
    assert ok_old is False
    assert code_old == "token_superseded"

    # And rec2 has NOT inherited rec1's affirmation (still awaiting summary presentation & new affirmation)
    ok_new_premature, code_new_premature, _ = mgr.verify_and_consume(
        rec2.confirmation_token,
        "reply_to_youtube_comment",
        {"comment_id": "C2", "reply_text": "Segunda resposta"},
    )
    assert ok_new_premature is False
    assert code_new_premature == "unverified_user_confirmation"


def test_confirmation_expiration_cancellation_and_service_restart():
    clock = [1000.0]
    mgr = YouTubeConfirmationManager(ttl_seconds=300, time_fn=lambda: clock[0])

    rec = mgr.create_proposal(
        operation="delete_youtube_video",
        channel_id="UC_1",
        channel_title="Canal 1",
        account_email="cursopb@gmail.com",
        payload={"video_id": "V1"},
        summary_pt_br="Resumo exclusão",
    )
    mgr.mark_summary_presented(rec.confirmation_token)
    mgr.record_user_affirmative_turn(source="voice")

    # Advance monotonic clock past 300s TTL
    clock[0] = 1305.0
    ok_exp, code_exp, _ = mgr.verify_and_consume(
        rec.confirmation_token,
        "delete_youtube_video",
        {"video_id": "V1"},
    )
    assert ok_exp is False
    assert code_exp == "token_expired"

    # Create another proposal and test service restart invalidation
    rec_restart = mgr.create_proposal(
        operation="delete_youtube_video",
        channel_id="UC_1",
        channel_title="Canal 1",
        account_email="cursopb@gmail.com",
        payload={"video_id": "V2"},
        summary_pt_br="Resumo 2",
    )
    mgr.mark_summary_presented(rec_restart.confirmation_token)
    mgr.record_user_affirmative_turn(source="voice")

    old_instance_id = mgr.service_instance_id
    new_instance_id = mgr.reset_service_session()
    assert new_instance_id != old_instance_id

    ok_rest, code_rest, _ = mgr.verify_and_consume(
        rec_restart.confirmation_token,
        "delete_youtube_video",
        {"video_id": "V2"},
    )
    assert ok_rest is False
    assert code_rest == "invalid_confirmation_token"


# =============================================================================
# 7. Vosk Voice Confirmation Intent Filtering (False Positives vs Real Affirm/Cancel)
# =============================================================================


def test_vosk_detect_confirmation_intent_rejects_ambiguous_or_low_confidence():
    detector = WakeWordDetector.__new__(WakeWordDetector)
    mock_rec = MagicMock()
    detector._vosk_rec = mock_rec

    # 1. Partial result only (AcceptWaveform == False) -> must return None
    mock_rec.AcceptWaveform.return_value = False
    assert detector.detect_confirmation_intent(b"\x00\x00" * 640) is None

    # 2. Contradiction / hesitation ("sim mas espera") -> must return None
    mock_rec.AcceptWaveform.return_value = True
    mock_rec.Result.return_value = json.dumps({"text": "sim mas espera"})
    assert detector.detect_confirmation_intent(b"\x00\x00" * 640) is None

    # 3. Low confidence (< 0.80) on "sim" -> must return None
    mock_rec.Result.return_value = json.dumps({
        "text": "sim",
        "result": [{"word": "sim", "conf": 0.62}],
    })
    assert detector.detect_confirmation_intent(b"\x00\x00" * 640) is None

    # 4. Cancellation ("não confirma") -> must return "cancel" even though "confirma" is present
    mock_rec.Result.return_value = json.dumps({"text": "não confirma"})
    assert detector.detect_confirmation_intent(b"\x00\x00" * 640) == "cancel"

    # 5. Clean high-confidence affirmation ("sim confirmo") -> returns "affirm"
    mock_rec.Result.return_value = json.dumps({
        "text": "sim confirmo",
        "result": [{"word": "sim", "conf": 0.96}, {"word": "confirmo", "conf": 0.94}],
    })
    assert detector.detect_confirmation_intent(b"\x00\x00" * 640) == "affirm"


# =============================================================================
# 8. Upload Privacy Lock Warning & Strict Single-Video Deletion Verification
# =============================================================================


def test_upload_youtube_video_warns_when_locked_private_by_youtube(tmp_path: Path, monkeypatch):
    creds_file = _make_valid_client_secrets(tmp_path / "credentials.json")
    tokens_dir = tmp_path / "tokens"
    service = YouTubeConnectionService(credentials_path=creds_file, tokens_dir=tokens_dir)
    _seed_channel_entry(service, "servpb@gmail.com", "UCYCmXtIR-tbWCyrwbLdczyA", "Alta Restauração")
    monkeypatch.setattr(youtube_tools, "get_youtube_service", lambda: service)

    video_file = tmp_path / "aula_teste.mp4"
    video_file.write_bytes(b"fake-mp4-binary-content" * 100)

    # Step 1: Generate proposal requesting 'public'
    step1 = youtube_tools.upload_youtube_video(
        file_path=str(video_file),
        title="Vídeo Teste Auditoria",
        privacy_status="public",
        channel="UCYCmXtIR-tbWCyrwbLdczyA",
    )
    assert step1["status"] == "confirmation_required"
    token = step1["confirmation_token"]

    # Mark summary presented and user affirmed
    service.confirmations.mark_summary_presented(token)
    service.confirmations.record_user_affirmative_turn(source="voice")

    # Simulate YouTube API returning effective privacyStatus='private' due to unaudited project
    fake_upload_resp = {
        "id": "UP_VID_777",
        "snippet": {"title": "Vídeo Teste Auditoria"},
        "status": {"privacyStatus": "private", "uploadStatus": "uploaded"},
    }
    with patch.object(service, "upload_video_resumable", return_value=(fake_upload_resp, "success", "OK")):
        step2 = youtube_tools.upload_youtube_video(
            file_path=str(video_file),
            title="Vídeo Teste Auditoria",
            privacy_status="public",
            channel="UCYCmXtIR-tbWCyrwbLdczyA",
            confirmation_token=token,
        )

    assert step2["status"] == "uploaded"
    assert step2["requested_privacy_status"] == "public"
    assert step2["effective_privacy_status"] == "private"
    assert step2["privacy_locked_by_youtube"] is True
    assert "YouTube Studio" in step2["message"]


def test_delete_youtube_video_enforces_exact_channel_and_video_titles(tmp_path: Path, monkeypatch):
    creds_file = _make_valid_client_secrets(tmp_path / "credentials.json")
    tokens_dir = tmp_path / "tokens"
    service = YouTubeConnectionService(credentials_path=creds_file, tokens_dir=tokens_dir)
    _seed_channel_entry(service, "servpb@gmail.com", "UCYCmXtIR-tbWCyrwbLdczyA", "Alta Restauração")
    monkeypatch.setattr(youtube_tools, "get_youtube_service", lambda: service)

    # Reject batch video IDs immediately
    batch_res = youtube_tools.delete_youtube_video(
        video_id="VID_1,VID_2",
        channel="UCYCmXtIR-tbWCyrwbLdczyA",
    )
    assert batch_res["status"] == "invalid_video_id"

    video_payload = {
        "items": [{
            "id": "VID_DEL_99",
            "snippet": {
                "title": "Restauração de Farol Antigo",
                "channelId": "UCYCmXtIR-tbWCyrwbLdczyA",
                "channelTitle": "Alta Restauração",
            },
            "status": {"privacyStatus": "private"},
        }]
    }

    with patch.object(service, "request_data_api", return_value=(video_payload, "success", "OK")):
        step1 = youtube_tools.delete_youtube_video(
            video_id="VID_DEL_99",
            channel="UCYCmXtIR-tbWCyrwbLdczyA",
        )
    assert step1["status"] == "confirmation_required"
    token = step1["confirmation_token"]

    service.confirmations.mark_summary_presented(token)
    service.confirmations.record_user_affirmative_turn(source="voice")

    # Attempt Step 2 with wrong video title -> blocked without consuming token
    with patch.object(service, "request_data_api", return_value=(video_payload, "success", "OK")):
        wrong_name_res = youtube_tools.delete_youtube_video(
            video_id="VID_DEL_99",
            channel="UCYCmXtIR-tbWCyrwbLdczyA",
            confirm_channel_name="Alta Restauração",
            confirm_video_title="Título Incorreto",
            confirmation_token=token,
        )
    assert wrong_name_res["status"] == "confirmation_names_mismatch"

    # Now pass exact channel name and video title -> succeeds
    def fake_del_api(endpoint, entry_key, method="GET", **kwargs):
        if method == "DELETE":
            return {}, "success", "OK"
        return video_payload, "success", "OK"

    with patch.object(service, "request_data_api", side_effect=fake_del_api):
        del_ok = youtube_tools.delete_youtube_video(
            video_id="VID_DEL_99",
            channel="UCYCmXtIR-tbWCyrwbLdczyA",
            confirm_channel_name="Alta Restauração",
            confirm_video_title="Restauração de Farol Antigo",
            confirmation_token=token,
        )
    assert del_ok["status"] == "deleted"
    assert del_ok["video_id"] == "VID_DEL_99"
