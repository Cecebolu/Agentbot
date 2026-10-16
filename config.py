"""All settings come from the .env file. Copy .env.example to .env and fill it in."""
import os
from dotenv import load_dotenv

load_dotenv()

def env(key, default=None):
    return os.getenv(key, default)

# Database
DB_PATH = env("DB_PATH", "leads.db")

# Sending (SMTP)
SMTP_HOST = env("SMTP_HOST")
SMTP_PORT = int(env("SMTP_PORT", "587"))
SMTP_USER = env("SMTP_USER")
SMTP_PASS = env("SMTP_PASS")
FROM_NAME = env("FROM_NAME", "TalkSasa")
FROM_EMAIL = env("FROM_EMAIL", SMTP_USER)
DAILY_LIMIT = int(env("DAILY_LIMIT", "25"))         # start low, raise slowly
SEND_DELAY_SECONDS = int(env("SEND_DELAY_SECONDS", "90"))  # gap between emails
# A lead that has already been emailed is never emailed again unless this is "true"
FOLLOWUPS_APPROVED = env("FOLLOWUPS_APPROVED", "false").strip().lower() == "true"

# Reading replies (IMAP)
IMAP_HOST = env("IMAP_HOST")
IMAP_USER = env("IMAP_USER", SMTP_USER)
IMAP_PASS = env("IMAP_PASS", SMTP_PASS)
POLL_MINUTES = int(env("POLL_MINUTES", "5"))

# AI classifier: "ollama" (local, free, open source) or "groq" (free tier API)
AI_PROVIDER = env("AI_PROVIDER", "ollama")
OLLAMA_URL = env("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = env("OLLAMA_MODEL", "qwen2.5:7b")
GROQ_API_KEY = env("GROQ_API_KEY")
GROQ_MODEL = env("GROQ_MODEL", "openai/gpt-oss-20b")      # labels replies (classifier.py)
# "false" = templates only: no AI opener and no AI-picked uses, so every email starts with
# the template's introduction and lists the first three uses for its industry in uses.yaml.
# The AI is then used for reply classification alone. "true" turns the AI slots back on.
USE_AI_OPENER = env("USE_AI_OPENER", "false").strip().lower() == "true"
# Writes openers and picks uses (personalise.py) when AI_PROVIDER is groq.
WRITER_MODEL = env("WRITER_MODEL", "llama-3.3-70b-versatile")

# Telegram alerts
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID")

# Business details used in emails
COMPANY = env("COMPANY", "TalkSasa Communications Ltd")
SENDER_NAME = env("SENDER_NAME", "Florence")
SENDER_PHONE = env("SENDER_PHONE", "")
WEBSITE = env("WEBSITE", "https://talksasa.com")
# PDF attached to every email. Path is relative to this folder. Empty = no attachment.
ATTACH_PDF = env("ATTACH_PDF", "TalkSasa_Overview.pdf")
PROFILE_URL = env("PROFILE_URL", "")  # optional, e.g. a company profile PDF or page
