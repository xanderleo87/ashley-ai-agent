"""
Google Auth Setup - Connect a user's Google account to Ashley.

USAGE:
  python setup_google.py                  # Set up your own account (admin)
  python setup_google.py 5448864853       # Set up a specific user by Telegram chat ID

STEPS FOR THE CLIENT:
1. Go to https://console.cloud.google.com/
2. Use the existing project (or create one)
3. Enable "Google Calendar API" and "Gmail API"
4. Go to Credentials -> OAuth Client ID -> Desktop app
5. Download JSON and save as "credentials.json" in this folder
6. Run this script with their Telegram chat ID
7. A browser window will open - the CLIENT signs in with THEIR Gmail
8. Done! Token is saved to Supabase automatically.

WHAT THE CLIENT NEEDS TO PROVIDE:
  - Their Telegram Chat ID (they can get it by messaging @userinfobot on Telegram)
  - Their Gmail address
  - Their timezone (e.g., Asia/Manila, America/New_York)
  - They need to click the Google auth link and authorize Ashley
"""

import sys
import json
import os
from google_auth_oauthlib.flow import InstalledAppFlow
import config

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]


def setup_for_user(telegram_chat_id: str):
    """Run Google OAuth for a specific user and save token to Supabase."""
    import database as db

    # Check user exists
    user = db.get_user(telegram_chat_id)
    if not user:
        print(f"ERROR: No user found with Telegram chat ID: {telegram_chat_id}")
        print(f"The user must /register on Telegram first.")
        print()
        print("Or create them manually:")
        print(f"  python -c \"import database as db; db.create_user('{telegram_chat_id}', 'ClientName', 'client@email.com')\"")
        return False

    print(f"Setting up Google for: {user['name']} ({user.get('email', 'no email')})")
    print()

    if not os.path.exists(config.GOOGLE_CREDENTIALS_FILE):
        print("ERROR: credentials.json not found!")
        print("Download it from Google Cloud Console -> Credentials -> OAuth Client ID")
        return False

    print("A browser window will open.")
    print(f"The CLIENT ({user['name']}) must sign in with THEIR Google account.")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(config.GOOGLE_CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    # Save token to Supabase
    token_data = json.loads(creds.to_json())
    db.save_user_google_token(telegram_chat_id, token_data)

    print()
    print(f"SUCCESS! Google account connected for {user['name']}.")
    print(f"Ashley can now access their Gmail and Calendar.")
    return True


def setup_admin_from_file():
    """Legacy: set up admin account from existing token.json file."""
    import database as db
    from dotenv import load_dotenv
    load_dotenv()

    chat_id = os.getenv("TELEGRAM_CHAT_ID", "5448864853")

    # Check if token.json exists locally
    token_file = "token.json"
    if os.path.exists(token_file):
        print(f"Found existing {token_file}. Migrating to Supabase...")
        with open(token_file, "r") as f:
            token_data = json.load(f)

        user = db.get_user(chat_id)
        if not user:
            # Create admin user
            email = os.getenv("GOOGLE_EMAIL", "anasopie2@gmail.com")
            db.create_user(chat_id, "Anasopie", email, "Asia/Manila")
            db.update_user(chat_id, {"is_admin": True})
            print(f"Created admin user: Anasopie ({email})")

        db.save_user_google_token(chat_id, token_data)
        print(f"Token migrated to Supabase for chat ID: {chat_id}")
        print("You can now delete token.json if you want.")
        return True

    # No token.json, run fresh auth
    print("No token.json found. Running fresh Google auth for admin...")
    return setup_for_user(chat_id)


if __name__ == "__main__":
    print("=" * 50)
    print("  Ashley AI Agent - Google Auth Setup")
    print("=" * 50)
    print()

    if len(sys.argv) > 1:
        # Set up specific user
        target_chat_id = sys.argv[1]
        print(f"Setting up Google for user: {target_chat_id}")
        print()
        setup_for_user(target_chat_id)
    else:
        # Set up admin / migrate existing token
        print("No user specified. Setting up admin account...")
        print()
        setup_admin_from_file()

    print()
    print("Done! You can now run Ashley with: python main.py")
