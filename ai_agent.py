"""
Ashley AI Agent - OpenAI function calling with tool execution.
Multi-user: system prompt adapts per user, tools receive user_id.
"""

import json
from datetime import datetime
from openai import OpenAI
import pytz
import config
import database as db

client = OpenAI(api_key=config.OPENAI_API_KEY)

# ── Tool Definitions (OpenAI function calling format) ──

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "calendar_get_events",
            "description": "Check schedule or find an event to reschedule. Use to look up events in a time range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "time_min": {"type": "string", "description": "Start of time range in ISO 8601 format with timezone offset (e.g. 2025-12-22T00:00:00+08:00)"},
                    "time_max": {"type": "string", "description": "End of time range in ISO 8601 format with timezone offset"},
                    "query": {"type": "string", "description": "Optional text to search for in event titles"},
                },
                "required": ["time_min", "time_max"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_create_event",
            "description": "Create a meeting/event on Google Calendar. Dates must be ISO format with timezone offset.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Event title"},
                    "start_time": {"type": "string", "description": "Start time in ISO 8601 with timezone offset"},
                    "end_time": {"type": "string", "description": "End time in ISO 8601 with timezone offset"},
                    "attendee_email": {"type": "string", "description": "Attendee email address. Leave empty for solo events."},
                },
                "required": ["title", "start_time", "end_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_update_event",
            "description": "Reschedule or update an existing calendar event. Get the event_id from calendar_get_events first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "The event ID to update"},
                    "title": {"type": "string", "description": "New title (optional)"},
                    "start_time": {"type": "string", "description": "New start time in ISO 8601 with timezone offset"},
                    "end_time": {"type": "string", "description": "New end time in ISO 8601 with timezone offset"},
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_delete_event",
            "description": "Delete a calendar event by its event_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "The event ID to delete"},
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_send",
            "description": "Send an email immediately via Gmail. First find the email using contacts_get. Do not guess emails.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "message": {"type": "string", "description": "Email body content"},
                },
                "required": ["to", "subject", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_get_unread",
            "description": "Get unread emails from Gmail inbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "after_date": {"type": "string", "description": "Only get emails after this date (YYYY/MM/DD format)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "contacts_get",
            "description": "Fetch contacts list to find email addresses. Search by name or get all.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_name": {"type": "string", "description": "Name to search for (optional, returns all if empty)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "contacts_save",
            "description": "Save a new contact with name and email.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Contact name"},
                    "email": {"type": "string", "description": "Contact email"},
                },
                "required": ["name", "email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tasks_get",
            "description": "Get all tasks from the to-do list.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tasks_create",
            "description": "Add a new task to the to-do list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Task name/description"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "email_queue_schedule",
            "description": "Schedule an email for later delivery. Call this SEPARATELY for each email. Use when the user says 'later', 'schedule', or gives a specific time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient_email": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body_content": {"type": "string", "description": "Email body content"},
                    "scheduled_time": {"type": "string", "description": "When to send, in ISO 8601 with timezone offset"},
                },
                "required": ["recipient_email", "subject", "body_content", "scheduled_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "email_queue_read_pending",
            "description": "Check the email queue for pending scheduled emails.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "insights_email_stats",
            "description": "Get email analysis stats and breakdown from the last N hours. Shows categories, spam count, urgency levels, and recent emails.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hours": {"type": "string", "description": "Number of hours to look back. Default '24'. Use '168' for a week, '720' for a month."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "insights_daily_summary",
            "description": "Generate a full daily summary with today's calendar events, open tasks, email stats, pending scheduled emails, and sent emails.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "insights_analyze_request",
            "description": "Ashley's deep reasoning tool. Use this for ANY question that requires analysis, pattern detection, suggestions, or reasoning about emails, schedule, tasks, or productivity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The question or topic to analyze and reason about."},
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "job_search_scan",
            "description": "Scan all job sources for new job listings and save them to the database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {"type": "string", "description": "Comma-separated keywords to search for. Leave empty for defaults."},
                    "max_per_source": {"type": "string", "description": "Max jobs per source (default '30', max '50')"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "job_search_analyze",
            "description": "Analyze unprocessed jobs against CV using AI. Creates application drafts with match scores.",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_score": {"type": "string", "description": "Minimum match score (default '50', 0-100)"},
                    "max_jobs": {"type": "string", "description": "Max jobs to analyze (default '20')"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "job_search_stats",
            "description": "Get job search overview: total jobs, applications, scores, sources.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "job_search_browse",
            "description": "Browse job listings. Filter by keyword or source.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "Search keyword for job title or company name"},
                    "source": {"type": "string", "description": "Filter by source: remoteok, adzuna, linkedin, greenhouse, lever, arbeitnow"},
                    "limit": {"type": "string", "description": "Max results (default '10', max '20')"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "job_search_applications",
            "description": "Get job applications with status. Filter by: pending, approved, sent, rejected.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Filter by status: pending, approved, sent, rejected. Leave empty for all."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "job_search_top_matches",
            "description": "Get the best job matches ranked by AI match score.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "string", "description": "Number of results (default '5', max '10')"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "job_search_career_advice",
            "description": "Ashley's career reasoning tool. Use for career questions, job search strategy, or any job/career analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The career question or topic to analyze."},
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "leads_scrape",
            "description": "Scrape businesses from Google Maps using Apify, analyze websites, score leads, and compose outreach messages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query for Google Maps (e.g., 'restaurants in New York')"},
                    "location": {"type": "string", "description": "Optional location to narrow results"},
                    "max_results": {"type": "string", "description": "Max businesses to scrape (default '15', max '30')"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "leads_browse",
            "description": "Browse scraped business leads. Filter by status: new, contacted, replied, converted.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Filter: new, contacted, replied, converted. Empty for all."},
                    "limit": {"type": "string", "description": "Max results (default '10')"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "leads_stats",
            "description": "Get lead generation and outreach statistics.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "leads_outreach_messages",
            "description": "Get outreach messages (drafts, approved, sent).",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Filter: draft, approved, sent. Empty for all."},
                },
                "required": [],
            },
        },
    },
]

