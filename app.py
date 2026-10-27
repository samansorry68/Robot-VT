import io
import os
import re
import threading
import requests
from flask import Flask, request, jsonify
from openpyxl import Workbook

app = Flask(__name__)
TOKEN = os.getenv("BOT_TOKEN", "").strip()
API = f"https://api.telegram.org/bot{TOKEN}" if TOKEN else ""

def telegram(method, data=None, files=None):
    if not API:
        return
    try:
        return requests.post(f"{API}/{method}", data=data or {}, files=files, timeout=30)
    except requests.RequestException:
        return

def send(chat_id, text):
    telegram("sendMessage", {"chat_id": chat_id, "text": text})

def is_instagram_link(text):
    return bool(re.search(r"https?://(?:www\\.)?instagram\\.com/(?:p|reel|tv)/[A-Za-z0-9_-]+", text))

def make_excel(chat_id, lines):
    rows = []
    for line in lines:
        if "|" in line:
            username, comment = line.split("|", 1)
            rows.append([username.strip(), comment.strip()])
    if not rows:
        send(chat_id, "فرمت درست نبود. هر کامنت را در یک خط بفرست: نام‌کاربری | متن کامنت")
        return
    book = Workbook()
    sheet = book.active
    sheet.title = "Comments"
    sheet.append(["Username", "Comment"])
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    buffer.seek(0)
    telegram("sendDocument",
             {"chat_id": chat_id, "caption": f"Robot V.T — {len(rows)} کامنت در فایل Excel"},
             {"document": ("Robot_VT_comments.xlsx", buffer.getvalue(),
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})

def handle(update):
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()
    if not chat_id or not text:
        return
    if text.startswith("/start"):
        send(chat_id, "سلام! 🤖 به Robot V.T خوش آمدی.\n\nبرای ساخت فایل Excel از کامنت‌هایی که مجاز به استفاده از آن‌ها هستی، هر کامنت را در یک خط و با فرمت «نام‌کاربری | متن کامنت» بفرست.\n\nاگر لینک اینستاگرام بفرستی، راهنمای محدودیت دسترسی را می‌دهم. استخراج خودکار از هر پست نیازمند دسترسی رسمی و مجاز است و برای همهٔ پست‌ها ممکن نیست.")
        return
    if text.startswith("/help"):
        send(chat_id, "برای خروجی Excel، هر کامنت را در خط جداگانه بنویس: نام‌کاربری | متن کامنت. رمز اینستاگرام را هرگز ارسال نکن.")
        return
    if is_instagram_link(text):
        send(chat_id, "لینک دریافت شد. استخراج خودکار کامنت‌های هر پست به دسترسی رسمی/مجاز اینستاگرام نیاز دارد و برای همهٔ پست‌ها در دسترس نیست. در این نسخه می‌توانی کامنت‌هایی را که مجاز به استفاده از آن‌ها هستی به صورت «نام‌کاربری | متن کامنت» در خط‌های جدا بفرستی تا فایل Excel ساخته شود.")
        return
    make_excel(chat_id, text.splitlines())

@app.get("/")
def home():
    return "Robot V.T is running.", 200

@app.get("/health")
def health():
    return jsonify({"status": "ok", "bot_token_configured": bool(TOKEN)})

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
    return (response.text if response else "Telegram API request failed"), 200
