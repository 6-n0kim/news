import os
import dotenv
import requests
import threading

dotenv.load_dotenv()

# CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CHAT_ID = os.getenv("TELEGRAM_GROUP_ID")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


def send_telegram_message_sync(message, parse_mode=None):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message}
        if parse_mode:
            payload["parse_mode"] = parse_mode
            payload["disable_web_page_preview"] = True
        requests.post(url, data=payload, timeout=5)
    except Exception as e:
        print(f"  [TELEGRAM ERROR] {e}")


def send_telegram_message(message, parse_mode=None):
    threading.Thread(
        target=send_telegram_message_sync,
        args=(message,),
        kwargs={"parse_mode": parse_mode},
        daemon=True,
    ).start()


def send_telegram_long(message: str, parse_mode=None, max_len: int = 4000) -> None:
    """
    텔레그램 메시지 길이 제한(4096자)을 넘을 경우 청크로 나누어 발송.
    """
    if not message:
        return

    chunks = []
    for i in range(0, len(message), max_len):
        chunk = message[i:i + max_len]
        if len(chunks) > 0:
            chunk = f"(계속 {len(chunks) + 1})\n{chunk}"
        chunks.append(chunk)

    for chunk in chunks:
        send_telegram_message_sync(chunk, parse_mode=parse_mode)
