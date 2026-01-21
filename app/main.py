import os
from typing import List

from rss_runner import fetch_new_items, RssItem


# 1) RSS 주소들을 여기에 넣으세요 (여러 개 가능)
RSS_URLS: List[str] = [
    "http://www.yonhapnewstv.co.kr/category/news/politics/feed/",
    "http://www.yonhapnewstv.co.kr/category/news/economy/feed/",
    "http://www.yonhapnewstv.co.kr/category/news/society/feed/"
]


def your_existing_function(item: RssItem) -> None:
    """
    ✅ 여기에 당신이 이미 만들어 둔 파이썬 함수를 연결하세요.
    예: DB 저장, 요약 생성, 슬랙/디스코드/노션 전송, 파일 생성 등
    """
    print(f"[PROCESS] {item.published} | {item.title} | {item.link}")


def main() -> None:
    if not RSS_URLS:
        raise RuntimeError("RSS_URLS가 비어있습니다. app/main.py에 RSS 주소를 추가하세요.")

    new_items = fetch_new_items(RSS_URLS, max_per_feed=30)

    if not new_items:
        print("새 RSS 항목 없음")
        return

    # 새 글이 여러 개면 오래된 것부터 처리하고 싶으면 정렬(선택)
    # new_items.reverse()

    print(f"새 RSS 항목 {len(new_items)}개 발견")
    for item in new_items:
        your_existing_function(item)


if __name__ == "__main__":
    main()
