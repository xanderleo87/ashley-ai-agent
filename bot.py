"""
Telegram bot handlers for Ashley AI Agent.
Multi-user: identifies users by Telegram chat ID, supports registration.
"""

import asyncio
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ChatAction
import config
import ai_agent
import voice
import database as db

# Thread pool for running blocking AI calls without freezing the bot
_executor = ThreadPoolExecutor(max_workers=3)


def _run_chat_sync(user_id: str, text: str) -> str:
    """Run the AI chat synchronously (for use in thread pool)."""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(ai_agent.chat(user_id, text))
    finally:
        loop.close()


async def _keep_typing(chat, stop_event: asyncio.Event):
    """Send typing indicator every 4 seconds until stop_event is set."""
    while not stop_event.is_set():
        try:
            await chat.send_action(ChatAction.TYPING)
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=4)
            break
        except asyncio.TimeoutError:
            continue


def _get_or_prompt_user(chat_id: str) -> dict | None:
    """Get user from database. Returns None if not registered."""
    return db.get_user(chat_id)


def _is_admin(chat_id: str) -> bool:
    """Check if user is an admin."""
    user = db.get_user(chat_id)
    return bool(user and user.get("is_admin", False))


async def _notify_admins(context_or_app, message: str):
    """Send a notification to all admin users."""
    admin_ids = db.get_admin_chat_ids()
    bot = getattr(context_or_app, "bot", context_or_app)
    for admin_id in admin_ids:
        try:
            await bot.send_message(chat_id=admin_id, text=message)
        except Exception:
            pass


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    chat_id = str(update.message.chat_id)
    user = _get_or_prompt_user(chat_id)

    if user:
        name = user.get("name", "there")
        is_approved = user.get("is_approved", False)

        if not is_approved:
            await update.message.reply_text(
                f"Hey {name}! Your account is pending approval.\n\n"
                f"An admin will review your registration soon.\n"
                f"You'll be notified once approved!"
            )
            return

        has_google = bool(user.get("google_token"))
        google_status = "Connected" if has_google else "Not connected - use /connectgoogle"
        await update.message.reply_text(
            f"Welcome back, {name}! Ashley here, your AI Executive Assistant.\n\n"
            f"Google Account: {google_status}\n\n"
            f"I can help you with:\n"
            f"  Calendar management\n"
            f"  Email drafting & scheduling\n"
            f"  Contact lookup\n"
            f"  Task tracking\n"
            f"  Voice messages\n"
            f"  Job search\n"
            f"  Lead generation\n\n"
            f"Just tell me what you need!"
        )
    else:
        await update.message.reply_text(
            "Hey there! I'm Ashley, your AI Executive Assistant.\n\n"
            "It looks like you haven't registered yet.\n"
            "To get started, send:\n\n"
            "/register YourName your@email.com\n\n"
            "Example:\n"
            "/register Maria maria@gmail.com\n\n"
            "You can also set your timezone after:\n"
            "/timezone Asia/Manila"
        )


async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /register Name Email - creates a new user."""
    chat_id = str(update.message.chat_id)

    # Check if already registered
    existing = db.get_user(chat_id)
    if existing:
        await update.message.reply_text(
            f"You're already registered as {existing['name']}!\n"
            f"Email: {existing.get('email', 'not set')}\n"
            f"Timezone: {existing.get('timezone', 'Asia/Manila')}\n\n"
            f"To update your info:\n"
            f"/name NewName\n"
            f"/email new@email.com\n"
            f"/timezone Your/Timezone"
        )
        return

    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: /register YourName your@email.com\n\n"
            "Example: /register Maria maria@gmail.com"
        )
        return

    name = args[0]
    email = args[1]

    try:
        db.create_user(
            telegram_chat_id=chat_id,
            name=name,
            email=email,
            timezone="Asia/Manila",
        )
        await update.message.reply_text(
            f"Thanks, {name}! Your registration has been submitted.\n\n"
            f"Your account is pending approval from an admin.\n"
            f"You'll be notified once you're approved!\n\n"
            f"In the meantime, you can set your timezone:\n"
            f"/timezone Your/Timezone"
        )

        # Notify admins about the new registration
        await _notify_admins(
            context.bot,
            f"New user registration!\n\n"
            f"  Name: {name}\n"
            f"  Email: {email}\n"
            f"  Chat ID: {chat_id}\n\n"
            f"To approve: /approve {chat_id}\n"
            f"To reject: /reject {chat_id}\n"
            f"See all pending: /pending"
        )
    except Exception as e:
        await update.message.reply_text(f"Registration failed: {e}")


async def set_name_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /name NewName - update user's name."""
    chat_id = str(update.message.chat_id)
    user = _get_or_prompt_user(chat_id)
    if not user:
        await update.message.reply_text("Please /register first!")
        return

    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /name YourNewName")
        return

    new_name = " ".join(args)
    db.update_user(chat_id, {"name": new_name})
    await update.message.reply_text(f"Name updated to: {new_name}")


