"""
News & Market Briefing Bot
===========================
Sends formatted news and stock market updates via WhatsApp (Twilio)
and Telegram at 8 AM, 3 PM, and 9 PM daily.

Dependencies:
    pip install requests yfinance apscheduler twilio python-telegram-bot pytz

API Keys Required:
    - NewsAPI      : https://newsapi.org/register
    - Twilio       : https://console.twilio.com (for WhatsApp)
    - Telegram Bot : https://t.me/BotFather
"""

import os
import logging
import requests
import yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo

from twilio.rest import Client as TwilioClient
import telegram
from apscheduler.schedulers.blocking import BlockingScheduler

# ─── Logging Setup ────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("briefing_bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ─── Configuration ────────────────────────────────────────────────────────────
# Replace all placeholder values before running.

CONFIG = {
    # Timezone for scheduling (e.g., "Asia/Kolkata", "America/New_York")
    "timezone": "Asia/Kolkata",

    # Schedule times (24-hour format HH:MM)
    "schedule_times": ["08:00", "15:00", "21:00"],

    # Session labels mapped to hour
    "session_labels": {8: "Morning", 15: "Afternoon", 21: "Evening"},

    # Your country for national news (ISO 3166-1 alpha-2, e.g., "in", "us", "gb")
    "country_code": "in",

"newsapi": {
    "api_key": "YOUR_NEWSAPI_KEY",

    # Stock symbols to track (Yahoo Finance format)
    "stocks": {
        "indices": ["^NSEI", "^BSESN", "^GSPC", "^IXIC"],   # NSE, BSE, S&P 500, Nasdaq
        "equities": ["RELIANCE.NS", "TCS.NS", "AAPL", "MSFT"],
    },

"twilio": {
    "account_sid": "YOUR_TWILIO_ACCOUNT_SID",
    "auth_token":  "YOUR_TWILIO_AUTH_TOKEN",
    "from_number": "whatsapp:+14155238886",
    "to_number":   "YOUR_WHATSAPP_NUMBER",
    },

"telegram": {
    "bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
    "chat_id":   "YOUR_TELEGRAM_CHAT_ID",
}

# ─── News Fetcher ─────────────────────────────────────────────────────────────

def fetch_national_news() -> list[dict]:
    """Fetch top national headlines using NewsAPI."""
    url = "https://newsapi.org/v2/top-headlines"
    params = {
        "country": CONFIG["country_code"],
        "pageSize": CONFIG["newsapi"]["national_headlines"],
        "apiKey": CONFIG["newsapi"]["api_key"],
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        articles = resp.json().get("articles", [])
        return [
            {"title": a["title"], "source": a["source"]["name"], "url": a["url"]}
            for a in articles if a.get("title")
        ]
    except Exception as e:
        log.error(f"National news fetch failed: {e}")
        return []


def fetch_international_news() -> list[dict]:
    """Fetch top international headlines using NewsAPI."""
    url = "https://newsapi.org/v2/top-headlines"
    params = {
        "language": "en",
        "pageSize": CONFIG["newsapi"]["international_headlines"],
        "apiKey": CONFIG["newsapi"]["api_key"],
        "category": "general",
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        articles = resp.json().get("articles", [])
        return [
            {"title": a["title"], "source": a["source"]["name"], "url": a["url"]}
            for a in articles if a.get("title")
        ]
    except Exception as e:
        log.error(f"International news fetch failed: {e}")
        return []

# ─── Stock Market Fetcher ──────────────────────────────────────────────────────

def fetch_stock_data() -> dict:
    """
    Fetch latest price and daily change for configured indices and equities.
    Uses yfinance (Yahoo Finance) — no API key required.
    """
    results = {"indices": [], "equities": []}

    for category, symbols in CONFIG["stocks"].items():
        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                info   = ticker.fast_info
                price  = round(info.last_price, 2)
                prev   = round(info.previous_close, 2)
                change = round(price - prev, 2)
                pct    = round((change / prev) * 100, 2) if prev else 0
                arrow  = "+" if change >= 0 else ""
                results[category].append({
                    "symbol": symbol,
                    "price":  price,
                    "change": f"{arrow}{change}",
                    "pct":    f"{arrow}{pct}%",
                })
            except Exception as e:
                log.warning(f"Stock fetch failed for {symbol}: {e}")

    return results

# ─── Message Builder ──────────────────────────────────────────────────────────

def build_message(session_label: str) -> str:
    """Build the full briefing message for a given session."""
    now_str = datetime.now(ZoneInfo(CONFIG["timezone"])).strftime("%d %b %Y, %I:%M %p")
    lines   = [f"{session_label} Briefing | {now_str}", "=" * 40]

    # National News
    lines.append("\n[National News]")
    national = fetch_national_news()
    if national:
        for i, article in enumerate(national, 1):
            lines.append(f"{i}. {article['title']} ({article['source']})")
    else:
        lines.append("No national news available.")

    # International News
    lines.append("\n[International News]")
    intl = fetch_international_news()
    if intl:
        for i, article in enumerate(intl, 1):
            lines.append(f"{i}. {article['title']} ({article['source']})")
    else:
        lines.append("No international news available.")

    # Stock Market
    lines.append("\n[Stock Market]")
    stocks = fetch_stock_data()

    if stocks["indices"]:
        lines.append("Indices:")
        for s in stocks["indices"]:
            lines.append(f"  {s['symbol']}: {s['price']} ({s['change']}, {s['pct']})")

    if stocks["equities"]:
        lines.append("Equities:")
        for s in stocks["equities"]:
            lines.append(f"  {s['symbol']}: {s['price']} ({s['change']}, {s['pct']})")

    lines.append("\n" + "=" * 40)
    return "\n".join(lines)

# ─── Message Senders ──────────────────────────────────────────────────────────

def send_whatsapp(message: str) -> None:
    """Send message via Twilio WhatsApp API."""
    try:
        cfg    = CONFIG["twilio"]
        client = TwilioClient(cfg["account_sid"], cfg["auth_token"])
        msg    = client.messages.create(
            body=message,
            from_=cfg["from_number"],
            to=cfg["to_number"]
        )
        log.info(f"WhatsApp sent. SID: {msg.sid}")
    except Exception as e:
        log.error(f"WhatsApp send failed: {e}")


def send_telegram(message: str) -> None:
    """Send message via Telegram Bot API."""
    try:
        cfg = CONFIG["telegram"]
        bot = telegram.Bot(token=cfg["bot_token"])
        bot.send_message(
            chat_id=cfg["chat_id"],
            text=message,
            parse_mode=None
        )
        log.info("Telegram message sent.")
    except Exception as e:
        log.error(f"Telegram send failed: {e}")

# ─── Core Job ─────────────────────────────────────────────────────────────────

def run_briefing() -> None:
    """Determine session label, build message, and dispatch to all channels."""
    hour  = datetime.now(ZoneInfo(CONFIG["timezone"])).hour
    label = CONFIG["session_labels"].get(hour, "Update")
    log.info(f"Running {label} briefing...")

    message = build_message(label)
    send_whatsapp(message)
    send_telegram(message)
    log.info(f"{label} briefing dispatched.")

# ─── Scheduler ────────────────────────────────────────────────────────────────

def start_scheduler() -> None:
    """Register jobs and start the blocking scheduler."""
    tz        = ZoneInfo(CONFIG["timezone"])
    scheduler = BlockingScheduler(timezone=str(tz))

    for time_str in CONFIG["schedule_times"]:
        hour, minute = map(int, time_str.split(":"))
        scheduler.add_job(
            run_briefing,
            trigger="cron",
            hour=hour,
            minute=minute,
            id=f"briefing_{hour:02d}{minute:02d}",
        )
        log.info(f"Scheduled briefing at {time_str} ({CONFIG['timezone']})")

    log.info("Scheduler started. Press Ctrl+C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped.")

# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # Run a single briefing immediately for testing
        log.info("Running test briefing...")
        run_briefing()
    else:
        start_scheduler()