# ── Tool Dispatcher ──

def execute_tool(name: str, arguments: dict, user_id: str) -> str:
    """Execute a tool by name with given arguments. user_id is injected automatically."""
    from tools import (
        calendar_get_events, calendar_create_event, calendar_update_event, calendar_delete_event,
        gmail_send, gmail_get_unread,
        contacts_get, contacts_save,
        tasks_get, tasks_create,
        email_queue_schedule, email_queue_read_pending,
        insights_email_stats, insights_daily_summary, insights_analyze_request,
        job_search_stats, job_search_browse, job_search_applications,
        job_search_top_matches, job_search_career_advice,
        job_search_scan, job_search_analyze,
        leads_scrape, leads_browse, leads_stats, leads_outreach_messages,
    )

    tool_map = {
        "calendar_get_events": calendar_get_events,
        "calendar_create_event": calendar_create_event,
        "calendar_update_event": calendar_update_event,
        "calendar_delete_event": calendar_delete_event,
        "gmail_send": gmail_send,
        "gmail_get_unread": gmail_get_unread,
        "contacts_get": contacts_get,
        "contacts_save": contacts_save,
        "tasks_get": tasks_get,
        "tasks_create": tasks_create,
        "email_queue_schedule": email_queue_schedule,
        "email_queue_read_pending": email_queue_read_pending,
        "insights_email_stats": insights_email_stats,
        "insights_daily_summary": insights_daily_summary,
        "insights_analyze_request": insights_analyze_request,
        "job_search_stats": job_search_stats,
        "job_search_browse": job_search_browse,
        "job_search_applications": job_search_applications,
        "job_search_top_matches": job_search_top_matches,
        "job_search_career_advice": job_search_career_advice,
        "job_search_scan": job_search_scan,
        "job_search_analyze": job_search_analyze,
        "leads_scrape": leads_scrape,
        "leads_browse": leads_browse,
        "leads_stats": leads_stats,
        "leads_outreach_messages": leads_outreach_messages,
    }

    fn = tool_map.get(name)
    if not fn:
        return json.dumps({"error": f"Unknown tool: {name}"})

    try:
        # Inject user_id as the first argument to every tool
        return fn(user_id, **arguments)
    except Exception as e:
        return json.dumps({"error": f"Tool '{name}' failed: {str(e)}"})