async def set_email_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /email new@email.com - update user's email."""
    chat_id = str(update.message.chat_id)
    user = _get_or_prompt_user(chat_id)
    if not user:
        await update.message.reply_text("Please /register first!")
        return

    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /email your@email.com")
        return

    new_email = args[0]
    db.update_user(chat_id, {"email": new_email})
    await update.message.reply_text(f"Email updated to: {new_email}")


async def set_timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /timezone Asia/Manila - update user's timezone."""
    chat_id = str(update.message.chat_id)
    user = _get_or_prompt_user(chat_id)
    if not user:
        await update.message.reply_text("Please /register first!")
        return

    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: /timezone Your/Timezone\n\n"
            "Examples:\n"
            "  /timezone Asia/Manila\n"
            "  /timezone America/New_York\n"
            "  /timezone Europe/London\n"
            "  /timezone Australia/Sydney"
        )
        return

    import pytz
    tz_name = args[0]
    try:
        pytz.timezone(tz_name)
    except pytz.exceptions.UnknownTimeZoneError:
        await update.message.reply_text(f"Unknown timezone: {tz_name}\nTry something like: Asia/Manila, America/New_York")
        return

    db.update_user(chat_id, {"timezone": tz_name})
    await update.message.reply_text(f"Timezone updated to: {tz_name}")


async def my_profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /profile - show user's profile info."""
    chat_id = str(update.message.chat_id)
    user = _get_or_prompt_user(chat_id)
    if not user:
        await update.message.reply_text("Please /register first!")
        return

    has_google = bool(user.get("google_token"))
    google_status = "Connected" if has_google else "Not connected"

    await update.message.reply_text(
        f"Your Profile:\n\n"
        f"  Name: {user.get('name', '?')}\n"
        f"  Email: {user.get('email', 'not set')}\n"
        f"  Timezone: {user.get('timezone', 'Asia/Manila')}\n"
        f"  Google: {google_status}\n"
        f"  Chat ID: {chat_id}\n\n"
        f"Update commands:\n"
        f"  /name NewName\n"
        f"  /email new@email.com\n"
        f"  /timezone Your/Timezone"
    )


async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /approve <chat_id> - admin approves a user."""
    chat_id = str(update.message.chat_id)
    if not _is_admin(chat_id):
        await update.message.reply_text("Only admins can approve users.")
        return

    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /approve <chat_id>\n\nSee pending users: /pending")
        return

    target_id = args[0]
    user = db.get_user(target_id)
    if not user:
        await update.message.reply_text(f"No user found with chat ID: {target_id}")
        return

    if user.get("is_approved"):
        await update.message.reply_text(f"{user['name']} is already approved.")
        return

    db.approve_user(target_id)
    await update.message.reply_text(
        f"Approved! {user['name']} ({user.get('email', 'no email')}) can now use Ashley."
    )

    # Notify the approved user
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                f"Great news, {user['name']}! Your account has been approved!\n\n"
                f"You can now use Ashley. To connect your Google account:\n"
                f"/connectgoogle\n\n"
                f"Or just start chatting with me!"
            ),
        )
    except Exception:
        pass


async def reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /reject <chat_id> - admin rejects a user."""
    chat_id = str(update.message.chat_id)
    if not _is_admin(chat_id):
        await update.message.reply_text("Only admins can reject users.")
        return

    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /reject <chat_id>\n\nSee pending users: /pending")
        return

    target_id = args[0]
    user = db.get_user(target_id)
    if not user:
        await update.message.reply_text(f"No user found with chat ID: {target_id}")
        return

    db.reject_user(target_id)
    await update.message.reply_text(f"Rejected. {user['name']} has been deactivated.")

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text="Sorry, your request to use Ashley was not approved at this time.",
        )
    except Exception:
        pass


