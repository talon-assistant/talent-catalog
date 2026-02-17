"""CodeSnippetTalent — save, search, and retrieve code snippets.

Store snippets with language tags and descriptions for quick retrieval.
Persists to data/snippets.json.

Examples:
    "save snippet python: def hello(): print('hi')"
    "save snippet javascript tagged api: fetch('/api/data')"
    "find snippet hello"
    "list snippets"
    "list python snippets"
    "delete snippet hello"
    "show snippet 3"
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


class CodeSnippetTalent(BaseTalent):
    name = "code_snippet"
    description = "Save, search, and paste code snippets by language and topic"
    keywords = [
        "snippet", "code snippet", "save snippet", "save code",
        "find snippet", "search snippet", "list snippet",
        "show snippet", "delete snippet", "paste snippet",
        "my snippets",
    ]
    priority = 43

    _EXCLUSIONS = [
        "remind", "timer", "email", "note", "weather", "hue",
        "light", "search", "news", "todo", "task", "pomodoro",
        "docker", "github", "regex", "json",
    ]

    _SNIPPETS_FILE = os.path.join(_data_dir(), "snippets.json")

    _LANGUAGES = [
        "python", "javascript", "typescript", "java", "cpp", "c",
        "rust", "go", "ruby", "php", "swift", "kotlin", "bash",
        "shell", "sql", "html", "css", "yaml", "json", "toml",
    ]

    def __init__(self):
        super().__init__()
        self._snippets = []
        self._load()

    def get_config_schema(self) -> dict:
        return {
            "fields": [
                {"key": "max_display", "label": "Max Snippets to Display",
                 "type": "int", "default": 15, "min": 5, "max": 50},
            ]
        }

    def can_handle(self, command: str) -> bool:
        cmd = command.lower()
        if any(ex in cmd for ex in self._EXCLUSIONS):
            return False
        return any(kw in cmd for kw in self.keywords)

    def execute(self, command: str, context: dict) -> dict:
        cmd = command.lower().strip()

        # Save snippet
        if any(p in cmd for p in ["save snippet", "save code", "store snippet",
                                   "add snippet", "new snippet"]):
            return self._save_snippet(command)

        # Delete
        if any(p in cmd for p in ["delete snippet", "remove snippet"]):
            query = self._strip_prefixes(cmd, ["delete snippet", "remove snippet"])
            return self._delete_snippet(query)

        # Show specific snippet by number
        num_match = re.search(r'(?:show|get|paste)\s+snippet\s+(\d+)', cmd)
        if num_match:
            index = int(num_match.group(1)) - 1
            return self._show_snippet(index)

        # Search / find
        if any(p in cmd for p in ["find snippet", "search snippet"]):
            query = self._strip_prefixes(cmd, ["find snippet", "search snippet",
                                                "find snippets", "search snippets"])
            return self._search_snippets(query)

        # List (with optional language filter)
        if any(p in cmd for p in ["list snippet", "my snippet", "show snippet",
                                   "list code"]):
            lang_filter = None
            for lang in self._LANGUAGES:
                if lang in cmd:
                    lang_filter = lang
                    break
            return self._list_snippets(lang_filter)

        # Default: list
        return self._list_snippets()

    # ── Save ─────────────────────────────────────────────────────

    def _save_snippet(self, command):
        # Strip prefix
        text = command
        for prefix in ["save snippet", "save code", "store snippet",
                        "add snippet", "new snippet"]:
            if text.lower().startswith(prefix):
                text = text[len(prefix):].strip()
                break

        if not text:
            return self._fail("Please provide the code to save.")

        # Detect language
        language = ""
        for lang in self._LANGUAGES:
            if text.lower().startswith(lang + ":") or text.lower().startswith(lang + " "):
                language = lang
                text = text[len(lang):].lstrip(": ").strip()
                break

        # Extract tag
        tag = ""
        tag_match = re.search(r'\btagged?\s+(\w+)', text, re.IGNORECASE)
        if tag_match:
            tag = tag_match.group(1)
            text = text[:tag_match.start()].strip() + " " + text[tag_match.end():].strip()
            text = text.strip()

        # Extract description (first line if multi-line, or first sentence)
        lines = text.split("\n")
        if len(lines) > 1:
            description = lines[0].strip().rstrip(":")
            code = "\n".join(lines[1:]).strip()
        else:
            # If single line, code and description are the same
            description = text[:50]
            code = text

        snippet = {
            "id": int(datetime.now().timestamp() * 1000),
            "code": code,
            "description": description,
            "language": language,
            "tag": tag,
            "created": datetime.now().isoformat(),
        }

        self._snippets.append(snippet)
        self._save()

        parts = [f"Saved snippet: \"{description}\""]
        if language:
            parts.append(f"Language: {language}")
        if tag:
            parts.append(f"Tag: {tag}")

        return self._ok(" | ".join(parts))

    # ── List ─────────────────────────────────────────────────────

    def _list_snippets(self, language=None):
        snippets = self._snippets
        if language:
            snippets = [s for s in snippets if s.get("language", "").lower() == language.lower()]

        if not snippets:
            label = f" ({language})" if language else ""
            return self._ok(f"No code snippets saved{label}.")

        max_display = self._config.get("max_display", 15)
        lines = [f"Code Snippets ({len(snippets)}):\n"]
        for i, s in enumerate(snippets[:max_display]):
            lang = f" [{s['language']}]" if s.get("language") else ""
            tag = f" #{s['tag']}" if s.get("tag") else ""
            desc = s.get("description", s.get("code", "")[:40])
            lines.append(f"  {i + 1}. {desc}{lang}{tag}")

        if len(snippets) > max_display:
            lines.append(f"\n  ...and {len(snippets) - max_display} more")
        lines.append("\nSay 'show snippet N' to see full code.")

        return self._ok("\n".join(lines))

    # ── Show ─────────────────────────────────────────────────────

    def _show_snippet(self, index):
        if index < 0 or index >= len(self._snippets):
            return self._fail(f"No snippet at position {index + 1}.")

        s = self._snippets[index]
        lang = s.get("language", "")
        lines = []
        if s.get("description"):
            lines.append(f"Description: {s['description']}")
        if lang:
            lines.append(f"Language: {lang}")
        if s.get("tag"):
            lines.append(f"Tag: {s['tag']}")
        lines.append(f"\n```{lang}\n{s['code']}\n```")

        return self._ok("\n".join(lines))

    # ── Search ───────────────────────────────────────────────────

    def _search_snippets(self, query):
        if not query:
            return self._fail("What should I search for?")

        query_lower = query.lower()
        matches = []
        for i, s in enumerate(self._snippets):
            searchable = " ".join([
                s.get("code", ""), s.get("description", ""),
                s.get("language", ""), s.get("tag", ""),
            ]).lower()
            if query_lower in searchable:
                matches.append((i, s))

        if not matches:
            return self._ok(f"No snippets matching \"{query}\".")

        lines = [f"Found {len(matches)} match(es) for \"{query}\":\n"]
        for idx, s in matches[:10]:
            lang = f" [{s['language']}]" if s.get("language") else ""
            desc = s.get("description", s.get("code", "")[:40])
            lines.append(f"  {idx + 1}. {desc}{lang}")

        return self._ok("\n".join(lines))

    # ── Delete ───────────────────────────────────────────────────

    def _delete_snippet(self, query):
        if not query:
            return self._fail("Which snippet should I delete?")

        # Try number first
        try:
            index = int(query) - 1
            if 0 <= index < len(self._snippets):
                removed = self._snippets.pop(index)
                self._save()
                return self._ok(f"Deleted snippet: \"{removed.get('description', 'untitled')}\"")
        except ValueError:
            pass

        # Search by text
        query_lower = query.lower()
        for i, s in enumerate(self._snippets):
            if query_lower in s.get("description", "").lower() or \
               query_lower in s.get("code", "").lower():
                removed = self._snippets.pop(i)
                self._save()
                return self._ok(f"Deleted snippet: \"{removed.get('description', 'untitled')}\"")

        return self._fail(f"No snippet matching \"{query}\".")

    # ── Helpers ──────────────────────────────────────────────────

    def _strip_prefixes(self, cmd, prefixes):
        for prefix in sorted(prefixes, key=len, reverse=True):
            if cmd.startswith(prefix):
                return cmd[len(prefix):].strip()
        return cmd

    def _ok(self, msg):
        return {"success": True, "response": msg,
                "actions_taken": [{"action": "code_snippet"}], "spoken": False}

    def _fail(self, msg):
        return {"success": False, "response": msg,
                "actions_taken": [], "spoken": False}

    def _load(self):
        try:
            if os.path.exists(self._SNIPPETS_FILE):
                with open(self._SNIPPETS_FILE, 'r') as f:
                    self._snippets = json.load(f)
        except Exception as e:
            print(f"   [CodeSnippet] Load error: {e}")
            self._snippets = []

    def _save(self):
        try:
            with open(self._SNIPPETS_FILE, 'w') as f:
                json.dump(self._snippets, f, indent=2)
        except Exception as e:
            print(f"   [CodeSnippet] Save error: {e}")
