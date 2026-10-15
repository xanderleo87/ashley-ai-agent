"""Google Calendar tools - CRUD operations. Multi-user: uses per-user Google credentials."""

import json
from google_auth import get_calendar_service
import database as db


def _get_user_email(user_id: str) -> str:
    """Get user's email for calendar ID."""
    user = db.get_user(user_id)
    return user.get("email", "primary") if user else "primary"


def _get_user_timezone(user_id: str) -> str:
    """Get user's timezone."""
    user = db.get_user(user_id)
    return user.get("timezone", "Asia/Manila") if user else "Asia/Manila"


def calendar_get_events(user_id: str, time_min: str, time_max: str, query: str = "") -> str:
    """Get events from Google Calendar within a time range."""
    try:
        service = get_calendar_service(user_id)
        calendar_id = _get_user_email(user_id)
        params = {
            "calendarId": calendar_id,
            "timeMin": time_min,
            "timeMax": time_max,
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if query:
            params["q"] = query

        result = service.events().list(**params).execute()
        events = result.get("items", [])

        if not events:
            return json.dumps({"message": "No events found in this time range.", "events": []})

        formatted = []
        for e in events:
            formatted.append({
                "id": e.get("id"),
                "summary": e.get("summary", "No title"),
                "start": e.get("start", {}).get("dateTime", e.get("start", {}).get("date")),
                "end": e.get("end", {}).get("dateTime", e.get("end", {}).get("date")),
                "attendees": [a.get("email") for a in e.get("attendees", [])],
            })

        return json.dumps({"message": f"Found {len(formatted)} event(s).", "events": formatted})
    except Exception as e:
        return json.dumps({"error": str(e)})


def calendar_create_event(user_id: str, title: str, start_time: str, end_time: str, attendee_email: str = "") -> str:
    """Create a new Google Calendar event."""
    try:
        service = get_calendar_service(user_id)
        calendar_id = _get_user_email(user_id)
        timezone = _get_user_timezone(user_id)

        event = {
            "summary": title,
            "start": {"dateTime": start_time, "timeZone": timezone},
            "end": {"dateTime": end_time, "timeZone": timezone},
        }
        if attendee_email and attendee_email.strip():
            event["attendees"] = [{"email": attendee_email}]

        result = service.events().insert(calendarId=calendar_id, body=event).execute()
        return json.dumps({
            "message": "Event created successfully!",
            "event_id": result.get("id"),
            "link": result.get("htmlLink"),
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def calendar_update_event(user_id: str, event_id: str, title: str = "", start_time: str = "", end_time: str = "") -> str:
    """Update an existing Google Calendar event."""
    try:
        service = get_calendar_service(user_id)
        calendar_id = _get_user_email(user_id)
        timezone = _get_user_timezone(user_id)

        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()

        if title:
            event["summary"] = title
        if start_time:
            event["start"] = {"dateTime": start_time, "timeZone": timezone}
        if end_time:
            event["end"] = {"dateTime": end_time, "timeZone": timezone}

        result = service.events().update(
            calendarId=calendar_id, eventId=event_id, body=event
        ).execute()

        return json.dumps({
            "message": "Event updated successfully!",
            "event_id": result.get("id"),
            "summary": result.get("summary"),
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def calendar_delete_event(user_id: str, event_id: str) -> str:
    """Delete a Google Calendar event."""
    try:
        service = get_calendar_service(user_id)
        calendar_id = _get_user_email(user_id)
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return json.dumps({"message": f"Event {event_id} deleted successfully!"})
    except Exception as e:
        return json.dumps({"error": str(e)})