async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /pending - admin sees users awaiting approval."""
    chat_id = str(update.message.chat_id)
    if not _is_admin(chat_id):
        await update.message.reply_text("Only admins can view pending users.")
        return

    pending = db.get_pending_users()
    if not pending:
        await update.message.reply_text("No pending users. All caught up!")
        return

    lines = ["Pending users:\n"]
    for u in pending:
        lines.append(
            f"  {u['name']} ({u.get('email', '?')})\n"
            f"  Chat ID: {u['telegram_chat_id']}\n"
            f"  /approve {u['telegram_chat_id']}  |  /reject {u['telegram_chat_id']}\n"
        )

    await update.message.reply_text("\n".join(lines))


async def connect_google_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /connectgoogle - send user the OAuth link to connect their Gmail."""
    chat_id = str(update.message.chat_id)
    user = _get_or_prompt_user(chat_id)

    if not user:
        await update.message.reply_text("Please /register first!")
        return

    if not user.get("is_approved"):
        await update.message.reply_text("Your account is pending approval. Please wait for an admin to approve you.")
        return

    if user.get("google_token"):
        await update.message.reply_text(
            "Your Google account is already connected!\n\n"
            "To reconnect with a different account, click the link below.\n"
        )

    oauth_url = f"{config.OAUTH_BASE_URL}/auth/start/{chat_id}"
    await update.message.reply_text(
        f"To connect your Google account, click the link below:\n\n"
        f"{oauth_url}\n\n"
        f"You'll be asked to sign in with your Google account and authorize Ashley "
        f"to access your Gmail and Calendar.\n\n"
        f"This is a one-time setup!"
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming text messages."""
    chat_id = str(update.message.chat_id)
    user_text = update.message.text

    if not user_text:
        return

    # Check if user is registered
    user = _get_or_prompt_user(chat_id)
    if not user:
        await update.message.reply_text(
            "Hey! You need to register first to use Ashley.\n\n"
            "Send: /register YourName your@email.com\n"
            "Example: /register Maria maria@gmail.com"
        )
        return

    # Check if user is approved
    if not user.get("is_approved"):
        await update.message.reply_text(
            "Your account is pending approval.\n"
            "An admin will review your registration soon!"
        )
        return

    # Keep typing while AI processes in background thread
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(update.message.chat, stop_typing))

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(_executor, _run_chat_sync, chat_id, user_text)
    except Exception as e:
        user_name = user.get("name", "Boss")
        response = f"Sorry {user_name}, I hit a snag: {e}"
    finally:
        stop_typing.set()
        await typing_task

    # Send text response
    try:
        await update.message.reply_text(response, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(response)

    # Generate and send voice response
    await send_voice_reply(update, response)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming voice messages."""
    chat_id = str(update.message.chat_id)

    # Check if user is registered
    user = _get_or_prompt_user(chat_id)
    if not user:
        await update.message.reply_text(
            "Hey! You need to register first.\n"
            "Send: /register YourName your@email.com"
        )
        return

    if not user.get("is_approved"):
        await update.message.reply_text("Your account is pending approval. Please wait for an admin to approve you.")
        return

    # Download voice file
    await update.message.chat.send_action(ChatAction.TYPING)
    voice_file = await update.message.voice.get_file()
    temp_path = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False).name
    await voice_file.download_to_drive(temp_path)

    # Transcribe
    transcribed_text = await voice.transcribe_voice(temp_path)
    voice.cleanup_file(temp_path)

    if not transcribed_text or transcribed_text.startswith("[Voice transcription failed"):
        await update.message.reply_text("Sorry, I couldn't understand that voice message. Could you try again?")
        return

    # Keep typing while AI processes in background thread
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(update.message.chat, stop_typing))

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(_executor, _run_chat_sync, chat_id, transcribed_text)
    except Exception as e:
        user_name = user.get("name", "Boss")
        response = f"Sorry {user_name}, I hit a snag: {e}"
    finally:
        stop_typing.set()
        await typing_task

    # Send text response
    try:
        await update.message.reply_text(response, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(response)

    # Generate and send voice response
    await send_voice_reply(update, response)


async def send_voice_reply(update: Update, text: str):
    """Generate TTS audio and send as voice note."""
    audio_path = await voice.generate_voice(text)
    if audio_path:
        try:
            await update.message.chat.send_action(ChatAction.RECORD_VOICE)
            with open(audio_path, "rb") as audio_file:
                await update.message.reply_voice(voice=audio_file)
        except Exception as e:
            print(f"Failed to send voice: {e}")
        finally:
            voice.cleanup_file(audio_path)


def create_bot() -> Application:
    """Create and configure the Telegram bot application."""
    app = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .concurrent_updates(True)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .get_updates_connect_timeout(30)
        .get_updates_read_timeout(30)
        .get_updates_write_timeout(30)
        .get_updates_pool_timeout(30)
        .build()
    )

    # Command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("register", register_command))
    app.add_handler(CommandHandler("name", set_name_command))
    app.add_handler(CommandHandler("email", set_email_command))
    app.add_handler(CommandHandler("timezone", set_timezone_command))
    app.add_handler(CommandHandler("profile", my_profile_command))
    app.add_handler(CommandHandler("connectgoogle", connect_google_command))

    # Admin commands
    app.add_handler(CommandHandler("approve", approve_command))
    app.add_handler(CommandHandler("reject", reject_command))
    app.add_handler(CommandHandler("pending", pending_command))

    # Message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    return app
