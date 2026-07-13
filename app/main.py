import os
from datetime import datetime
from typing import List

from app.rss_runner import fetch_new_items, RssItem
from app.nvidia_llm import analyze_news
from app.telegram import send_telegram_long


# 1) RSS 주소들을 여기에 넣으세요 (여러 개 가능)
RSS_URLS: List[str] = [
    "http://www.yonhapnewstv.co.kr/category/news/politics/feed/",
    "http://www.yonhapnewstv.co.kr/category/news/economy/feed/",
    "http://www.yonhapnewstv.co.kr/category/news/society/feed/"
]


def build_analysis_prompt(items: List[RssItem]) -> str:
    """
    수집된 뉴스 항목을 하나의 프롬프트로 묶어 주가 영향 분석 요청.
    """
    lines = []
    for idx, it in enumerate(items, start=1):
        body = it.summary or it.content_html or ""
        body = body.strip()
        # 프롬프트가 과도하게 길어지지 않도록 본문 길이 제한
        if len(body) > 800:
            body = body[:800] + "...(생략)"
        lines.append(f"[{idx}] 제목: {it.title}")
        if it.published:
            lines.append(f"    게시일: {it.published}")
        if body:
            lines.append(f"    내용: {body}")

    news_block = "\n".join(lines)

    return f"""아래는 수집된 뉴스 목록입니다. 이 뉴스들을 바탕으로 내일 한국 주식 시장에
긍정적 또는 부정적 영향을 줄 만한 이슈를 요약하고, 관련 종목/섹터와 그 근거를 한국어로 마크업 형식이 아닌 반정형 텍스트 형식으로 정리해 주세요.
[뉴스 목록]
{news_block}
"""


def main() -> None:
    if not RSS_URLS:
        raise RuntimeError("RSS_URLS가 비어있습니다. app/main.py에 RSS 주소를 추가하세요.")

    new_items, state = fetch_new_items(RSS_URLS, max_per_feed=30)

    if not new_items:
        print("새 RSS 항목 없음")
        # 신규 항목이 없어도 state는 동일하므로 굳이 저장하지 않음
        return

    print(f"새 RSS 항목 {len(new_items)}개 발견")

    # 1) NVIDIA LLM을 통한 주가 영향 분석 (배치 요약)
    prompt = build_analysis_prompt(new_items)
    print("[LLM] 분석 요청 중...")
    analysis = analyze_news(prompt)
    print("[LLM] 분석 완료")
    print(analysis)

    # 2) 텔레그램 발송
    header = f"📈 일일 뉴스 주가 영향 분석 ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n"
    send_telegram_long(header + analysis)
    print("[TELEGRAM] 발송 완료")

    # 3) state.json에 분석 결과 기록 후 저장
    if "analyses" not in state:
        state["analyses"] = []
    state["analyses"].append({
        "generated_at": datetime.now().isoformat(),
        "item_count": len(new_items),
        "analysis": analysis,
    })
    state["analyses"] = state["analyses"][-50:]

    from app.rss_runner import save_state
    save_state(state)
    print("[STATE] 저장 완료")


if __name__ == "__main__":
    main()
