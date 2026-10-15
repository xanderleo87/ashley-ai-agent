# Ashley — AI Personal Assistant Agent

A tool-using AI agent that lives in Telegram and manages email, calendar, contacts,
tasks, and lead generation on the user's behalf. Built around **OpenAI function calling**:
the model decides which tools to invoke, the backend executes them against real Google
and Supabase APIs, and the results are fed back into the conversation loop.

## What it demonstrates

- **Agent architecture** — a clean `tools/` layer where each capability (calendar, Gmail,
  contacts, tasks, leads, insights, job search, email queue) is an independently
  testable function exposed to the model via the function-calling schema (`ai_agent.py`).
- **Real API integrations** — OpenAI, Google Calendar/Gmail (OAuth 2.0), Telegram Bot API,
  Supabase (Postgres), and Apify.
- **Multi-user design** — every tool receives a `user_id`; the system prompt and OAuth
  tokens adapt per user, with self-service Google auth via a small OAuth web server.
- **Background automation** — APScheduler jobs poll Gmail, dispatch queued emails, and
  send a daily digest (`schedulers/`).
- **Email intelligence** — an LLM reasoning module categorizes incoming mail, scores
  spam/phishing risk, and suggests actions (`reasoning.py`).
- **Production-minded** — `config.py` reads all secrets from the environment, plus a
  `systemd` unit, deploy script, and Supabase migration SQL for shipping to a server.

## Architecture

```
main.py                  Entry point — starts the bot + schedulers + OAuth server
bot.py                   Telegram interface
ai_agent.py              Function-calling loop + tool schema definitions
reasoning.py             LLM email analysis (category / urgency / spam)
tools/                   Agent tools (calendar, gmail, contacts, tasks, leads, ...)
schedulers/              Background jobs (gmail watcher, dispatcher, daily digest)
job_scanner/             Job-board scraping + parsing pipeline
google_auth.py           OAuth 2.0 flow
oauth_server.py          Per-user self-service auth web server
database.py              Supabase / Postgres data layer
```

## Running locally

```bash
pip install -r requirements.txt
cp .env.example .env        # then fill in your keys
# place your Google OAuth credentials.json in the project root
python main.py
```

> **Note:** `.env`, `credentials.json`, and `token.json` are intentionally excluded —
> they hold live secrets. Use `.env.example` as the template.

## Author

Alexander III Empleo
