"""TodoTalent — local todo list with priorities, due dates, and categories.

Add, complete, search, and list tasks using natural language.
Tasks persist to data/todo.json.

Examples:
    "add task buy groceries"
    "add high priority task finish report by friday"
    "show my todo list"
    "complete buy groceries"
    "remove buy groceries"
    "show tasks tagged work"
"""

import os
import json
import re
from datetime import datetime
from talents.base import BaseTalent


def _data_dir():
    d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    os.makedirs(d, exist_ok=True)
    return d


class TodoTalent(BaseTalent):
    name = "todo"
    description = "Local todo list with priorities, due dates, and categories"
    keywords = [
        "todo", "task", "add task", "to-do", "to do list",
        "check off", "complete task", "remove task", "show tasks",
        "my tasks", "my list", "todo list",
    ]
    priority = 46

    _TODO_FILE = os.path.join(_data_dir(), "todo.json")

    _EXCLUSIONS = [
        "remind", "timer", "alarm", "email", "send", "note",
        "weather", "forecast", "hue", "light", "search",
    ]

    def __init__(self):
        super().__init__()
        self._tasks = []
        self._load()

    def get_config_schema(self) -> dict:
        return {
            "fields": [
                {"key": "default_priority", "label": "Default Priority",
                 "type": "choice", "default": "medium",
                 "choices": ["low", "medium", "high"]},
                {"key": "show_completed", "label": "Show Completed Tasks in List",
                 "type": "bool", "default": False},
            ]
        }

    def can_handle(self, command: str) -> bool:
        cmd = command.lower()
        if any(ex in cmd for ex in self._EXCLUSIONS):
            return False
        return any(kw in cmd for kw in self.keywords)

    def execute(self, command: str, context: dict) -> dict:
        cmd = command.lower().strip()

        # Natural phrasing: "add X to my todo list" / "put X on my list"
        # Must be checked BEFORE the list-tasks branch (which matches "todo list")
        add_match = re.match(
            r'(?:add|put)\s+(.+?)\s+(?:to|on)\s+(?:my\s+)?(?:todo|to-do|to do|task)?\s*list',
            cmd
        )
        if add_match:
            return self._add_task_direct(add_match.group(1).strip())

        # List tasks
        if any(p in cmd for p in ["show", "list", "my task", "my todo", "my to-do",
                                   "what are my", "todo list", "to do list"]):
            tag = None
            tag_match = re.search(r'(?:tagged?|category|label)\s+(\w+)', cmd)
            if tag_match:
                tag = tag_match.group(1)
            return self._list_tasks(tag)

        # Complete / check off
        if any(p in cmd for p in ["complete", "check off", "finish", "done with",
                                   "mark done", "mark complete"]):
            query = self._extract_task_text(cmd, ["complete", "check off", "finish",
                                                   "done with", "mark done", "mark complete"])
            return self._complete_task(query)

        # Remove / delete
        if any(p in cmd for p in ["remove task", "delete task"]):
            query = self._extract_task_text(cmd, ["remove task", "delete task",
                                                   "remove", "delete"])
            return self._remove_task(query)

        # Add task (prefix-based)
        if any(p in cmd for p in ["add task", "add a task", "new task", "create task",
                                   "add to my", "add to todo", "add to list"]):
            return self._add_task(cmd, context)

        # Fallback: if they just say "todo buy milk", treat as add
        if cmd.startswith("todo ") or cmd.startswith("task "):
            return self._add_task(cmd, context)

        return self._list_tasks()

    # ── Add ───────────────────────────────────────────────────────

    def _add_task(self, cmd, context):
        # Strip command prefixes
        text = cmd
        for prefix in ["add task", "add a task", "new task", "create task",
                        "add to my todo list", "add to my list", "add to todo",
                        "add to list", "todo", "task"]:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break

        if not text:
            return self._fail("What task would you like to add?")

        # Extract priority
        priority = self._config.get("default_priority", "medium")
        for p in ["high", "medium", "low"]:
            if f"{p} priority" in text:
                priority = p
                text = text.replace(f"{p} priority", "").strip()
                break

        # Extract tag
        tag = None
        tag_match = re.search(r'(?:tag(?:ged)?|category|label)\s+(\w+)', text)
        if tag_match:
            tag = tag_match.group(1)
            text = text[:tag_match.start()].strip()

        # Extract due date hint (simple: "by friday", "by tomorrow")
        due = None
        due_match = re.search(r'\bby\s+(\w+)', text)
        if due_match:
            due = due_match.group(1)
            text = text[:due_match.start()].strip()

        # Clean up trailing/leading noise
        text = re.sub(r'^(to|that)\s+', '', text).strip()
        if not text:
            return self._fail("I couldn't figure out the task description.")

        task = {
            "id": int(datetime.now().timestamp() * 1000),
            "text": text,
            "priority": priority,
            "tag": tag,
            "due": due,
            "completed": False,
            "created": datetime.now().isoformat(),
        }
        self._tasks.append(task)
        self._save()

        parts = [f"Added task: \"{text}\""]
        if priority != "medium":
            parts.append(f"Priority: {priority}")
        if tag:
            parts.append(f"Tag: {tag}")
        if due:
            parts.append(f"Due: {due}")

        return {
            "success": True,
            "response": " | ".join(parts),
            "actions_taken": [{"action": "todo_add", "text": text}],
            "spoken": False,
        }

    def _add_task_direct(self, text):
        """Add a task where the description text has already been extracted."""
        if not text:
            return self._fail("What task would you like to add?")

        priority = self._config.get("default_priority", "medium")
        for p in ["high", "medium", "low"]:
            if f"{p} priority" in text:
                priority = p
                text = text.replace(f"{p} priority", "").strip()
                break

        tag = None
        tag_match = re.search(r'(?:tag(?:ged)?|category|label)\s+(\w+)', text)
        if tag_match:
            tag = tag_match.group(1)
            text = text[:tag_match.start()].strip()

        due = None
        due_match = re.search(r'\bby\s+(\w+)', text)
        if due_match:
            due = due_match.group(1)
            text = text[:due_match.start()].strip()

        if not text:
            return self._fail("I couldn't figure out the task description.")

        task = {
            "id": int(datetime.now().timestamp() * 1000),
            "text": text,
            "priority": priority,
            "tag": tag,
            "due": due,
            "completed": False,
            "created": datetime.now().isoformat(),
        }
        self._tasks.append(task)
        self._save()

        parts = [f"Added task: \"{text}\""]
        if priority != "medium":
            parts.append(f"Priority: {priority}")
        if tag:
            parts.append(f"Tag: {tag}")
        if due:
            parts.append(f"Due: {due}")

        return {
            "success": True,
            "response": " | ".join(parts),
            "actions_taken": [{"action": "todo_add", "text": text}],
            "spoken": False,
        }

    # ── List ──────────────────────────────────────────────────────

    def _list_tasks(self, tag=None):
        show_completed = self._config.get("show_completed", False)
        tasks = self._tasks if show_completed else [t for t in self._tasks if not t["completed"]]

        if tag:
            tasks = [t for t in tasks if t.get("tag", "").lower() == tag.lower()]

        if not tasks:
            msg = "Your todo list is empty!" if not tag else f"No tasks tagged '{tag}'."
            return {"success": True, "response": msg,
                    "actions_taken": [{"action": "todo_list"}], "spoken": False}

        # Sort: high > medium > low, then by created
        priority_order = {"high": 0, "medium": 1, "low": 2}
        tasks.sort(key=lambda t: (priority_order.get(t.get("priority", "medium"), 1),
                                   t.get("created", "")))

        lines = ["Your tasks:\n"]
        for t in tasks:
            check = "\u2705" if t.get("completed") else "\u2b1c"
            pri = ""
            if t.get("priority") == "high":
                pri = " \u2757"
            elif t.get("priority") == "low":
                pri = " \u25bd"
            tag_str = f" [{t['tag']}]" if t.get("tag") else ""
            due_str = f" (by {t['due']})" if t.get("due") else ""
            lines.append(f"{check} {t['text']}{pri}{tag_str}{due_str}")

        return {"success": True, "response": "\n".join(lines),
                "actions_taken": [{"action": "todo_list"}], "spoken": False}

    # ── Complete ──────────────────────────────────────────────────

    def _complete_task(self, query):
        if not query:
            return self._fail("Which task should I mark as complete?")

        task = self._find_task(query)
        if not task:
            return self._fail(f"Couldn't find a task matching \"{query}\".")

        task["completed"] = True
        task["completed_at"] = datetime.now().isoformat()
        self._save()

        return {
            "success": True,
            "response": f"Completed: \"{task['text']}\" \u2705",
            "actions_taken": [{"action": "todo_complete", "text": task["text"]}],
            "spoken": False,
        }

    # ── Remove ────────────────────────────────────────────────────

    def _remove_task(self, query):
        if not query:
            return self._fail("Which task should I remove?")

        task = self._find_task(query)
        if not task:
            return self._fail(f"Couldn't find a task matching \"{query}\".")

        self._tasks.remove(task)
        self._save()

        return {
            "success": True,
            "response": f"Removed: \"{task['text']}\"",
            "actions_taken": [{"action": "todo_remove", "text": task["text"]}],
            "spoken": False,
        }

    # ── Helpers ────────────────────────────────────────────────────

    def _find_task(self, query):
        query_lower = query.lower()
        # Exact substring match first
        for t in self._tasks:
            if query_lower in t["text"].lower():
                return t
        # Word overlap fallback
        query_words = set(query_lower.split())
        best, best_score = None, 0
        for t in self._tasks:
            words = set(t["text"].lower().split())
            overlap = len(query_words & words)
            if overlap > best_score:
                best, best_score = t, overlap
        return best if best_score > 0 else None

    def _extract_task_text(self, cmd, prefixes):
        for prefix in sorted(prefixes, key=len, reverse=True):
            if prefix in cmd:
                return cmd.split(prefix, 1)[1].strip()
        return ""

    def _fail(self, msg):
        return {"success": False, "response": msg,
                "actions_taken": [], "spoken": False}

    def _load(self):
        try:
            if os.path.exists(self._TODO_FILE):
                with open(self._TODO_FILE, 'r') as f:
                    self._tasks = json.load(f)
        except Exception as e:
            print(f"   [Todo] Load error: {e}")
            self._tasks = []

    def _save(self):
        try:
            with open(self._TODO_FILE, 'w') as f:
                json.dump(self._tasks, f, indent=2)
        except Exception as e:
            print(f"   [Todo] Save error: {e}")
