import json
import os
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

import feedparser


STATE_PATH = os.path.join(os.path.dirname(__file__), "state.json")


@dataclass
class RssItem:
    id: str                  # guid 또는 link
    title: str
    link: str
    published: str
    author: str              # dc:creator 등
    summary: str             # description/summary
    content_html: str        # content:encoded (있으면), 없으면 ""


def load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_PATH):
        return {"seen_ids": []}
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: Dict[str, Any]) -> None:
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _get_entry_id(e) -> str:
    guid = getattr(e, "id", None) or getattr(e, "guid", None)
    link = getattr(e, "link", None)
    item_id = (guid or link or "").strip()
    return item_id


def _get_author(e) -> str:
    # dc:creator → feedparser에서 보통 dc_creator로 들어옴
    author = getattr(e, "dc_creator", None)
    if author:
        return str(author).strip()

    # fallback: author 필드
    author = getattr(e, "author", None)
    if author:
        return str(author).strip()

    # fallback: authors 리스트
    authors = getattr(e, "authors", None)
    if authors and isinstance(authors, list) and len(authors) > 0:
        name = authors[0].get("name")
        if name:
            return str(name).strip()

    return ""


def _get_content_encoded_html(e) -> str:
    """
    content:encoded (RSS 2.0 content module)
    feedparser: entry.content = [{"value": "...", "type": "text/html"}] 형태로 들어오는 경우가 많음
    """
    content = getattr(e, "content", None)
    if content and isinstance(content, list) and len(content) > 0:
        value = content[0].get("value")
        if value:
            return str(value).strip()
    return ""


def _get_summary(e) -> str:
    # RSS description → feedparser에서 보통 summary로 들어옴
    summary = getattr(e, "summary", None) or getattr(e, "description", None)
    if summary:
        return str(summary).strip()
    return ""


def _get_published(e) -> str:
    published = getattr(e, "published", None) or getattr(e, "updated", None)
    if published:
        return str(published).strip()
    return ""


def fetch_new_items(rss_urls: List[str], max_per_feed: int = 30) -> List[RssItem]:
    state = load_state()
    seen = set(state.get("seen_ids", []))

    new_items: List[RssItem] = []

    for url in rss_urls:
        feed = feedparser.parse(url)
        entries = feed.entries[:max_per_feed]

        for e in entries:
            item_id = _get_entry_id(e)
            if not item_id:
                continue

            if item_id in seen:
                continue

            title = str(getattr(e, "title", "")).strip()
            link = str(getattr(e, "link", "")).strip()
            published = _get_published(e)
            author = _get_author(e)
            content_html = _get_content_encoded_html(e)
            summary = _get_summary(e)

            new_items.append(
                RssItem(
                    id=item_id,
                    title=title,
                    link=link,
                    published=published,
                    author=author,
                    summary=summary,
                    content_html=content_html,
                )
            )

    # seen 업데이트 (너무 커지면 최근 N개만 유지)
    if new_items:
        for it in new_items:
            seen.add(it.id)
        state["seen_ids"] = list(seen)[-3000:]  # 필요하면 조절
        save_state(state)

    return new_items
