"""Public YouTube video search and catalog lookup for Aton (zero API quota cost)."""

import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

VIDEO_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{11}$")


def lookup_youtube_videos(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Search YouTube for verified real videos matching a query without hallucinating IDs.

    Uses standard HTTPS scraping of YouTube initial data with zero quota cost.

    Args:
        query: Search keywords (e.g. 'Como E Grande o Meu Amor por Voce Roberto Carlos').
        max_results: Maximum candidate videos to return (1 to 10).

    Returns:
        List of dicts: [{"id": "...", "title": "...", "channel": "..."}]
    """
    cleaned_query = query.strip()
    if not cleaned_query:
        return []

    url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(cleaned_query)}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        logger.warning(f"Error fetching YouTube search for '{cleaned_query}': {exc}")
        return []

    # Extract ytInitialData json
    match = re.search(r"var ytInitialData\s*=\s*({.*?});</script>", html)
    if not match:
        # Fallback to secondary regex format
        match = re.search(r"window\[\"ytInitialData\"\]\s*=\s*({.*?});", html)

    if not match:
        logger.debug("Could not parse ytInitialData from YouTube response.")
        return []

    try:
        data = json.loads(match.group(1))
    except Exception as exc:
        logger.debug(f"JSON decode error for ytInitialData: {exc}")
        return []

    results: List[Dict[str, str]] = []
    seen_ids = set()

    contents = (
        data.get("contents", {})
        .get("twoColumnSearchResultsRenderer", {})
        .get("primaryContents", {})
        .get("sectionListRenderer", {})
        .get("contents", [])
    )

    for section in contents:
        items = section.get("itemSectionRenderer", {}).get("contents", [])
        for item in items:
            renderer = item.get("videoRenderer")
            if not renderer:
                continue

            vid_id = renderer.get("videoId", "").strip()
            if not vid_id or not VIDEO_ID_REGEX.match(vid_id):
                continue

            if vid_id in seen_ids:
                continue

            # Extract title
            title_text = ""
            title_obj = renderer.get("title", {})
            if "runs" in title_obj and title_obj["runs"]:
                title_text = title_obj["runs"][0].get("text", "")
            elif "simpleText" in title_obj:
                title_text = title_obj.get("simpleText", "")

            # Extract channel
            channel_name = ""
            owner_obj = renderer.get("ownerText", {})
            if "runs" in owner_obj and owner_obj["runs"]:
                channel_name = owner_obj["runs"][0].get("text", "")

            if vid_id and title_text:
                results.append({
                    "id": vid_id,
                    "title": title_text.strip(),
                    "channel": channel_name.strip(),
                })
                seen_ids.add(vid_id)

            if len(results) >= max_results:
                break
        if len(results) >= max_results:
            break

    return results

