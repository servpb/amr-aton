"""YouTube Multi-Account & Multi-Channel Tools for Aton.

Exposes 12 tools for Gemini Live / CLI / Gateway:
- Read-only operations:
  1. list_youtube_channels(account=None)
  2. get_youtube_channel_stats(channel, start_date=None, end_date=None)
  3. list_youtube_videos(channel, max_results=10, query=None)
  4. get_youtube_video_details(video_id, channel=None)
  5. list_youtube_comments(video_id, channel=None, max_results=10)
  11. check_youtube_connection(account=None)
- Write / Destructive operations (enforced by server-side two-phase YouTubeConfirmationManager):
  6. reply_to_youtube_comment(comment_id, reply_text, channel=None, confirmation_token=None)
  7. update_youtube_video_metadata(video_id, channel=None, title=None, description=None, tags=None,
                                   category_id=None, privacy_status=None, publish_at=None, confirmation_token=None)
  8. upload_youtube_video(file_path, title, description="", tags=None, category_id="22",
                          privacy_status="private", publish_at=None, channel=None, confirmation_token=None)
  9. delete_youtube_video(video_id, channel, confirm_channel_name="", confirm_video_title="", confirmation_token=None)
- Authentication & account management:
  10. authenticate_youtube(expected_email=None, mode="manage")
  12. remove_youtube_account(target, revoke_remote=False)
"""

from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.integrations.youtube_service import (
    YOUTUBE_API_QUOTA_COSTS,
    YouTubeConnectionService,
    get_youtube_service,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Helper: Video Ownership & Ambiguous Channel Resolution
# =============================================================================


def _verify_video_channel_ownership(
    service: YouTubeConnectionService,
    video_id: str,
    requested_channel: Optional[str] = None,
    require_write: bool = False,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], str, str]:
    """Resolve the channel entry and verify that `video_id` belongs to the expected channel when writing.

    Returns:
        Tuple of (resolved_channel_entry, video_resource, status_code, message_pt_br)
    """
    vid = (video_id or "").strip()
    if not vid:
        return None, None, "invalid_video_id", "Informe o ID do vídeo do YouTube."

    all_channels = service.get_all_configured_channels()
    if not all_channels:
        return (
            None,
            None,
            "not_authenticated",
            (
                "Nenhuma conta ou canal do YouTube está conectado ao Aton. "
                "Execute 'run.bat youtube-auth cursopb@gmail.com' e 'run.bat youtube-auth servpb@gmail.com'."
            ),
        )

    # Case 1: Caller explicitly passed a channel query
    if requested_channel and requested_channel.strip():
        entry, res_code, res_msg = service.resolve_channel_entry(requested_channel)
        if entry is None:
            return None, None, res_code, res_msg

        entry_key = str(entry["entry_key"])
        data, api_code, api_msg = service.request_data_api(
            "videos",
            entry_key=entry_key,
            query_params={
                "part": "snippet,status,statistics,contentDetails",
                "id": vid,
            },
            required_operation="read_data",
            operation_name="videos.list",
        )
        if data is None or api_code != "success":
            return None, None, api_code, api_msg

        items = data.get("items", [])
        if not items:
            return (
                None,
                None,
                "video_not_found",
                f"O vídeo '{vid}' não foi encontrado no YouTube ou não está acessível pelo canal '{entry.get('channel_title')}'.",
            )

        video_item = items[0]
        owner_channel_id = str(video_item.get("snippet", {}).get("channelId", "")).strip()
        expected_channel_id = str(entry.get("channel_id", "")).strip()
        if owner_channel_id and expected_channel_id and owner_channel_id != expected_channel_id:
            owner_title = video_item.get("snippet", {}).get("channelTitle", owner_channel_id)
            return (
                None,
                video_item,
                "channel_mismatch",
                (
                    f"Conflito de propriedade (channel_mismatch): o vídeo '{video_item.get('snippet', {}).get('title', vid)}' "
                    f"({vid}) pertence ao canal '{owner_title}' ({owner_channel_id}), e não ao canal selecionado "
                    f"'{entry.get('channel_title')}' ({expected_channel_id}). Operação bloqueada."
                ),
            )
        return entry, video_item, "resolved", "OK"

    # Case 2: Caller did NOT specify a channel
    if len(all_channels) == 1:
        entry = all_channels[0]
        entry_key = str(entry["entry_key"])
        data, api_code, api_msg = service.request_data_api(
            "videos",
            entry_key=entry_key,
            query_params={
                "part": "snippet,status,statistics,contentDetails",
                "id": vid,
            },
            required_operation="read_data",
            operation_name="videos.list",
        )
        if data is None or api_code != "success":
            return None, None, api_code, api_msg

        items = data.get("items", [])
        if not items:
            return None, None, "video_not_found", f"O vídeo '{vid}' não foi encontrado no YouTube."

        video_item = items[0]
        owner_channel_id = str(video_item.get("snippet", {}).get("channelId", "")).strip()
        expected_channel_id = str(entry.get("channel_id", "")).strip()
        if require_write and owner_channel_id and expected_channel_id and owner_channel_id != expected_channel_id:
            owner_title = video_item.get("snippet", {}).get("channelTitle", owner_channel_id)
            return (
                None,
                video_item,
                "channel_mismatch",
                (
                    f"Conflito de propriedade (channel_mismatch): o vídeo '{video_item.get('snippet', {}).get('title', vid)}' "
                    f"({vid}) pertence ao canal '{owner_title}' ({owner_channel_id}), e não ao canal conectado "
                    f"'{entry.get('channel_title')}' ({expected_channel_id})."
                ),
            )
        return entry, video_item, "resolved", "OK"

    # Multiple channels connected and no channel specified:
    # Probe with the first valid channel to inspect the video's owner channelId
    video_item: Optional[Dict[str, Any]] = None
    last_err_code = "video_not_found"
    last_err_msg = f"O vídeo '{vid}' não foi encontrado."
    for candidate in all_channels:
        data, api_code, api_msg = service.request_data_api(
            "videos",
            entry_key=str(candidate["entry_key"]),
            query_params={
                "part": "snippet,status,statistics,contentDetails",
                "id": vid,
            },
            required_operation="read_data",
            operation_name="videos.list",
        )
        if data is not None and api_code == "success":
            items = data.get("items", [])
            if items:
                video_item = items[0]
                break
        else:
            last_err_code = api_code
            last_err_msg = api_msg

    if video_item is None:
        return None, None, last_err_code, last_err_msg

    owner_channel_id = str(video_item.get("snippet", {}).get("channelId", "")).strip()
    matching_entries = [
        c for c in all_channels if str(c.get("channel_id", "")).strip() == owner_channel_id
    ]
    if len(matching_entries) == 1:
        return matching_entries[0], video_item, "resolved", "OK"

    if len(matching_entries) > 1:
        opts = ", ".join(
            f"{m.get('channel_title')} [{m.get('channel_id')}] (conta {m.get('account_email')})"
            for m in matching_entries
        )
        return (
            None,
            video_item,
            "ambiguous_channel",
            (
                f"Ambiguidade de conta/canal (ambiguous_channel): o canal '{owner_channel_id}' está autenticado em "
                f"mais de uma conta ({opts}). Especifique o parâmetro 'channel' (ou e-mail da conta) para continuar."
            ),
        )

    if require_write:
        owner_title = video_item.get("snippet", {}).get("channelTitle", owner_channel_id)
        avail = ", ".join(f"{c.get('channel_title')} ({c.get('channel_id')})" for c in all_channels)
        return (
            None,
            video_item,
            "channel_mismatch",
            (
                f"O vídeo '{video_item.get('snippet', {}).get('title', vid)}' ({vid}) pertence ao canal "
                f"'{owner_title}' ({owner_channel_id}), que não está entre os canais autenticados ({avail})."
            ),
        )

    # For read-only detail lookup on a public video when multiple channels exist, require explicit channel if ambiguous
    opts = ", ".join(
        f"{m.get('channel_title')} [{m.get('channel_id')}] ({m.get('account_email')})"
        for m in all_channels
    )
    return (
        None,
        video_item,
        "ambiguous_channel",
        (
            f"Há {len(all_channels)} canais conectados ({opts}) e o vídeo '{vid}' pertence a '{owner_channel_id}'. "
            "Por favor, informe o parâmetro 'channel' para definir qual credencial utilizar."
        ),
    )


