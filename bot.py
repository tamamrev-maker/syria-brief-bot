import os
import json
import asyncio
import logging
import time
from datetime import datetime
import pytz
import re

import anthropic
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from telegram.constants import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_KEY  = os.environ["ANTHROPIC_KEY"]
GROUP_CHAT_ID  = int(os.environ["GROUP_CHAT_ID"])
SEND_HOUR      = int(os.environ.get("SEND_HOUR", "7"))
SEND_MINUTE    = int(os.environ.get("SEND_MINUTE", "0"))
TIMEZONE       = os.environ.get("TIMEZONE", "Asia/Damascus")
COUNTRY        = os.environ.get("COUNTRY", "Syria")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

GOVS = "دمشق،ريف دمشق،حلب،حمص،حماه،اللاذقية،طرطوس،إدلب،درعا،السويداء،القنيطرة،دير الزور،الرقة،الحسكة"

def clean_json(text):
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return text

def safe_parse(raw):
    match = re.search(r'\{[\s\S]*\}', raw)
    if not match:
        raise ValueError("No JSON found")
    s = match.group()
    try:
        return json.loads(s)
    except Exception:
        return json.loads(clean_json(s))

def call_api(prompt, max_tokens=2000, use_search=False):
    tools = [{"type": "web_search_20250305", "name": "web_search"}] if use_search else []
    last_err = None
    for attempt in range(3):
        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=max_tokens,
                tools=tools if tools else None,
                messages=[{"role": "user", "content": prompt}]
            )
            return "".join(b.text for b in response.content if hasattr(b, "text") and b.text)
        except anthropic.RateLimitError as e:
            last_err = e
            wait = 30 * (attempt + 1)
            log.warning(f"Rate limit, waiting {wait}s...")
            time.sleep(wait)
        except Exception as e:
            raise e
    raise last_err

def generate_brief(country=None):
    country = country or COUNTRY
    now = datetime.now(pytz.timezone(TIMEZONE))
    today_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    day_month = now.strftime("%B %d")

    prompt = (
        "Arabic editor. " + today_str + " " + time_str + " Damascus.\n"
        "Search " + country + " news last 12h: security, politics, govs (" + GOVS + "), minorities, economy. Also find history on " + day_month + ".\n"
        'JSON only: {"summary":"s","items":[{"title":"t","summary":"s","angle":"a","publishedAt":"p","source":"src","governorate":"g","carousel":"c","video":"v","thread":"th"}],"trends":[{"text":"t","platform":"p","reason":"r"}],"on_this_day":[{"year":"y","event":"e","era":"pre2011/revolution"}]}\n'
        "6 items, 4 trends, 4 on_this_day. Short Arabic, no newlines in values."
    )
    raw = call_api(prompt, max_tokens=3000, use_search=True)
    return safe_parse(raw)

def analyze_news(text):
    prompt = (
        "أنت مدير تحريري متخصص في الشأن السوري.\n"
        "حلل هذا الخبر أو النص وأعطني:\n"
        "1. ملخص تحريري\n"
        "2. الزاوية الأهم للتغطية\n"
        "3. السياق والخلفية\n"
        "4. أفكار محتوى:\n"
        "   - كاروسيل انستغرام\n"
        "   - فيديو قصير\n"
        "   - ثريد تويتر\n"
        "5. أسئلة يجب البحث عنها\n\n"
        "الخبر:\n" + text
    )
    return call_api(prompt, max_tokens=1500, use_search=False)

def esc(text):
    if not text:
        return ""
    special = r'_*[]()~`>#+-=|{}.!'
    return "".join(("\\" + c) if c in special else c for c in str(text))

def split_messages(text, max_len=4000):
    parts = []
    while len(text) > max_len:
        split_at = text.rfind("\n\n", 0, max_len)
        if split_at == -1:
            split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        parts.append(text[:split_at])
        text = text[split_at:].lstrip()
    if text:
        parts.append(text)
    return parts

