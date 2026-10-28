import io
import os
import re
import threading
from urllib.parse import urlparse, urlunparse

import requests
from flask import Flask, request, jsonify
from openpyxl import Workbook

app = Flask(__name__)
TOKEN = os.getenv("BOT_TOKEN", "").strip()
API = f"https://api.telegram.org/bot{TOKEN}" if TOKEN else ""

# Official Instagram API credentials are optional. They must belong to an
# Instagram professional account (Business/Creator) authorized for this app.
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN", "").strip()
IG_USER_ID = os.getenv("IG_USER_ID", "").strip()
IG_API_VERSION = os.getenv("IG_API_VERSION", "v26.0").strip()
IG_API = f"https://graph.instagram.com/{IG_API_VERSION}"


def telegram(method, data=None, files=None):
    if not API:
        return None
    try:
        return requests.post(f"{API}/{method}", data=data or {}, files=files, timeout=30)
    except requests.RequestException:
        return None


def send(chat_id, text):
    telegram("sendMessage", {"chat_id": chat_id, "text": text})


def instagram_permalink(text):
    # Accept standard post/reel links even when surrounded by punctuation.
    match = re.search(
        r"https?://(?:www\\.)?instagram\\.com/(p|reel|tv)/([A-Za-z0-9_-]+)(?:/)?(?:\\?[^\\s]*)?",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    kind = match.group(1).lower()
    shortcode = match.group(2)
    return f"https://www.instagram.com/{kind}/{shortcode}/"


def contains_instagram_url(text):
    return bool(re.search(r"https?://(?:[a-z0-9-]+\\.)?instagram\\.com/[^\\s]+", text, re.IGNORECASE))

def ig_get(path, params=None):
    if not IG_ACCESS_TOKEN:
        raise RuntimeError("توکن رسمی اینستاگرام تنظیم نشده است.")
    query = dict(params or {})
    query["access_token"] = IG_ACCESS_TOKEN
    response = requests.get(f"{IG_API}/{path.lstrip('/')}", params=query, timeout=30)
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if not response.ok or "error" in payload:
        error = payload.get("error", {})
        message = error.get("message", "خطای نامشخص از Instagram API")
        raise RuntimeError(message)
    return payload


def fetch_comments_for_owned_post(permalink):
    """Fetch comments only if the link belongs to media exposed by the authorized IG account."""
    if not IG_USER_ID or not IG_ACCESS_TOKEN:
        raise RuntimeError("تنظیمات رسمی اینستاگرام هنوز کامل نیست.")
    target = permalink.rstrip("/")
    next_url = None
    params = {"fields": "id,permalink", "limit": 100}
    media_id = None

    # Search media visible through the authorized professional account.
    for _ in range(20):
        if next_url:
            response = requests.get(next_url, timeout=30)
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            if not response.ok or "error" in payload:
                error = payload.get("error", {})
                raise RuntimeError(error.get("message", "دریافت فهرست پست‌ها ناموفق بود."))
        else:
            payload = ig_get(f"{IG_USER_ID}/media", params)
        for media in payload.get("data", []):
            if (media.get("permalink") or "").rstrip("/") == target:
                media_id = media.get("id")
                break
        if media_id:
            break
        next_url = (payload.get("paging") or {}).get("next")
        if not next_url:
            break

    if not media_id:
        raise RuntimeError(
            "این پست در فهرست پست‌های حساب حرفه‌ای متصل‌شده پیدا نشد. "
            "این روش برای پست‌های دلخواه دیگران کار نمی‌کند."
        )

    rows = []
    next_url = None
    params = {"fields": "id,username,text,timestamp", "limit": 100}
    for _ in range(100):
        if next_url:
            response = requests.get(next_url, timeout=30)
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            if not response.ok or "error" in payload:
                error = payload.get("error", {})
                raise RuntimeError(error.get("message", "دریافت کامنت‌ها ناموفق بود."))
        else:
            payload = ig_get(f"{media_id}/comments", params)
        for comment in payload.get("data", []):
            rows.append([
                comment.get("username", ""),
                comment.get("text", ""),
                comment.get("id", ""),
                comment.get("timestamp", ""),
            ])
        next_url = (payload.get("paging") or {}).get("next")
        if not next_url:
            break
    return rows


def send_excel(chat_id, rows, caption):
    book = Workbook()
    sheet = book.active
    sheet.title = "Comments"
    sheet.append(["Username", "Comment", "Comment ID", "Timestamp"])
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    buffer.seek(0)
    telegram(
        "sendDocument",
        {"chat_id": chat_id, "caption": caption},
        {"document": ("Robot_VT_comments.xlsx", buffer.getvalue(),
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )


def make_excel(chat_id, lines):
    rows = []
    for line in lines:
        if "|" in line:
            username, comment = line.split("|", 1)
            rows.append([username.strip(), comment.strip(), "", ""])
    if not rows:
        send(chat_id, "فرمت درست نبود. هر کامنت را در یک خط بفرست: نام‌کاربری | متن کامنت")
        return
    send_excel(chat_id, rows, f"Robot V.T — {len(rows)} کامنت در فایل Excel")


def handle(update):
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()
    if not chat_id or not text:
        return

    if text.startswith("/start"):
        send(
            chat_id,
            "سلام! 🤖 به Robot V.T خوش آمدی.\n\n"
            "لینک پست یا Reel را بفرست تا بررسی کنم آیا از طریق API رسمی و حساب متصل‌شده قابل دریافت است یا نه. "
            "دریافت خودکار فقط برای محتوایی ممکن است که حساب حرفه‌ای مجاز به آن دسترسی داشته باشد؛ "
            "پست‌های دلخواه دیگران قابل استخراج نیستند.\n\n"
            "برای ساخت Excel دستی، هر کامنت را در یک خط با فرمت «نام‌کاربری | متن کامنت» بفرست."
        )
        return
    if text.startswith("/help"):
        send(
            chat_id,
            "برای دریافت کامنت با API رسمی، مدیر ربات باید IG_ACCESS_TOKEN و IG_USER_ID را در Render تنظیم کند "
            "و دسترسی لازم را برای حساب حرفه‌ای Business/Creator بدهد. رمز اینستاگرام را هرگز برای ربات نفرست.\n\n"
            "ساخت Excel دستی: نام‌کاربری | متن کامنت"
        )
        return

    permalink = instagram_permalink(text)
    if contains_instagram_url(text) and not permalink:
        send(
            chat_id,
            "این لینک از اینستاگرام است، اما لینک مستقیم پست یا Reel نیست. "
            "لطفاً خود پست را باز کن و از گزینه اشتراک‌گذاری، Copy link را بزن و همان لینک را بفرست."
        )
        return

    if permalink:
        if not IG_ACCESS_TOKEN or not IG_USER_ID:
            send(
                chat_id,
                "لینک دریافت شد؛ اما اتصال رسمی اینستاگرام هنوز تنظیم نشده است.\n\n"
                "برای فعال‌سازی باید یک حساب Instagram حرفه‌ای (Business یا Creator) را به اپ Meta مجاز کنی "
                "و متغیرهای IG_ACCESS_TOKEN و IG_USER_ID را در Render اضافه کنی. "
                "این API کامنت‌های پست‌های حساب مجاز را می‌خواند، نه هر پست عمومی دیگران."
            )
            return
        send(chat_id, "دارم بررسی می‌کنم آیا این پست در حساب اینستاگرام مجازشده قرار دارد…")
        try:
            rows = fetch_comments_for_owned_post(permalink)
            if not rows:
                send(chat_id, "پست پیدا شد، اما API هیچ کامنتی برنگرداند.")
                return
            send_excel(chat_id, rows, f"Robot V.T — {len(rows)} کامنت دریافت شد")
        except Exception as exc:
            # Avoid leaking tokens; only the API error message is sent.
            send(chat_id, f"نتوانستم کامنت‌ها را دریافت کنم: {str(exc)[:700]}")
        return

    make_excel(chat_id, text.splitlines())


@app.get("/")
def home():
    return "Robot V.T is running.", 200


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "bot_token_configured": bool(TOKEN),
        "instagram_api_configured": bool(IG_ACCESS_TOKEN and IG_USER_ID),
    })


@app.post("/telegram-webhook")
def webhook():
    update = request.get_json(silent=True) or {}
    threading.Thread(target=handle, args=(update,), daemon=True).start()
    return jsonify({"ok": True})


@app.get("/setup-webhook")
def setup_webhook():
    if not TOKEN:
        return jsonify({"ok": False, "error": "BOT_TOKEN is missing"}), 400
    base = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    if not base:
        return jsonify({"ok": False, "error": "Set RENDER_EXTERNAL_URL to the deployed HTTPS URL"}), 400
    response = telegram("setWebhook", {"url": base + "/telegram-webhook"})
    if not response:
        return jsonify({"ok": False, "error": "Telegram API request failed"}), 502
    return response.text, response.status_code
