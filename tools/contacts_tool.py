"""Contacts tools - backed by Supabase. Multi-user."""

import json
import database as db


def contacts_get(user_id: str, search_name: str = "") -> str:
    """Get contacts, optionally filtered by name."""
    try:
        if search_name:
            contacts = db.search_contact(user_id, search_name)
        else:
            contacts = db.get_contacts(user_id)

        if not contacts:
            return json.dumps({"message": "No contacts found.", "contacts": []})

        return json.dumps({
            "message": f"Found {len(contacts)} contact(s).",
            "contacts": [{"name": c["name"], "email": c["email"]} for c in contacts],
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def contacts_save(user_id: str, name: str, email: str) -> str:
    """Save a new contact."""
    try:
        existing = db.get_contact_by_email(user_id, email)
        if existing:
            return json.dumps({"message": f"Contact with email {email} already exists.", "contact": existing[0]})

        result = db.add_contact(user_id, name, email)
        return json.dumps({"message": f"Contact '{name}' ({email}) saved successfully!"})
    except Exception as e:
        return json.dumps({"error": str(e)})
