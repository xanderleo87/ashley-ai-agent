import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

# Google OAuth app credentials (shared across all users)
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")

# Default timezone (used as fallback)
DEFAULT_TIMEZONE = os.getenv("TIMEZONE", "Asia/Manila")
TIMEZONE = DEFAULT_TIMEZONE

# OAuth Web Server
OAUTH_PORT = int(os.getenv("OAUTH_PORT", "5050"))
OAUTH_BASE_URL = os.getenv("OAUTH_BASE_URL", f"http://localhost:{OAUTH_PORT}")

# Apify (Google Maps Scraper)
APIFY_API_KEY = os.getenv("APIFY_API_KEY", "")