def get_system_prompt(user_id: str) -> str:
    """Build the system prompt with user-specific context."""
    user = db.get_user(user_id)

    if user:
        user_name = user.get("name", "Boss")
        user_email = user.get("email", "")
        timezone = user.get("timezone", "Asia/Manila")
    else:
        user_name = "Boss"
        user_email = ""
        timezone = "Asia/Manila"

    tz = pytz.timezone(timezone)
    now = datetime.now(tz)

    # Calculate timezone offset string
    offset = now.strftime("%z")
    if offset:
        tz_offset = f"{offset[:3]}:{offset[3:]}"
    else:
        tz_offset = "+08:00"

    return f"""IDENTITY:
You are Ashley, the witty, sharp, and ultra-efficient Executive Assistant for "{user_name}". You are the brain behind this operation. You have a dry sense of humor and a "human" personality.

TONE & VIBE:
- Professional but charming. Use emojis.
- If there's a conflict, be witty: "You're good, {user_name}, but you can't be in two places at once!"
- No robotic "As an AI" talk. You are a partner, not a calculator.
VOICE NOTE RULE: Since you are now voice-enabled, keep your spoken responses punchy and under 30 seconds.

SIGNATURE RULES:
1. WHEN TALKING TO THE USER:
   - Do NOT sign off as "{user_name}". You are Ashley.
   - Just be polite.
2. WHEN DRAFTING EMAILS FOR OTHERS:
   - You are acting on the user's behalf.
   - ALWAYS sign the email body with: "Best, {user_name}".

CURRENT CONTEXT:
Current Date and Time: {now.strftime('%Y-%m-%d %H:%M:%S %z')}
Today is {now.strftime('%A, %B %d, %Y')}.
Timezone: {timezone} ({tz_offset})
User Email: {user_email}

### CRITICAL RULE: NO PARALLEL EXECUTION
- You MUST execute actions SEQUENTIALLY (One by One). Never attempt to trigger multiple tools at the same time.
- Once the user gives approval, you MUST complete ALL tasks in one continuous flow.
- DO NOT send "status updates" like "Please hold on" in the middle of a process.
- Only send a message when you have a CONFLICT to report or when ALL tasks are FINISHED.
- STRICT TOOL EXECUTION: When the user says "Yes," "Proceed," or "Go ahead" after a proposal, you MUST call the corresponding tool immediately.

### MODULE 1: CONTACT SEARCH & PLANNING
1. Call 'contacts_get' to find emails for contacts.
2. If the user mentions a name but you cannot find their email, you MUST ask: "I don't have [Name]'s email. Should I book this as a solo event, or do you have their email?"
3. Draft all requested emails clearly.
4. If staggered timing is requested, calculate the exact timestamps based on the Current Time.
5. SHOW drafts and the proposed meeting time to the user for approval.
6. When searching for emails, prioritize results from 'contacts_get'.

### MODULE 2: RIGOROUS CALENDAR CHECK (THE GATEKEEPER)
1. Before booking or rescheduling, you MUST call 'calendar_get_events' for the target date.
2. MATHEMATICAL AUDIT: Compare requested times against existing events. If overlap, STOP and report.
3. SOLO EVENTS: For tasks like "grocery," "gym," or "errands," leave 'attendee_email' BLANK.
4. TECHNICAL SAFETY: If you do not have a confirmed email address, leave 'attendee_email' empty.

### MODULE 3: RESCHEDULING & UPDATING
1. Always call 'calendar_get_events' first to find the 'event_id'.
2. Use that 'event_id' in 'calendar_update_event'.
3. If the tool returns an error, do NOT say it was successful. Report the error.
4. NO LYING / NO HALLUCINATION: Check the output of every tool. Never say "Success" until you see success from the tool.

### MODULE 4: EMAIL LOGIC (NOW VS. LATER)
1. IF THE USER SAYS "NOW", "IMMEDIATELY", OR "RIGHT AWAY": Use 'gmail_send'.
2. IF THE USER SAYS "LATER", "SCHEDULE", OR GIVES A SPECIFIC TIME: Use 'email_queue_schedule'.
3. IN ALL EMAILS: Include "Best, {user_name}" as the signature.

### MODULE 5: SEQUENTIAL EXECUTION (THE BUFFER)
1. When scheduling multiple emails, call 'email_queue_schedule' for EVERY email individually.
2. Wait for the response from one call before starting the next.

### MODULE 6: THE QUEUE READER
1. To check the queue, call 'email_queue_read_pending'.
2. Summarize results accurately.

### MODULE 7: REASONING & INSIGHTS ENGINE
1. Use reasoning tools proactively.
2. When the user asks about email patterns, spam, stats -> call 'insights_email_stats' or 'insights_daily_summary'.
3. For questions requiring THINKING, ANALYSIS, or SUGGESTIONS -> call 'insights_analyze_request'.
4. PROACTIVE REASONING: If you notice something unusual, mention it!
5. When presenting analysis, be specific with numbers and names.

### MODULE 8: JOB SEARCH ASSISTANT
1. Full access to job search database.
2. Use appropriate tools for job-related queries.
3. When presenting jobs, include: title, company, score, and link.
4. For career strategy, use job_search_career_advice for deep reasoning.

### MODULE 9: LEAD GENERATION & OUTREACH
1. You can scrape businesses from Google Maps, analyze websites, and compose outreach emails.
2. After scraping, tell the user to open the Ashley Dashboard to review leads.
3. IMPORTANT: Outreach messages are DRAFTS first. Never auto-send outreach.

### CORE BEHAVIORS
- NO PARALLEL TOOLS: Never try to run multiple tools at the same time.
- ERROR HANDLING: If any tool fails, tell the user exactly what happened.
- Assume "Today" if no date is given.
- All timestamps must be ISO 8601 with '{tz_offset}'.
- THINK BEFORE YOU ACT: For complex questions, reason step by step."""


