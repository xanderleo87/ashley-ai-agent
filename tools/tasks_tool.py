"""Tasks tools - backed by Supabase. Multi-user."""

import json
import database as db


def tasks_get(user_id: str) -> str:
    """Get all tasks."""
    try:
        tasks = db.get_tasks(user_id)
        if not tasks:
            return json.dumps({"message": "No tasks found. Your to-do list is empty!", "tasks": []})

        return json.dumps({
            "message": f"You have {len(tasks)} task(s).",
            "tasks": [{"id": t["id"], "name": t["name"]} for t in tasks],
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def tasks_create(user_id: str, name: str) -> str:
    """Create a new task."""
    try:
        result = db.create_task(user_id, name)
        return json.dumps({"message": f"Task '{name}' added to your to-do list!"})
    except Exception as e:
        return json.dumps({"error": str(e)})
