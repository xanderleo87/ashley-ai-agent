"""
Google OAuth2 authentication for Gmail and Calendar APIs.
Multi-user: each user has their own Google token stored in Supabase.
For admin/setup: tokens can also be loaded from local files.
"""

import os
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import config

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]


def get_credentials_for_user(user_id: str) -> Credentials:
    """Load or refresh Google OAuth2 credentials for a specific user from Supabase."""
    import database as db

    token_data = db.get_user_google_token(user_id)

    if not token_data:
        raise FileNotFoundError(
            f"No Google token found for user {user_id}. "
            f"Run: python setup_google.py {user_id}"
        )

    creds = Credentials.from_authorized_user_info(token_data, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Save refreshed token back to Supabase
            db.save_user_google_token(user_id, json.loads(creds.to_json()))
        else:
            raise FileNotFoundError(
                f"Google token for user {user_id} is expired and cannot be refreshed. "
                f"Run: python setup_google.py {user_id}"
            )

    return creds


def setup_user_google_auth(user_id: str) -> Credentials:
    """Run the interactive OAuth flow for a user and save their token to Supabase."""
    import database as db

    if not os.path.exists(config.GOOGLE_CREDENTIALS_FILE):
        raise FileNotFoundError(
            "credentials.json not found! This is the OAuth app config.\n"
            "See README for instructions on getting Google OAuth2 credentials."
        )

    flow = InstalledAppFlow.from_client_secrets_file(config.GOOGLE_CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    # Save token to Supabase
    token_data = json.loads(creds.to_json())
    db.save_user_google_token(user_id, token_data)

    return creds


def get_calendar_service(user_id: str):
    """Get authenticated Google Calendar API service for a user."""
    creds = get_credentials_for_user(user_id)
    return build("calendar", "v3", credentials=creds)


def get_gmail_service(user_id: str):
    """Get authenticated Gmail API service for a user."""
    creds = get_credentials_for_user(user_id)
    return build("gmail", "v1", credentials=creds)


# ── Legacy support: load from local file (for initial admin setup) ──

def get_credentials_from_file(token_file: str = "token.json") -> Credentials:
    """Load credentials from a local token file (used during setup)."""
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(config.GOOGLE_CREDENTIALS_FILE):
                raise FileNotFoundError("credentials.json not found!")
            flow = InstalledAppFlow.from_client_secrets_file(config.GOOGLE_CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_file, "w") as f:
            f.write(creds.to_json())

    return creds