# =============================================================================
# 1. list_youtube_channels
# =============================================================================


def list_youtube_channels(account: Optional[str] = None) -> Dict[str, Any]:
    """List all authenticated YouTube channels, associated Google accounts, access modes, and check target channel UCYCmXtIR-tbWCyrwbLdczyA."""
    service = get_youtube_service()
    return service.check_connection_and_channels(account=account)


# =============================================================================
# 2. get_youtube_channel_stats (Data API v3 Totals + Analytics API v2 Report)
# =============================================================================


def get_youtube_channel_stats(
    channel: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch both YouTube Data API v3 lifetime totals and YouTube Analytics API v2 period metrics for a channel.

    Clearly distinguishes Data API v3 totals from Analytics API v2 metrics, reports unavailable metrics,
    discloses period and timezone (America/Sao_Paulo), and warns about variable processing latency.
    """
    service = get_youtube_service()
    entry, res_code, res_msg = service.resolve_channel_entry(channel)
    if entry is None:
        return {
            "status": res_code,
            "message": res_msg,
        }

    entry_key = str(entry["entry_key"])
    channel_id = str(entry["channel_id"])
    account_email = str(entry["account_email"])

    # 1. Fetch YouTube Data API v3 lifetime channel totals
    data_resp, data_code, data_msg = service.request_data_api(
        "channels",
        entry_key=entry_key,
        query_params={
            "part": "snippet,statistics,contentDetails,status",
            "id": channel_id,
        },
        required_operation="read_data",
        operation_name="channels.list",
    )
    if data_resp is None or data_code != "success":
        return {
            "status": data_code,
            "channel_id": channel_id,
            "account_email": account_email,
            "api_source": "YouTube Data API v3",
            "message": data_msg,
        }

    items = data_resp.get("items", [])
    if not items:
        return {
            "status": "channel_not_found",
            "channel_id": channel_id,
            "account_email": account_email,
            "message": f"O canal '{channel_id}' não retornou dados na YouTube Data API v3.",
        }

    parsed_ch = service._parse_channel_item(items[0])
    data_api_totals = {
        "api_source": "YouTube Data API v3 (channels.list)",
        "subscriber_count": parsed_ch["subscriber_count"],
        "hidden_subscriber_count": parsed_ch["hidden_subscriber_count"],
        "total_view_count": parsed_ch["view_count"],
        "total_video_count": parsed_ch["video_count"],
    }

    # 2. Compute period for YouTube Analytics API v2 (default: last 28 days)
    today_utc = datetime.now(timezone.utc).date()
    end_dt_str = (end_date or "").strip() or today_utc.strftime("%Y-%m-%d")
    start_dt_str = (start_date or "").strip() or (today_utc - timedelta(days=28)).strftime("%Y-%m-%d")

    requested_metrics = [
        "views",
        "estimatedMinutesWatched",
        "averageViewDuration",
        "subscribersGained",
        "subscribersLost",
        "likes",
        "comments",
        "shares",
    ]
    analytics_params = {
        "ids": f"channel=={channel_id}",
        "startDate": start_dt_str,
        "endDate": end_dt_str,
        "metrics": ",".join(requested_metrics),
    }

    analytics_resp, ana_code, ana_msg = service.request_analytics_api(
        entry_key=entry_key,
        query_params=analytics_params,
    )

    latency_disclaimer = (
        "Nota sobre latência: os relatórios da YouTube Analytics API v2 possuem atraso de processamento "
        "variável (dados das últimas horas ou dias recentes podem estar incompletos ou ainda em consolidação pelo YouTube)."
    )

    if analytics_resp is not None and ana_code == "success":
        headers = [str(h.get("name", "")) for h in analytics_resp.get("columnHeaders", [])]
        rows = analytics_resp.get("rows", [])
        metrics_values: Dict[str, Any] = {}
        if rows and isinstance(rows[0], list):
            for idx, col_name in enumerate(headers):
                if idx < len(rows[0]):
                    metrics_values[col_name] = rows[0][idx]
        else:
            for col_name in headers:
                metrics_values[col_name] = 0

        unavailable_metrics = [m for m in requested_metrics if m not in metrics_values]
        analytics_report = {
            "api_source": "YouTube Analytics API v2 (reports.query)",
            "available": True,
            "period": {"start_date": start_dt_str, "end_date": end_dt_str},
            "timezone": "America/Sao_Paulo",
            "metrics": metrics_values,
            "unavailable_metrics": unavailable_metrics,
            "latency_notice": latency_disclaimer,
        }
        ana_summary_pt = (
            f"No período de {start_dt_str} a {end_dt_str} (YouTube Analytics API v2, fuso America/Sao_Paulo): "
            f"{metrics_values.get('views', 0)} visualizações, "
            f"{metrics_values.get('estimatedMinutesWatched', 0)} minutos assistidos, "
            f"+{metrics_values.get('subscribersGained', 0)}/-{metrics_values.get('subscribersLost', 0)} inscritos, "
            f"{metrics_values.get('likes', 0)} curtidas e {metrics_values.get('comments', 0)} comentários."
        )
    else:
        analytics_report = {
            "api_source": "YouTube Analytics API v2 (reports.query)",
            "available": False,
            "error_code": ana_code,
            "period": {"start_date": start_dt_str, "end_date": end_dt_str},
            "timezone": "America/Sao_Paulo",
            "metrics": {},
            "unavailable_metrics": requested_metrics,
            "reason": ana_msg,
            "latency_notice": latency_disclaimer,
        }
        ana_summary_pt = (
            f"Métricas de período da YouTube Analytics API v2 ({start_dt_str} a {end_dt_str}) não puderam ser obtidas: "
            f"{ana_msg}"
        )

    summary_msg = (
        f"Estatísticas do canal '{parsed_ch['title']}' [{channel_id}] (conta {account_email}): "
        f"Totais acumulados (YouTube Data API v3): {parsed_ch['subscriber_count']} inscritos, "
        f"{parsed_ch['view_count']} visualizações totais e {parsed_ch['video_count']} vídeos publicados. "
        f"{ana_summary_pt} {latency_disclaimer}"
    )

    return {
        "status": "success",
        "channel_id": channel_id,
        "channel_title": parsed_ch["title"],
        "custom_url": parsed_ch["custom_url"],
        "account_email": account_email,
        "period": {"start_date": start_dt_str, "end_date": end_dt_str},
        "timezone": "America/Sao_Paulo",
        "data_api_totals": data_api_totals,
        "analytics_api_report": analytics_report,
        "message": summary_msg,
    }


# =============================================================================
# 3. list_youtube_videos (Quota-Aware Uploads Playlist by Default)
# =============================================================================


def list_youtube_videos(
    channel: str,
    max_results: int = 10,
    query: Optional[str] = None,
) -> Dict[str, Any]:
    """List videos from a connected YouTube channel.

    Uses the channel's `uploads` playlist (`playlistItems.list` + `videos.list`, 2 quota units total)
    by default, and only calls `search.list` (100 quota units) when a `query` filter is provided.
    """
    service = get_youtube_service()
    entry, res_code, res_msg = service.resolve_channel_entry(channel)
    if entry is None:
        return {"status": res_code, "message": res_msg}

    entry_key = str(entry["entry_key"])
    channel_id = str(entry["channel_id"])
    channel_title = str(entry.get("channel_title", channel_id))
    account_email = str(entry.get("account_email", ""))
    limit = max(1, min(int(max_results or 10), 50))

    video_ids: List[str] = []
    quota_method_used = "playlistItems.list + videos.list (2 unidades de cota)"

    if query and query.strip():
        quota_method_used = "search.list + videos.list (101 unidades de cota)"
        search_data, s_code, s_msg = service.request_data_api(
            "search",
            entry_key=entry_key,
            query_params={
                "part": "id,snippet",
                "channelId": channel_id,
                "q": query.strip(),
                "type": "video",
                "order": "date",
                "maxResults": limit,
            },
            required_operation="read_data",
            operation_name="search.list",
        )
        if search_data is None or s_code != "success":
            return {"status": s_code, "channel_id": channel_id, "message": s_msg}

        for item in search_data.get("items", []):
            vid = str(item.get("id", {}).get("videoId", "")).strip()
            if vid:
                video_ids.append(vid)
    else:
        uploads_playlist = str(entry.get("uploads_playlist_id", "")).strip()
        if not uploads_playlist:
            ch_data, c_code, c_msg = service.request_data_api(
                "channels",
                entry_key=entry_key,
                query_params={"part": "contentDetails", "id": channel_id},
                required_operation="read_data",
                operation_name="channels.list",
            )
            if ch_data is None or c_code != "success":
                return {"status": c_code, "channel_id": channel_id, "message": c_msg}
            ch_items = ch_data.get("items", [])
            if ch_items:
                uploads_playlist = (
                    ch_items[0]
                    .get("contentDetails", {})
                    .get("relatedPlaylists", {})
                    .get("uploads", "")
                )

        if not uploads_playlist:
            return {
                "status": "uploads_playlist_not_found",
                "channel_id": channel_id,
                "message": f"Não foi possível localizar a playlist de envios do canal '{channel_title}' ({channel_id}).",
            }

        pl_data, p_code, p_msg = service.request_data_api(
            "playlistItems",
            entry_key=entry_key,
            query_params={
                "part": "contentDetails,snippet",
                "playlistId": uploads_playlist,
                "maxResults": limit,
            },
            required_operation="read_data",
            operation_name="playlists.list",
        )
        if pl_data is None or p_code != "success":
            return {"status": p_code, "channel_id": channel_id, "message": p_msg}

        for item in pl_data.get("items", []):
            vid = str(item.get("contentDetails", {}).get("videoId", "")).strip()
            if vid:
                video_ids.append(vid)

    if not video_ids:
        return {
            "status": "success",
            "channel_id": channel_id,
            "channel_title": channel_title,
            "account_email": account_email,
            "videos": [],
            "message": f"Nenhum vídeo encontrado no canal '{channel_title}' ({channel_id}).",
        }

    v_data, v_code, v_msg = service.request_data_api(
        "videos",
        entry_key=entry_key,
        query_params={
            "part": "snippet,status,statistics,contentDetails",
            "id": ",".join(video_ids),
        },
        required_operation="read_data",
        operation_name="videos.list",
    )
    if v_data is None or v_code != "success":
        return {"status": v_code, "channel_id": channel_id, "message": v_msg}

    videos_list: List[Dict[str, Any]] = []
    for v_item in v_data.get("items", []):
        snippet = v_item.get("snippet", {}) or {}
        status_obj = v_item.get("status", {}) or {}
        stats = v_item.get("statistics", {}) or {}
        videos_list.append({
            "video_id": v_item.get("id", ""),
            "title": snippet.get("title", ""),
            "published_at": snippet.get("publishedAt", ""),
            "privacy_status": status_obj.get("privacyStatus", ""),
            "view_count": int(stats.get("viewCount", 0) or 0),
            "like_count": int(stats.get("likeCount", 0) or 0),
            "comment_count": int(stats.get("commentCount", 0) or 0),
        })

    preview_str = "; ".join(
        f"'{v['title']}' [ID: {v['video_id']}] ({v['privacy_status']}, {v['view_count']} views)"
        for v in videos_list[:5]
    )
    return {
        "status": "success",
        "channel_id": channel_id,
        "channel_title": channel_title,
        "account_email": account_email,
        "quota_method": quota_method_used,
        "count": len(videos_list),
        "videos": videos_list,
        "message": (
            f"Encontrados {len(videos_list)} vídeo(s) no canal '{channel_title}' [{channel_id}]: {preview_str}."
        ),
    }


# =============================================================================
# 4. get_youtube_video_details
# =============================================================================


def get_youtube_video_details(video_id: str, channel: Optional[str] = None) -> Dict[str, Any]:
    """Get complete metadata, privacy status, and statistics for a specific YouTube video."""
    service = get_youtube_service()
    entry, video_item, code, msg = _verify_video_channel_ownership(
        service,
        video_id=video_id,
        requested_channel=channel,
        require_write=False,
    )
    if entry is None or video_item is None:
        return {"status": code, "message": msg}

    snippet = video_item.get("snippet", {}) or {}
    status_obj = video_item.get("status", {}) or {}
    stats = video_item.get("statistics", {}) or {}
    content_details = video_item.get("contentDetails", {}) or {}

    details = {
        "video_id": video_item.get("id", ""),
        "title": snippet.get("title", ""),
        "description": snippet.get("description", ""),
        "tags": snippet.get("tags", []),
        "category_id": snippet.get("categoryId", ""),
        "channel_id": snippet.get("channelId", ""),
        "channel_title": snippet.get("channelTitle", ""),
        "published_at": snippet.get("publishedAt", ""),
        "duration": content_details.get("duration", ""),
        "privacy_status": status_obj.get("privacyStatus", ""),
        "publish_at": status_obj.get("publishAt", ""),
        "made_for_kids": bool(status_obj.get("madeForKids", False)),
        "view_count": int(stats.get("viewCount", 0) or 0),
        "like_count": int(stats.get("likeCount", 0) or 0),
        "comment_count": int(stats.get("commentCount", 0) or 0),
    }

    return {
        "status": "success",
        "account_email": entry.get("account_email", ""),
        "video": details,
        "message": (
            f"Vídeo '{details['title']}' [ID: {details['video_id']}] do canal '{details['channel_title']}' "
            f"({details['channel_id']}): status '{details['privacy_status']}', "
            f"{details['view_count']} visualizações, {details['like_count']} curtidas e "
            f"{details['comment_count']} comentários."
        ),
    }


# =============================================================================
# 5. list_youtube_comments
# =============================================================================


def list_youtube_comments(
    video_id: str,
    channel: Optional[str] = None,
    max_results: int = 10,
) -> Dict[str, Any]:
    """List top-level comments on a YouTube video (`commentThreads.list`).

    Compatible with `youtube.readonly` for public videos; does NOT require `youtube.force-ssl` for reading.
    """
    service = get_youtube_service()
    entry, video_item, code, msg = _verify_video_channel_ownership(
        service,
        video_id=video_id,
        requested_channel=channel,
        require_write=False,
    )
    if entry is None or video_item is None:
        return {"status": code, "message": msg}

    entry_key = str(entry["entry_key"])
    limit = max(1, min(int(max_results or 10), 50))

    c_data, c_code, c_msg = service.request_data_api(
        "commentThreads",
        entry_key=entry_key,
        query_params={
            "part": "snippet,replies",
            "videoId": video_id.strip(),
            "maxResults": limit,
            "order": "time",
            "textFormat": "plainText",
        },
        required_operation="read_data",
        operation_name="commentThreads.list",
    )
    if c_data is None or c_code != "success":
        return {"status": c_code, "video_id": video_id, "message": c_msg}

    comments_out: List[Dict[str, Any]] = []
    for item in c_data.get("items", []):
        top_comment = item.get("snippet", {}).get("topLevelComment", {}) or {}
        top_snip = top_comment.get("snippet", {}) or {}
        comments_out.append({
            "comment_id": top_comment.get("id", item.get("id", "")),
            "author": top_snip.get("authorDisplayName", "Autor desconhecido"),
            "text": top_snip.get("textDisplay", ""),
            "like_count": int(top_snip.get("likeCount", 0) or 0),
            "published_at": top_snip.get("publishedAt", ""),
            "total_reply_count": int(item.get("snippet", {}).get("totalReplyCount", 0) or 0),
        })

    vid_title = video_item.get("snippet", {}).get("title", video_id)
    if not comments_out:
        return {
            "status": "success",
            "video_id": video_id,
            "video_title": vid_title,
            "comments": [],
            "message": f"Não há comentários públicos no vídeo '{vid_title}' ({video_id}).",
        }

    preview = "; ".join(
        f"[{c['comment_id']}] {c['author']}: \"{c['text'][:80]}\""
        for c in comments_out[:5]
    )
    return {
        "status": "success",
        "video_id": video_id,
        "video_title": vid_title,
        "count": len(comments_out),
        "comments": comments_out,
        "message": f"{len(comments_out)} comentário(s) no vídeo '{vid_title}' ({video_id}): {preview}.",
    }


# =============================================================================
# 6. reply_to_youtube_comment (Two-Step Confirmed Write Operation)
# =============================================================================


def reply_to_youtube_comment(
    comment_id: str,
    reply_text: str,
    channel: Optional[str] = None,
    confirmation_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Reply to an existing YouTube comment (`comments.insert`, 50 quota units).

    Requires two-step confirmation via `YouTubeConfirmationManager` and `manage` scope (`youtube.force-ssl`).
    """
    cid = (comment_id or "").strip()
    text = (reply_text or "").strip()
    if not cid or not text:
        return {
            "status": "invalid_parameters",
            "message": "Informe o 'comment_id' do comentário principal e o texto da resposta ('reply_text').",
        }

    service = get_youtube_service()
    entry, res_code, res_msg = service.resolve_channel_entry(channel)
    if entry is None:
        return {"status": res_code, "message": res_msg}

    entry_key = str(entry["entry_key"])
    channel_id = str(entry["channel_id"])
    channel_title = str(entry.get("channel_title", channel_id))
    account_email = str(entry.get("account_email", ""))

    # Verify scope before even proposing or executing
    creds, sc_code, sc_msg = service._load_and_validate_entry_credentials(
        entry_key=entry_key,
        required_operation="manage_comments",
    )
    if creds is None:
        return {"status": sc_code, "channel_id": channel_id, "message": sc_msg}

    payload_for_digest = {
        "entry_key": entry_key,
        "channel_id": channel_id,
        "comment_id": cid,
        "reply_text": text,
    }

    # Step 1: No confirmation_token -> Generate proposal
    if not confirmation_token or not confirmation_token.strip():
        summary_pt = (
            f"Confirma a publicação de resposta ao comentário '{cid}' usando o canal "
            f"'{channel_title}' ({channel_id}, conta {account_email}) com o texto: \"{text}\"? "
            "Responda 'Sim' para autorizar."
        )
        record = service.confirmations.create_proposal(
            operation="reply_to_youtube_comment",
            channel_id=channel_id,
            channel_title=channel_title,
            account_email=account_email,
            payload=payload_for_digest,
            summary_pt_br=summary_pt,
        )
        return {
            "status": "confirmation_required",
            "operation": "reply_to_youtube_comment",
            "confirmation_token": record.confirmation_token,
            "channel_id": channel_id,
            "channel_title": channel_title,
            "account_email": account_email,
            "comment_id": cid,
            "reply_text": text,
            "quota_cost_units": YOUTUBE_API_QUOTA_COSTS["comments.insert"],
            "summary": summary_pt,
            "message": summary_pt,
        }

    # Step 2: Validate server-side USER_AFFIRMED state + digest match
    ok, v_code, v_msg = service.confirmations.verify_and_consume(
        confirmation_token=confirmation_token,
        operation="reply_to_youtube_comment",
        payload=payload_for_digest,
    )
    if not ok:
        return {
            "status": v_code,
            "channel_id": channel_id,
            "comment_id": cid,
            "message": v_msg,
        }

    body = {
        "snippet": {
            "parentId": cid,
            "textOriginal": text,
        }
    }
    resp_data, api_code, api_msg = service.request_data_api(
        "comments",
        entry_key=entry_key,
        method="POST",
        query_params={"part": "snippet"},
        json_body=body,
        required_operation="manage_comments",
        operation_name="comments.insert",
    )
    if resp_data is None or api_code != "success":
        return {"status": api_code, "channel_id": channel_id, "comment_id": cid, "message": api_msg}

    reply_id = resp_data.get("id", "")
    return {
        "status": "replied",
        "channel_id": channel_id,
        "channel_title": channel_title,
        "account_email": account_email,
        "parent_comment_id": cid,
        "reply_comment_id": reply_id,
        "reply_text": text,
        "message": (
            f"Resposta publicada com sucesso no comentário '{cid}' pelo canal '{channel_title}' "
            f"(ID da resposta: {reply_id})."
        ),
    }


# =============================================================================
# 7. update_youtube_video_metadata (Two-Step Confirmed + Preserves Existing Fields)
# =============================================================================


def update_youtube_video_metadata(
    video_id: str,
    channel: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
    category_id: Optional[str] = None,
    privacy_status: Optional[str] = None,
    publish_at: Optional[str] = None,
    confirmation_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Update a YouTube video's metadata (`videos.update`, 50 quota units).

    Always fetches current `snippet` and `status` first so omitted fields are preserved intact,
    verifies channel ownership (`channel_mismatch`), and requires two-step user confirmation.
    """
    service = get_youtube_service()
    entry, video_item, own_code, own_msg = _verify_video_channel_ownership(
        service,
        video_id=video_id,
        requested_channel=channel,
        require_write=True,
    )
    if entry is None or video_item is None:
        return {"status": own_code, "message": own_msg}

    entry_key = str(entry["entry_key"])
    channel_id = str(entry["channel_id"])
    channel_title = str(entry.get("channel_title", channel_id))
    account_email = str(entry.get("account_email", ""))

    # Verify manage_videos scope upfront
    creds, sc_code, sc_msg = service._load_and_validate_entry_credentials(
        entry_key=entry_key,
        required_operation="manage_videos",
    )
    if creds is None:
        return {"status": sc_code, "channel_id": channel_id, "message": sc_msg}

    cur_snippet = dict(video_item.get("snippet", {}) or {})
    cur_status = dict(video_item.get("status", {}) or {})

    new_title = title.strip() if title is not None and title.strip() else cur_snippet.get("title", "")
    new_desc = description if description is not None else cur_snippet.get("description", "")
    new_tags = list(tags) if tags is not None else list(cur_snippet.get("tags", []) or [])
    new_cat = (
        category_id.strip()
        if category_id is not None and category_id.strip()
        else str(cur_snippet.get("categoryId", "22"))
    )
    new_privacy = (
        privacy_status.strip().lower()
        if privacy_status is not None and privacy_status.strip()
        else str(cur_status.get("privacyStatus", "private"))
    )
    new_publish_at = (
        publish_at.strip()
        if publish_at is not None and publish_at.strip()
        else cur_status.get("publishAt")
    )

    payload_for_digest = {
        "entry_key": entry_key,
        "channel_id": channel_id,
        "video_id": video_id.strip(),
        "title": new_title,
        "description": new_desc,
        "tags": new_tags,
        "category_id": new_cat,
        "privacy_status": new_privacy,
        "publish_at": new_publish_at or "",
    }

    if not confirmation_token or not confirmation_token.strip():
        changes_desc: List[str] = []
        if title is not None:
            changes_desc.append(f"título para '{new_title}'")
        if description is not None:
            changes_desc.append("descrição atualizada")
        if tags is not None:
            changes_desc.append(f"tags ({len(new_tags)} tags)")
        if category_id is not None:
            changes_desc.append(f"categoria para '{new_cat}'")
        if privacy_status is not None:
            changes_desc.append(f"privacidade para '{new_privacy}'")
        if publish_at is not None:
            changes_desc.append(f"agendamento para '{new_publish_at}'")
        changes_str = ", ".join(changes_desc) if changes_desc else "revisão de metadados atuais"

        summary_pt = (
            f"Confirma a alteração dos metadados do vídeo '{cur_snippet.get('title', video_id)}' "
            f"(ID: {video_id.strip()}) no canal '{channel_title}' ({channel_id}, conta {account_email}): "
            f"{changes_str}? Responda 'Sim' para autorizar."
        )
        record = service.confirmations.create_proposal(
            operation="update_youtube_video_metadata",
            channel_id=channel_id,
            channel_title=channel_title,
            account_email=account_email,
            payload=payload_for_digest,
            summary_pt_br=summary_pt,
        )
        return {
            "status": "confirmation_required",
            "operation": "update_youtube_video_metadata",
            "confirmation_token": record.confirmation_token,
            "channel_id": channel_id,
            "channel_title": channel_title,
            "account_email": account_email,
            "video_id": video_id.strip(),
            "proposed_metadata": payload_for_digest,
            "quota_cost_units": YOUTUBE_API_QUOTA_COSTS["videos.update"],
            "summary": summary_pt,
            "message": summary_pt,
        }

    ok, v_code, v_msg = service.confirmations.verify_and_consume(
        confirmation_token=confirmation_token,
        operation="update_youtube_video_metadata",
        payload=payload_for_digest,
    )
    if not ok:
        return {"status": v_code, "channel_id": channel_id, "video_id": video_id.strip(), "message": v_msg}

    updated_snippet: Dict[str, Any] = {
        "title": new_title,
        "description": new_desc,
        "categoryId": new_cat,
    }
    if new_tags:
        updated_snippet["tags"] = new_tags
    if "defaultLanguage" in cur_snippet:
        updated_snippet["defaultLanguage"] = cur_snippet["defaultLanguage"]
    if "defaultAudioLanguage" in cur_snippet:
        updated_snippet["defaultAudioLanguage"] = cur_snippet["defaultAudioLanguage"]

    updated_status: Dict[str, Any] = {
        "privacyStatus": new_privacy,
    }
    if "madeForKids" in cur_status:
        updated_status["madeForKids"] = cur_status["madeForKids"]
    if "selfDeclaredMadeForKids" in cur_status:
        updated_status["selfDeclaredMadeForKids"] = cur_status["selfDeclaredMadeForKids"]
    if new_publish_at:
        updated_status["publishAt"] = new_publish_at

    update_body = {
        "id": video_id.strip(),
        "snippet": updated_snippet,
        "status": updated_status,
    }

    resp_data, api_code, api_msg = service.request_data_api(
        "videos",
        entry_key=entry_key,
        method="PUT",
        query_params={"part": "snippet,status"},
        json_body=update_body,
        required_operation="manage_videos",
        operation_name="videos.update",
    )
    if resp_data is None or api_code != "success":
        return {"status": api_code, "channel_id": channel_id, "video_id": video_id.strip(), "message": api_msg}

    return {
        "status": "updated",
        "channel_id": channel_id,
        "channel_title": channel_title,
        "account_email": account_email,
        "video_id": video_id.strip(),
        "title": resp_data.get("snippet", {}).get("title", new_title),
        "privacy_status": resp_data.get("status", {}).get("privacyStatus", new_privacy),
        "message": (
            f"Metadados do vídeo '{new_title}' (ID: {video_id.strip()}) atualizados com sucesso no canal "
            f"'{channel_title}' ({channel_id})."
        ),
    }


# =============================================================================
# 8. upload_youtube_video (Two-Step Confirmed + Unaudited Project Privacy Check)
# =============================================================================


def upload_youtube_video(
    file_path: str,
    title: str,
    description: str = "",
    tags: Optional[List[str]] = None,
    category_id: str = "22",
    privacy_status: str = "private",
    publish_at: Optional[str] = None,
    channel: Optional[str] = None,
    confirmation_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Upload a video file to a connected YouTube channel (`videos.insert`, 1600 quota units).

    Defaults to `privacy_status='private'`, requires two-step user confirmation, and inspects the
    returned `status.privacyStatus` after upload to warn if YouTube locked the video as `private`
    due to an unaudited Google Cloud project.
    """
    fpath = Path((file_path or "").strip())
    if not fpath.exists() or not fpath.is_file():
        return {
            "status": "file_not_found",
            "message": f"O arquivo de vídeo '{file_path}' não foi encontrado no computador.",
        }

    v_title = (title or "").strip()
    if not v_title:
        return {
            "status": "invalid_parameters",
            "message": "Informe um título ('title') para o envio do vídeo ao YouTube.",
        }

    service = get_youtube_service()
    entry, res_code, res_msg = service.resolve_channel_entry(channel)
    if entry is None:
        return {"status": res_code, "message": res_msg}

    entry_key = str(entry["entry_key"])
    channel_id = str(entry["channel_id"])
    channel_title = str(entry.get("channel_title", channel_id))
    account_email = str(entry.get("account_email", ""))

    creds, sc_code, sc_msg = service._load_and_validate_entry_credentials(
        entry_key=entry_key,
        required_operation="upload_videos",
    )
    if creds is None:
        return {"status": sc_code, "channel_id": channel_id, "message": sc_msg}

    req_privacy = (privacy_status or "private").strip().lower()
    if req_privacy not in ("private", "unlisted", "public"):
        return {
            "status": "invalid_privacy_status",
            "message": f"Status de privacidade inválido '{privacy_status}'. Use 'private', 'unlisted' ou 'public'.",
        }

    clean_tags = list(tags) if tags else []
    clean_cat = (category_id or "22").strip()
    clean_pub_at = publish_at.strip() if publish_at and publish_at.strip() else ""
    file_size_bytes = fpath.stat().st_size

    payload_for_digest = {
        "entry_key": entry_key,
        "channel_id": channel_id,
        "file_path": str(fpath.resolve()),
        "file_size": file_size_bytes,
        "title": v_title,
        "description": description or "",
        "tags": clean_tags,
        "category_id": clean_cat,
        "privacy_status": req_privacy,
        "publish_at": clean_pub_at,
    }

    if not confirmation_token or not confirmation_token.strip():
        size_mb = round(file_size_bytes / (1024 * 1024), 2)
        summary_pt = (
            f"Confirma o envio (upload) do arquivo '{fpath.name}' ({size_mb} MB) com o título '{v_title}' "
            f"e privacidade '{req_privacy}' para o canal '{channel_title}' ({channel_id}, conta {account_email})? "
            "Custo de cota: 1600 unidades. Responda 'Sim' para autorizar."
        )
        record = service.confirmations.create_proposal(
            operation="upload_youtube_video",
            channel_id=channel_id,
            channel_title=channel_title,
            account_email=account_email,
            payload=payload_for_digest,
            summary_pt_br=summary_pt,
        )
        return {
            "status": "confirmation_required",
            "operation": "upload_youtube_video",
            "confirmation_token": record.confirmation_token,
            "channel_id": channel_id,
            "channel_title": channel_title,
            "account_email": account_email,
            "file_path": str(fpath.resolve()),
            "title": v_title,
            "privacy_status": req_privacy,
            "quota_cost_units": YOUTUBE_API_QUOTA_COSTS["videos.insert"],
            "summary": summary_pt,
            "message": summary_pt,
        }

    ok, v_code, v_msg = service.confirmations.verify_and_consume(
        confirmation_token=confirmation_token,
        operation="upload_youtube_video",
        payload=payload_for_digest,
    )
    if not ok:
        return {"status": v_code, "channel_id": channel_id, "message": v_msg}

    body_metadata: Dict[str, Any] = {
        "snippet": {
            "title": v_title,
            "description": description or "",
            "categoryId": clean_cat,
        },
        "status": {
            "privacyStatus": req_privacy,
        },
    }
    if clean_tags:
        body_metadata["snippet"]["tags"] = clean_tags
    if clean_pub_at:
        body_metadata["status"]["publishAt"] = clean_pub_at

    resp_data, up_code, up_msg = service.upload_video_resumable(
        entry_key=entry_key,
        file_path=fpath,
        body_metadata=body_metadata,
    )
    if resp_data is None or up_code != "success":
        return {"status": up_code, "channel_id": channel_id, "message": up_msg}

    uploaded_id = resp_data.get("id", "")
    effective_privacy = str(resp_data.get("status", {}).get("privacyStatus", req_privacy)).lower()
    upload_status = str(resp_data.get("status", {}).get("uploadStatus", "uploaded"))

    privacy_lock_warning = ""
    if req_privacy in ("public", "unlisted") and effective_privacy == "private":
        privacy_lock_warning = (
            " Atenção: você solicitou privacidade '"
            f"{req_privacy}', mas a API do YouTube fixou o vídeo como 'private' (privado). "
            "Projetos do Google Cloud ainda não submetidos à auditoria de conformidade da YouTube API têm "
            "uploads restritos ao modo privado; para torná-lo público imediatamente, altere a visibilidade "
            "diretamente no YouTube Studio."
        )

    return {
        "status": "uploaded",
        "channel_id": channel_id,
        "channel_title": channel_title,
        "account_email": account_email,
        "video_id": uploaded_id,
        "title": v_title,
        "requested_privacy_status": req_privacy,
        "effective_privacy_status": effective_privacy,
        "upload_status": upload_status,
        "privacy_locked_by_youtube": bool(privacy_lock_warning),
        "message": (
            f"Vídeo '{v_title}' enviado com sucesso para o canal '{channel_title}' [{channel_id}]! "
            f"ID do vídeo: {uploaded_id} (privacidade efetiva: {effective_privacy}).{privacy_lock_warning}"
        ),
    }


# =============================================================================
# 9. delete_youtube_video (Strict Two-Step Confirmed + Exact Channel & Video Title)
# =============================================================================


def delete_youtube_video(
    video_id: str,
    channel: str,
    confirm_channel_name: str = "",
    confirm_video_title: str = "",
    confirmation_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Permanently delete a single YouTube video (`videos.delete`, 50 quota units).

    Strictly enforces:
    1. Explicit `channel` argument (never inferred automatically).
    2. Ownership verification (`channel_mismatch` if video belongs to another channel).
    3. Step 1 generates the summary with the exact channel title and video title fetched from the API.
    4. Step 2 requires a valid `USER_AFFIRMED` `confirmation_token` AND exact match (case-insensitive)
       of both `confirm_channel_name` and `confirm_video_title`.
    5. Batch deletion is strictly forbidden (single `video_id` only).
    """
    vid = (video_id or "").strip()
    if not vid or "," in vid or " " in vid:
        return {
            "status": "invalid_video_id",
            "message": "A exclusão permite apenas 1 vídeo por vez. Informe um único 'video_id' válido.",
        }

    if not channel or not channel.strip():
        return {
            "status": "missing_channel",
            "message": "Para excluir um vídeo, é obrigatório especificar o parâmetro 'channel' (nome ou ID do canal).",
        }

    service = get_youtube_service()
    entry, video_item, own_code, own_msg = _verify_video_channel_ownership(
        service,
        video_id=vid,
        requested_channel=channel,
        require_write=True,
    )
    if entry is None or video_item is None:
        return {"status": own_code, "message": own_msg}

    entry_key = str(entry["entry_key"])
    channel_id = str(entry["channel_id"])
    actual_channel_title = str(
        video_item.get("snippet", {}).get("channelTitle") or entry.get("channel_title") or channel_id
    ).strip()
    actual_video_title = str(video_item.get("snippet", {}).get("title") or "").strip()
    account_email = str(entry.get("account_email", ""))

    creds, sc_code, sc_msg = service._load_and_validate_entry_credentials(
        entry_key=entry_key,
        required_operation="manage_videos",
    )
    if creds is None:
        return {"status": sc_code, "channel_id": channel_id, "message": sc_msg}

    payload_for_digest = {
        "entry_key": entry_key,
        "channel_id": channel_id,
        "video_id": vid,
        "channel_title": actual_channel_title.lower(),
        "video_title": actual_video_title.lower(),
    }

    # Step 1: No confirmation_token -> Return irreversible deletion warning with exact names
    if not confirmation_token or not confirmation_token.strip():
        summary_pt = (
            f"ATENÇÃO — EXCLUSÃO PERMANENTE E IRREVERSÍVEL: Você solicitou excluir definitivamente o vídeo "
            f"'{actual_video_title}' (ID: {vid}) do canal '{actual_channel_title}' ({channel_id}, conta {account_email}). "
            "Para confirmar, responda 'Sim, confirmo a exclusão' após ouvir este aviso."
        )
        record = service.confirmations.create_proposal(
            operation="delete_youtube_video",
            channel_id=channel_id,
            channel_title=actual_channel_title,
            account_email=account_email,
            payload=payload_for_digest,
            summary_pt_br=summary_pt,
        )
        return {
            "status": "confirmation_required",
            "operation": "delete_youtube_video",
            "confirmation_token": record.confirmation_token,
            "channel_id": channel_id,
            "channel_title": actual_channel_title,
            "account_email": account_email,
            "video_id": vid,
            "video_title": actual_video_title,
            "required_confirm_channel_name": actual_channel_title,
            "required_confirm_video_title": actual_video_title,
            "quota_cost_units": YOUTUBE_API_QUOTA_COSTS["videos.delete"],
            "summary": summary_pt,
            "message": summary_pt,
        }

    # Step 2: Check explicit channel name and video title BEFORE consuming token
    given_ch_name = (confirm_channel_name or "").strip().lower()
    given_vid_title = (confirm_video_title or "").strip().lower()
    if given_ch_name != actual_channel_title.lower() or given_vid_title != actual_video_title.lower():
        return {
            "status": "confirmation_names_mismatch",
            "channel_id": channel_id,
            "video_id": vid,
            "expected_channel_name": actual_channel_title,
            "expected_video_title": actual_video_title,
            "message": (
                "Exclusão bloqueada: para excluir permanentemente um vídeo, é obrigatório informar com exatidão "
                f"o nome do canal ('{actual_channel_title}') em 'confirm_channel_name' e o título do vídeo "
                f"('{actual_video_title}') em 'confirm_video_title'."
            ),
        }

    ok, v_code, v_msg = service.confirmations.verify_and_consume(
        confirmation_token=confirmation_token,
        operation="delete_youtube_video",
        payload=payload_for_digest,
    )
    if not ok:
        return {"status": v_code, "channel_id": channel_id, "video_id": vid, "message": v_msg}

    _, api_code, api_msg = service.request_data_api(
        "videos",
        entry_key=entry_key,
        method="DELETE",
        query_params={"id": vid},
        required_operation="manage_videos",
        operation_name="videos.delete",
    )
    if api_code != "success":
        return {"status": api_code, "channel_id": channel_id, "video_id": vid, "message": api_msg}

    return {
        "status": "deleted",
        "channel_id": channel_id,
        "channel_title": actual_channel_title,
        "account_email": account_email,
        "video_id": vid,
        "video_title": actual_video_title,
        "message": (
            f"O vídeo '{actual_video_title}' (ID: {vid}) do canal '{actual_channel_title}' ({channel_id}) "
            "foi excluído permanentemente."
        ),
    }


# =============================================================================
# 10, 11, 12. Authentication, Connection Diagnostics & Account/Channel Removal
# =============================================================================


def authenticate_youtube(
    expected_email: Optional[str] = None,
    mode: str = "manage",
) -> Dict[str, Any]:
    """Start interactive OAuth 2.0 Desktop authentication for a Google Account / YouTube channel identity."""
    service = get_youtube_service()
    return service.authenticate_interactive(
        open_browser=True,
        expected_email=expected_email,
        mode=mode,
    )


def check_youtube_connection(account: Optional[str] = None) -> Dict[str, Any]:
    """Passively check connected YouTube accounts/channels and target channel UCYCmXtIR-tbWCyrwbLdczyA without opening a browser."""
    service = get_youtube_service()
    return service.check_connection_and_channels(account=account)


def remove_youtube_account(target: str, revoke_remote: bool = False) -> Dict[str, Any]:
    """Disconnect a YouTube channel or Google Account locally (and optionally revoke the token on Google's servers)."""
    service = get_youtube_service()
    return service.remove_account_or_channel(target=target, revoke_remote=revoke_remote)


# =============================================================================
# Gemini Live Tool Declarations & Dispatcher
# =============================================================================


YOUTUBE_FUNCTION_DECLARATIONS: List[Dict[str, Any]] = [
    {
        "name": "list_youtube_channels",
        "description": (
            "Lista todos os canais do YouTube autenticados no Aton (associados às contas Google como "
            "cursopb@gmail.com e servpb@gmail.com), mostra o modo de acesso ('readonly' ou 'manage'), "
            "inscritos, vídeos e verifica se o canal UCYCmXtIR-tbWCyrwbLdczyA já está autorizado."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "account": {
                    "type": "STRING",
                    "description": "Opcional. Filtra os canais por endereço de e-mail da conta Google (ex.: 'cursopb@gmail.com' ou 'servpb@gmail.com').",
                }
            },
        },
    },
    {
        "name": "get_youtube_channel_stats",
        "description": (
            "Consulta estatísticas completas de um canal do YouTube, separando os totais acumulados da "
            "YouTube Data API v3 (inscritos, visualizações totais, total de vídeos) das métricas de período "
            "da YouTube Analytics API v2 (visualizações no período, minutos assistidos, duração média, "
            "inscritos ganhos/perdidos, curtidas, comentários e compartilhamentos)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "channel": {
                    "type": "STRING",
                    "description": "Nome do canal, ID do canal (ex.: 'UCYCmXtIR-tbWCyrwbLdczyA'), @handle ou e-mail da conta caso ela tenha apenas 1 canal.",
                },
                "start_date": {
                    "type": "STRING",
                    "description": "Data inicial no formato YYYY-MM-DD para o relatório do YouTube Analytics (padrão: 28 dias atrás).",
                },
                "end_date": {
                    "type": "STRING",
                    "description": "Data final no formato YYYY-MM-DD para o relatório do YouTube Analytics (padrão: hoje).",
                },
            },
            "required": ["channel"],
        },
    },
    {
        "name": "list_youtube_videos",
        "description": (
            "Lista os vídeos publicados ou enviados em um canal conectado do YouTube, retornando título, "
            "ID do vídeo, data de publicação, status de privacidade e contagens de visualizações, curtidas e comentários."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "channel": {
                    "type": "STRING",
                    "description": "Nome do canal, ID do canal (UC...), @handle ou e-mail da conta.",
                },
                "max_results": {
                    "type": "INTEGER",
                    "description": "Quantidade máxima de vídeos a listar (padrão: 10, máximo: 50).",
                },
                "query": {
                    "type": "STRING",
                    "description": "Opcional. Termo de busca para filtrar vídeos específicos no canal.",
                },
            },
            "required": ["channel"],
        },
    },
    {
        "name": "get_youtube_video_details",
        "description": (
            "Obtém todos os detalhes e metadados de um vídeo específico do YouTube pelo seu ID "
            "(título, descrição completa, tags, categoria, duração, privacidade e estatísticas)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "video_id": {
                    "type": "STRING",
                    "description": "ID do vídeo no YouTube (ex.: 'dQw4w9WgXcQ').",
                },
                "channel": {
                    "type": "STRING",
                    "description": "Opcional. Canal ou conta autenticada a utilizar para a consulta.",
                },
            },
            "required": ["video_id"],
        },
    },
    {
        "name": "list_youtube_comments",
        "description": (
            "Lista os comentários principais mais recentes de um vídeo do YouTube, trazendo ID do comentário, "
            "autor, texto, curtidas e número de respostas."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "video_id": {
                    "type": "STRING",
                    "description": "ID do vídeo no YouTube.",
                },
                "channel": {
                    "type": "STRING",
                    "description": "Opcional. Canal ou conta autenticada a utilizar.",
                },
                "max_results": {
                    "type": "INTEGER",
                    "description": "Quantidade máxima de comentários (padrão: 10, máximo: 50).",
                },
            },
            "required": ["video_id"],
        },
    },
    {
        "name": "reply_to_youtube_comment",
        "description": (
            "Responde a um comentário do YouTube em 2 etapas obrigatórias. "
            "Na 1ª etapa (sem confirmation_token), gera o resumo e um token de uso único sem publicar nada. "
            "Apresente o resumo ao usuário e aguarde ele dizer 'Sim'. "
            "Somente após a confirmação verbal do usuário, chame novamente passando o confirmation_token."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "comment_id": {
                    "type": "STRING",
                    "description": "ID do comentário principal que receberá a resposta.",
                },
                "reply_text": {
                    "type": "STRING",
                    "description": "Texto da resposta a ser publicada.",
                },
                "channel": {
                    "type": "STRING",
                    "description": "Canal do YouTube que publicará a resposta.",
                },
                "confirmation_token": {
                    "type": "STRING",
                    "description": "Token de confirmação retornado na 1ª etapa. Só envie após o usuário responder 'Sim'.",
                },
            },
            "required": ["comment_id", "reply_text"],
        },
    },
    {
        "name": "update_youtube_video_metadata",
        "description": (
            "Atualiza metadados de um vídeo do YouTube (título, descrição, tags, categoria, privacidade ou agendamento) "
            "em 2 etapas obrigatórias, preservando os campos não informados. "
            "Na 1ª etapa (sem confirmation_token), gera o resumo da alteração. "
            "Na 2ª etapa (após o usuário responder 'Sim'), executa a atualização com o confirmation_token."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "video_id": {
                    "type": "STRING",
                    "description": "ID do vídeo a ser atualizado.",
                },
                "channel": {
                    "type": "STRING",
                    "description": "Canal proprietário do vídeo.",
                },
                "title": {
                    "type": "STRING",
                    "description": "Novo título do vídeo (opcional).",
                },
                "description": {
                    "type": "STRING",
                    "description": "Nova descrição do vídeo (opcional).",
                },
                "tags": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Nova lista de tags do vídeo (opcional).",
                },
                "category_id": {
                    "type": "STRING",
                    "description": "ID da categoria do YouTube (ex.: '22' para Pessoas e Blogs).",
                },
                "privacy_status": {
                    "type": "STRING",
                    "description": "Status de visibilidade: 'private', 'unlisted' ou 'public'.",
                },
                "publish_at": {
                    "type": "STRING",
                    "description": "Data/hora ISO 8601 para agendamento de publicação (opcional).",
                },
                "confirmation_token": {
                    "type": "STRING",
                    "description": "Token de confirmação da 1ª etapa, enviado somente após o usuário confirmar com 'Sim'.",
                },
            },
            "required": ["video_id"],
        },
    },
    {
        "name": "upload_youtube_video",
        "description": (
            "Envia (faz upload de) um arquivo de vídeo local para um canal do YouTube em 2 etapas obrigatórias. "
            "Padrão de privacidade seguro: 'private'. "
            "Na 1ª etapa (sem confirmation_token), valida o arquivo e gera o resumo para confirmação do usuário. "
            "Na 2ª etapa (após o usuário dizer 'Sim'), realiza o envio resumível com o confirmation_token."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "file_path": {
                    "type": "STRING",
                    "description": "Caminho completo do arquivo de vídeo no computador.",
                },
                "title": {
                    "type": "STRING",
                    "description": "Título do vídeo no YouTube.",
                },
                "description": {
                    "type": "STRING",
                    "description": "Descrição do vídeo (opcional).",
                },
                "tags": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Lista de tags do vídeo (opcional).",
                },
                "category_id": {
                    "type": "STRING",
                    "description": "ID da categoria do YouTube (padrão: '22').",
                },
                "privacy_status": {
                    "type": "STRING",
                    "description": "Privacidade desejada: 'private' (padrão), 'unlisted' ou 'public'.",
                },
                "publish_at": {
                    "type": "STRING",
                    "description": "Horário ISO 8601 para agendamento (opcional).",
                },
                "channel": {
                    "type": "STRING",
                    "description": "Canal de destino para o envio do vídeo.",
                },
                "confirmation_token": {
                    "type": "STRING",
                    "description": "Token de confirmação da 1ª etapa, enviado somente após o usuário responder 'Sim'.",
                },
            },
            "required": ["file_path", "title"],
        },
    },
    {
        "name": "delete_youtube_video",
        "description": (
            "Exclui permanentemente um único vídeo de um canal do YouTube em 2 etapas estritas. "
            "Na 1ª etapa (sem confirmation_token), verifica se o vídeo pertence ao canal e retorna o nome exato do canal e do vídeo. "
            "Na 2ª etapa (somente após o usuário confirmar verbalmente), exige o confirmation_token mais "
            "confirm_channel_name e confirm_video_title idênticos aos originais."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "video_id": {
                    "type": "STRING",
                    "description": "ID do único vídeo a ser excluído.",
                },
                "channel": {
                    "type": "STRING",
                    "description": "Nome ou ID do canal proprietário do vídeo (obrigatório).",
                },
                "confirm_channel_name": {
                    "type": "STRING",
                    "description": "Nome exato do canal (obrigatório na 2ª etapa para confirmar a exclusão).",
                },
                "confirm_video_title": {
                    "type": "STRING",
                    "description": "Título exato do vídeo (obrigatório na 2ª etapa para confirmar a exclusão).",
                },
                "confirmation_token": {
                    "type": "STRING",
                    "description": "Token de uso único gerado na 1ª etapa, enviado apenas após confirmação explícita do usuário.",
                },
            },
            "required": ["video_id", "channel"],
        },
    },
    {
        "name": "authenticate_youtube",
        "description": (
            "Inicia o fluxo interativo OAuth 2.0 Desktop no navegador para conectar uma conta Google "
            "(ex.: cursopb@gmail.com ou servpb@gmail.com) e autorizar um canal ou Conta de Marca do YouTube."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "expected_email": {
                    "type": "STRING",
                    "description": "E-mail esperado da conta Google (ex.: 'cursopb@gmail.com' ou 'servpb@gmail.com').",
                },
                "mode": {
                    "type": "STRING",
                    "description": "Modo de escopos OAuth: 'manage' (padrão, leitura + escrita/upload) ou 'readonly' (somente leitura).",
                },
            },
        },
    },
    {
        "name": "check_youtube_connection",
        "description": (
            "Verifica passivamente (sem abrir navegador) o status das conexões OAuth do YouTube, "
            "lista os canais ativos e verifica o canal UCYCmXtIR-tbWCyrwbLdczyA."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "account": {
                    "type": "STRING",
                    "description": "Opcional. E-mail da conta para filtrar o diagnóstico.",
                }
            },
        },
    },
    {
        "name": "remove_youtube_account",
        "description": (
            "Desconecta um canal do YouTube ou conta Google do Aton removendo o token local "
            "(e opcionalmente revogando o token nos servidores do Google se revoke_remote=True)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "target": {
                    "type": "STRING",
                    "description": "E-mail da conta Google, ID do canal (UC...) ou nome do canal a desconectar.",
                },
                "revoke_remote": {
                    "type": "BOOLEAN",
                    "description": "Se True, também solicita revogação remota do token OAuth nos servidores do Google.",
                },
            },
            "required": ["target"],
        },
    },
]


