import io
import os
import re
import threading
import requests
import instaloader
from flask import Flask, request, jsonify
from openpyxl import Workbook

app = Flask(__name__)
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BASE = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else ""
_busy = set()
_lock = threading.Lock()

def tg(method, data=None, files=None, timeout=25):
    if not BASE:
        return None
    try:
        return requests.post(f"{BASE}/{method}", data=data or {}, files=files, timeout=timeout)
    except requests.RequestException:
        return None

def send_message(chat_id, text):
    tg("sendMessage", {"chat_id": chat_id, "text": text})

def extract_shortcode(url):
    match = re.search(r"instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)", url)
    return match.group(1) if match else None

def process_instagram(chat_id, url):
    shortcode = extract_shortcode(url)
    if not shortcode:
        send_message(chat_id, "لینک معتبر پست یا ریلز پیدا نشد. لینک عمومی اینستاگرام را دوباره بفرست.")
        return
    send_message(chat_id, "لینک دریافت شد. در حال بررسی کامنت‌های عمومی؛ ممکن است اینستاگرام دسترسی را محدود کند...")
    try:
        loader = instaloader.Instaloader(quiet=True, download_pictures=False,
                                        download_videos=False, download_video_thumbnails=False,
                                        save_metadata=False, compress_json=False)
        post = instaloader.Post.from_shortcode(loader.context, shortcode)
        rows = []
        for comment in post.get_comments():
            owner = getattr(comment, "owner", None)
            username = getattr(owner, "username", "") if owner else ""
            numeric_id = getattr(owner, "userid", "") if owner else ""
            rows.append([username, str(numeric_id) if numeric_id else "", getattr(comment, "text", "")])
        if not rows:
            send_message(chat_id, "کامنتی دریافت نشد. ممکن است پست کامنت نداشته باشد یا اینستاگرام دسترسی را محدود کرده باشد.")
            return
        wb = Workbook()
        ws = wb.active
        ws.title = "Comments"
        ws.append(["Username", "Numeric user ID (if available)", "Comment"])
        for row in rows:
            ws.append(row)
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        tg("sendDocument", {"chat_id": chat_id, "caption": f"Robot V.T — {len(rows)} کامنت دریافت شد."},
           files={"document": ("Robot_VT_comments.xlsx", output.getvalue(),
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}, timeout=60)
        send_message(chat_id, f"تمام شد: {len(rows)} کامنت در فایل Excel آماده شد. توجه: فقط اطلاعاتی که منبع در دسترس قرار داد وارد فایل شده است.")
    except Exception:
        send_message(chat_id, "نتوانستم کامنت‌ها را دریافت کنم. اینستاگرام ممکن است دسترسی سرور را مسدود کرده باشد یا پست محدود باشد. لینک عمومی دیگری را امتحان کن.")

def handle_update(update):
    message = update.get("message") or update.get("edited_message")
    if not message or not message.get("chat"):
        return
    chat_id = message["chat"]["id"]
    text = (message.get("text") or "").strip()
    if text.startswith("/start"):
        send_message(chat_id, "سلام! 🤖 من Robot V.T هستم.\n\nلینک عمومی پست یا ریلز اینستاگرام را بفرست تا تلاش کنم کامنت‌های قابل‌دسترسی را در فایل Excel آماده کنم.\n\nمحدودیت: اینستاگرام ممکن است دسترسی را مسدود کند؛ دریافت همهٔ پست‌ها و همهٔ کامنت‌ها تضمین‌شده نیست.")
        return
    if text.startswith("/help"):
        send_message(chat_id, "فقط لینک عمومی یک پست یا ریلز اینستاگرام را بفرست. هرگز رمز اینستاگرام خود را ارسال نکن.")
        return
    shortcode = extract_shortcode(text)
    if shortcode:
        with _lock:
            if chat_id in _busy:
                send_message(chat_id, "درخواست قبلی هنوز در حال بررسی است؛ کمی صبر کن.")
                return
            _busy.add(chat_id)
        try:
            process_instagram(chat_id, text)
        finally:
            with _lock:
                _busy.discard(chat_id)
    else:
        send_message(chat_id, "لطفاً لینک کامل یک پست یا ریلز عمومی اینستاگرام را بفرست. برای راهنما /help را بزن.")

@app.get("/")
def home():
    return "Robot V.T is running.", 200

@app.get("/health")
def health():
    return jsonify({"status": "ok", "bot_token_configured": bool(BOT_TOKEN)})

@app.post("/telegram-webhook")
def telegram_webhook():
    update = request.get_json(silent=True) or {}
    threading.Thread(target=handle_update, args=(update,), daemon=True).start()
    return jsonify({"ok": True})

if BOT_TOKEN and os.getenv("RENDER_EXTERNAL_URL"):
    try:
        tg("setWebhook", {"url": os.getenv("RENDER_EXTERNAL_URL").rstrip("/") + "/telegram-webhook"})
    except Exception:
        pass
