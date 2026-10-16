"""Telegram alerts. Setup:
1. In Telegram, message @BotFather, send /newbot, copy the token.
2. Send any message to your new bot.
3. Open https://api.telegram.org/bot<TOKEN>/getUpdates and copy "chat":{"id": ...}.
"""
import requests
import config

ICONS = {"interested": "🔥", "question": "❓", "needs_review": "👀"}


def send(text):
    if not config.TELEGRAM_BOT_TOKEN:
        print("[telegram not configured]\n" + text)
        return
    requests.post(
        f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text},
        timeout=15,
    )


def lead_alert(lead, reply_from, subject, label, summary, body):
    icon = ICONS.get(label, "📩")
    company = lead["company"] if lead else "Unknown company"
    snippet = body.strip()[:400]
    send(f"{icon} {label.upper()} — {company}\n"
         f"From: {reply_from}\nSubject: {subject}\n\n"
         f"Summary: {summary}\n\n\"{snippet}\"")


if __name__ == "__main__":
    send("✅ LeadBot test message. Telegram alerts are working.")