def dispatch_youtube_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Route a YouTube tool call by name."""
    args = args or {}
    if name == "list_youtube_channels":
        return list_youtube_channels(account=args.get("account"))
    if name == "get_youtube_channel_stats":
        return get_youtube_channel_stats(
            channel=str(args.get("channel", "")),
            start_date=args.get("start_date"),
            end_date=args.get("end_date"),
        )
    if name == "list_youtube_videos":
        return list_youtube_videos(
            channel=str(args.get("channel", "")),
            max_results=int(args.get("max_results", 10) or 10),
            query=args.get("query"),
        )
    if name == "get_youtube_video_details":
        return get_youtube_video_details(
            video_id=str(args.get("video_id", "")),
            channel=args.get("channel"),
        )
    if name == "list_youtube_comments":
        return list_youtube_comments(
            video_id=str(args.get("video_id", "")),
            channel=args.get("channel"),
            max_results=int(args.get("max_results", 10) or 10),
        )
    if name == "reply_to_youtube_comment":
        return reply_to_youtube_comment(
            comment_id=str(args.get("comment_id", "")),
            reply_text=str(args.get("reply_text", "")),
            channel=args.get("channel"),
            confirmation_token=args.get("confirmation_token"),
        )
    if name == "update_youtube_video_metadata":
        return update_youtube_video_metadata(
            video_id=str(args.get("video_id", "")),
            channel=args.get("channel"),
            title=args.get("title"),
            description=args.get("description"),
            tags=args.get("tags"),
            category_id=args.get("category_id"),
            privacy_status=args.get("privacy_status"),
            publish_at=args.get("publish_at"),
            confirmation_token=args.get("confirmation_token"),
        )
    if name == "upload_youtube_video":
        return upload_youtube_video(
            file_path=str(args.get("file_path", "")),
            title=str(args.get("title", "")),
            description=str(args.get("description", "") or ""),
            tags=args.get("tags"),
            category_id=str(args.get("category_id", "22") or "22"),
            privacy_status=str(args.get("privacy_status", "private") or "private"),
            publish_at=args.get("publish_at"),
            channel=args.get("channel"),
            confirmation_token=args.get("confirmation_token"),
        )
    if name == "delete_youtube_video":
        return delete_youtube_video(
            video_id=str(args.get("video_id", "")),
            channel=str(args.get("channel", "")),
            confirm_channel_name=str(args.get("confirm_channel_name", "") or ""),
            confirm_video_title=str(args.get("confirm_video_title", "") or ""),
            confirmation_token=args.get("confirmation_token"),
        )
    if name == "authenticate_youtube":
        return authenticate_youtube(
            expected_email=args.get("expected_email"),
            mode=str(args.get("mode", "manage") or "manage"),
        )
    if name == "check_youtube_connection":
        return check_youtube_connection(account=args.get("account"))
    if name == "remove_youtube_account":
        return remove_youtube_account(
            target=str(args.get("target", "")),
            revoke_remote=bool(args.get("revoke_remote", False)),
        )
    return {"status": "error", "message": f"Ferramenta do YouTube desconhecida: {name}"}

