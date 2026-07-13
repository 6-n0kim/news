import os
from datetime import datetime
from typing import List
from zoneinfo import ZoneInfo

from app.rss_runner import fetch_new_items
from app.llm_chain import run_pipeline
from app.telegram import send_telegram_long


# 1) RSS 주소들을 여기에 넣으세요 (여러 개 가능)
RSS_URLS: List[str] = [
    # 연합뉴스TV
    "http://www.yonhapnewstv.co.kr/category/news/politics/feed/",
    "http://www.yonhapnewstv.co.kr/category/news/economy/feed/",
    "http://www.yonhapnewstv.co.kr/category/news/society/feed/",
    # 한국경제
    "https://www.hankyung.com/feed/finance",
    "https://www.hankyung.com/feed/economy",
    # 이투데이
    "https://rss.etoday.co.kr/eto/market_news.xml",
    "https://rss.etoday.co.kr/eto/finance_news.xml",
    "https://rss.etoday.co.kr/eto/economy_news.xml",
]


def main() -> None:
    if not RSS_URLS:
        raise RuntimeError("RSS_URLS가 비어있습니다. app/main.py에 RSS 주소를 추가하세요.")

    new_items, state = fetch_new_items(RSS_URLS, max_per_feed=30)

    if not new_items:
        print("새 RSS 항목 없음")
        # 신규 항목이 없어도 state는 동일하므로 굳이 저장하지 않음
        return

    print(f"새 RSS 항목 {len(new_items)}개 발견")

    # 1) NVIDIA LLM을 통한 주가 영향 분석 (10개 단위 청크 분석 -> 종합 -> 구조화 후처리)
    print("[LLM] 분석 요청 중...")
    analysis = run_pipeline(new_items)
    print("[LLM] 분석 완료")
    print(analysis)

    # 2) 텔레그램 발송
    header = f"📈 일일 뉴스 주가 영향 분석 ({datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d %H:%M')})\n"
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
