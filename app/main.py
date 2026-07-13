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
    마크다운을 배제하고 깔끔한 텍스트 템플릿 형태로 출력을 유도합니다.
    """
    lines = []
    for idx, it in enumerate(items, start=1):
        body = it.summary or it.content_html or ""
        body = body.strip()
        if len(body) > 800:
            body = body[:800] + "...(생략)"
        lines.append(f"[{idx}] 제목: {it.title}")
        if it.published:
            lines.append(f"    게시일: {it.published}")
        if body:
            lines.append(f"    내용: {body}")

    news_block = "\n".join(lines)

    return f"""아래 뉴스 목록을 분석하여 내일 한국 주식 시장에 줄 영향을 정리해 주세요.

[출력 형식 제한 사항 - 필수]
1. 마크다운(Markdown) 문법을 절대 사용하지 마세요. (예: **, ###, _, ` 및 |---| 표 형태 금지)
2. 오직 줄바꿈, 대괄호([]), 대시(-), 숫자로만 구조화된 일반 텍스트(Plain Text) 포맷으로만 출력하세요.
3. 아래 제공된 [출력 템플릿 양식]의 구조와 항목 이름을 정확히 똑같이 유지하며 내용을 채우세요.

[출력 템플릿 양식]
[시장 요약 진단]
내용: (금일 뉴스 기반의 내일 시장 심리 요약)

--------------------------------------------------
[핵심 이슈 분석]
이슈 1: (뉴스 제목 요약)
- 시장 영향도: (상 / 중 / 하)
- 예상 방향성: (긍정적 / 부정적 / 중립)

이슈 2: (뉴스 제목 요약)
- 시장 영향도: (상 / 중 / 하)
- 예상 방향성: (긍정적 / 부정적 / 중립)

--------------------------------------------------
[섹터 및 종목별 영향]
1. (섹터/테마명)
- 예상 방향: (강세 / 약세 / 변동성 확대)
- 관련 종목군: (관련 주식이나 ETF 이름 목록)
- 투자 대응: (대응 방법 요약)

2. (섹터/테마명)
- 예상 방향: (강세 / 약세 / 변동성 확대)
- 관련 종목군: (관련 주식이나 ETF 이름 목록)
- 투자 대응: (대응 방법 요약)

--------------------------------------------------
[내일 장 전략 한 줄 요약]
전략: (투자자가 취해야 할 행동 요약)

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
