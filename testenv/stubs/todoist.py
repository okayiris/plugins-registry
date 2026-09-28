"""Sample answers shaped like the Todoist API v1 (https://developer.todoist.com/api/v1/), for recording a
cassette without a token. Record with IRIS_KEY_TODOIST set to replace them with real answers."""
import json
from datetime import datetime, timedelta


def iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%S%z")


def answer(item, method, url, body):
    now = datetime.now().astimezone().replace(second=0, microsecond=0)
    today = now.date().isoformat()
    tasks = [
        {"id": "1", "content": "Call the plumber", "priority": 4, "project_id": "p1", "description": "",
         "due": {"date": today, "datetime": iso(now + timedelta(hours=2)), "is_recurring": False, "string": "today 12:00"}},
        {"id": "2", "content": "Pay rent", "priority": 1, "project_id": "p2", "description": "",
         "due": {"date": (now.date() - timedelta(days=2)).isoformat(), "is_recurring": True, "string": "every month"}},
        {"id": "3", "content": "Buy milk", "priority": 1, "project_id": "p2", "description": "", "due": {"date": today}},
        {"id": "4", "content": "Buy bread", "priority": 1, "project_id": "p2", "description": "", "due": None},
    ]
    if "/tasks/filter" in url:
        return 200, {"results": tasks[:3], "next_cursor": None}
    if "/projects" in url:
        return 200, {"results": [{"id": "p1", "name": "Work"}, {"id": "p2", "name": "Inbox"}], "next_cursor": None}
    if "/tasks?" in url and "project_id=p1" in url:
        return 200, {"results": [tasks[0]], "next_cursor": None}
    if "/tasks?" in url:
        return 200, {"results": tasks, "next_cursor": None}
    if url.endswith("/tasks") and method == "POST":
        b = json.loads(body)
        due = None
        if b.get("due_string"):
            at = (now + timedelta(days=1)).replace(hour=9, minute=0)
            due = {"date": at.date().isoformat(), "datetime": iso(at), "string": b["due_string"], "is_recurring": False}
        return 200, {"id": "9", "content": b["content"], "due": due, "priority": 1, "project_id": "p2"}
    if url.endswith("/close"):
        return 204, ""
    return 404, {"error": "not in the stub"}