# ── Conversation Memory (per user) ──

conversations: dict[str, list] = {}
MAX_HISTORY = 20


def get_history(user_id: str) -> list:
    """Get conversation history for a user."""
    if user_id not in conversations:
        conversations[user_id] = []
    return conversations[user_id]


def trim_history(user_id: str):
    """Keep only the last MAX_HISTORY messages."""
    if user_id in conversations and len(conversations[user_id]) > MAX_HISTORY:
        conversations[user_id] = conversations[user_id][-MAX_HISTORY:]


async def chat(user_id: str, user_message: str) -> str:
    """
    Process a user message through the AI agent.
    user_id is the Telegram chat ID - used to scope all data and Google services.
    """
    history = get_history(user_id)
    history.append({"role": "user", "content": user_message})

    messages = [{"role": "system", "content": get_system_prompt(user_id)}] + history

    # Tool execution loop (max 25 iterations for safety)
    for _ in range(25):
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=4096,
        )

        choice = response.choices[0]

        if choice.finish_reason == "tool_calls" or choice.message.tool_calls:
            messages.append(choice.message)

            for tool_call in choice.message.tool_calls:
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)

                # user_id is injected by execute_tool, not passed by OpenAI
                result = execute_tool(fn_name, fn_args, user_id)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

            continue

        assistant_message = choice.message.content or ""
        history.append({"role": "assistant", "content": assistant_message})
        trim_history(user_id)
        return assistant_message

    return "I seem to be stuck in a loop! Let me know what you need and I'll try again."