def format_brief(data, country=None):
    country = country or COUNTRY
    now = datetime.now(pytz.timezone(TIMEZONE))
    date_str = now.strftime("%d/%m/%Y %H:%M")

    lines = [
        "📋 *البريفينج التحريري اليومي*",
        esc(country) + " \\| " + esc(date_str),
        "",
        "_" + esc(data.get("summary", "")) + "_",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    for i, item in enumerate(data.get("items", []), 1):
        meta_parts = []
        if item.get("governorate"): meta_parts.append("📍" + esc(item["governorate"]))
        if item.get("publishedAt"): meta_parts.append(esc(item["publishedAt"]))
        if item.get("source"): meta_parts.append(esc(item["source"]))

        lines += ["", "📰 *" + str(i) + "\\. " + esc(item.get("title", "")) + "*"]
        if meta_parts:
            lines.append("_" + " \\| ".join(meta_parts) + "_")
        lines += [
            esc(item.get("summary", "")),
            "↳ _" + esc(item.get("angle", "")) + "_",
            "🎠 " + esc(item.get("carousel", "")),
            "🎬 " + esc(item.get("video", "")),
            "🧵 " + esc(item.get("thread", "")),
        ]

    trends = data.get("trends", [])
    if trends:
        lines += ["", "━━━━━━━━━━━━━━━━━━━━", "*ترندات اليوم:*", ""]
        icons = {"Twitter": "🐦", "Facebook": "📘", "news": "📰"}
        for t in trends:
            if isinstance(t, dict):
                icon = icons.get(t.get("platform", ""), "🔥")
                lines.append(icon + " *" + esc(t.get("text", "")) + "* — " + esc(t.get("reason", "")))

    on_this_day = data.get("on_this_day", [])
    pre = [e for e in on_this_day if isinstance(e, dict) and e.get("era") == "pre2011"]
    rev = [e for e in on_this_day if isinstance(e, dict) and e.get("era") == "revolution"]

    if pre or rev:
        lines += ["", "━━━━━━━━━━━━━━━━━━━━", "*في مثل هذا اليوم:*"]
    if pre:
        lines += ["", "🏛 *تاريخ سوريا:*"]
        for ev in pre:
            lines.append("• *" + esc(ev.get("year", "")) + "* — " + esc(ev.get("event", "")))
    if rev:
        lines += ["", "🔴 *الثورة السورية:*"]
        for ev in rev:
            lines.append("• *" + esc(ev.get("year", "")) + "* — " + esc(ev.get("event", "")))

    lines += ["", "━━━━━━━━━━━━━━━━━━━━", "🤖 _14 محافظة \\| اخر 12 ساعة_"]
    return "\n".join(lines)

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 البريفينج التحريري السوري\n\n"
        "الأوامر:\n"
        "/brief — بريفينج سوريا الصباحي\n"
        "/brief لبنان — بريفينج لبلد آخر\n\n"
        "💡 أو أرسل أي خبر أو نص مباشرة وسأحلله لك فوراً"
    )

async def cmd_brief(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    country = " ".join(ctx.args) if ctx.args else COUNTRY
    msg = await update.message.reply_text("⏳ جاري تحضير البريفينج...")
    try:
        data = generate_brief(country)
        text = format_brief(data, country)
        parts = split_messages(text)
        await msg.edit_text(parts[0], parse_mode=ParseMode.MARKDOWN_V2)
        for part in parts[1:]:
            await update.message.reply_text(part, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        log.error("Brief error: " + str(e))
        await msg.edit_text("خطأ: " + str(e))

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text or len(text) < 10:
        return
    msg = await update.message.reply_text("🔍 جاري تحليل الخبر...")
    try:
        analysis = analyze_news(text)
        parts = split_messages(analysis)
        await msg.edit_text(parts[0])
        for part in parts[1:]:
            await update.message.reply_text(part)
    except Exception as e:
        log.error("Analysis error: " + str(e))
        await msg.edit_text("خطأ في التحليل: " + str(e))

async def send_daily_brief(bot: Bot):
    try:
        data = generate_brief(COUNTRY)
        text = format_brief(data, COUNTRY)
        for part in split_messages(text):
            await bot.send_message(chat_id=GROUP_CHAT_ID, text=part, parse_mode=ParseMode.MARKDOWN_V2)
        log.info("Daily brief sent.")
    except Exception as e:
        log.error("Failed: " + str(e))
        await bot.send_message(chat_id=GROUP_CHAT_ID, text="فشل: " + str(e))

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("brief", cmd_brief))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        lambda: asyncio.ensure_future(send_daily_brief(app.bot)),
        trigger="cron", hour=SEND_HOUR, minute=SEND_MINUTE,
    )
    scheduler.start()
    log.info("Bot running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
