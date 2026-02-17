"""JSONFormatterTalent — format, validate, and query JSON data.

Prettify minified JSON, validate syntax, and extract values
using dot-notation paths.

Examples:
    "format json {\"name\":\"test\",\"value\":42}"
    "validate json {\"broken: true}"
    "prettify json {\"a\":1,\"b\":[2,3]}"
    "json get users.0.name from {\"users\":[{\"name\":\"Alice\"}]}"
"""

import json
import re
from talents.base import BaseTalent


class JSONFormatterTalent(BaseTalent):
    name = "json_formatter"
    description = "Format, validate, and query JSON data"
    keywords = [
        "json", "format json", "prettify json", "validate json",
        "parse json", "minify json", "json get", "json query",
    ]
    priority = 41

    _EXCLUSIONS = [
        "remind", "timer", "email", "note", "weather", "hue",
        "light", "search", "news", "todo", "task", "pomodoro",
        "docker", "github", "regex",
    ]

    def get_config_schema(self) -> dict:
        return {
            "fields": [
                {"key": "indent", "label": "Indentation Spaces",
                 "type": "int", "default": 2, "min": 1, "max": 8},
                {"key": "sort_keys", "label": "Sort Keys Alphabetically",
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

        # Validate
        if "validate" in cmd:
            json_str = self._extract_json(command)
            return self._validate(json_str)

        # Minify
        if "minify" in cmd or "compact" in cmd:
            json_str = self._extract_json(command)
            return self._minify(json_str)

        # Query / get path
        if any(p in cmd for p in ["json get", "json query", "json extract",
                                   "get from json", "extract from json"]):
            return self._query(command)

        # Format / prettify (default)
        json_str = self._extract_json(command)
        return self._format(json_str)

    # ── Format ───────────────────────────────────────────────────

    def _format(self, json_str):
        if not json_str:
            return self._fail("No JSON data provided. Paste or type the JSON after the command.")

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return self._fail(f"Invalid JSON: {e}")

        indent = self._config.get("indent", 2)
        sort_keys = self._config.get("sort_keys", False)
        formatted = json.dumps(data, indent=indent, sort_keys=sort_keys, ensure_ascii=False)

        return self._ok(f"Formatted JSON:\n\n{formatted}")

    # ── Validate ─────────────────────────────────────────────────

    def _validate(self, json_str):
        if not json_str:
            return self._fail("No JSON data provided.")

        try:
            data = json.loads(json_str)
            # Count structure
            def count_elements(obj):
                if isinstance(obj, dict):
                    total = len(obj)
                    for v in obj.values():
                        total += count_elements(v)
                    return total
                elif isinstance(obj, list):
                    total = len(obj)
                    for item in obj:
                        total += count_elements(item)
                    return total
                return 0

            count = count_elements(data)
            dtype = type(data).__name__

            return self._ok(
                f"\u2705 Valid JSON!\n"
                f"  Type: {dtype}\n"
                f"  Elements: {count}\n"
                f"  Size: {len(json_str)} characters")
        except json.JSONDecodeError as e:
            return self._ok(
                f"\u274c Invalid JSON!\n"
                f"  Error: {e.msg}\n"
                f"  Line {e.lineno}, Column {e.colno}")

    # ── Minify ───────────────────────────────────────────────────

    def _minify(self, json_str):
        if not json_str:
            return self._fail("No JSON data provided.")

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return self._fail(f"Invalid JSON: {e}")

        minified = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
        saved = len(json_str) - len(minified)

        return self._ok(
            f"Minified JSON ({saved} characters saved):\n\n{minified}")

    # ── Query ────────────────────────────────────────────────────

    def _query(self, command):
        # Parse: "json get PATH from JSON"
        # or: "json query PATH in JSON"
        match = re.search(
            r'(?:get|query|extract)\s+([\w.[\]]+)\s+(?:from|in)\s+(.+)',
            command, re.IGNORECASE | re.DOTALL)

        if not match:
            return self._fail(
                "Format: 'json get path.to.key from {\"your\": \"json\"}'")

        path = match.group(1).strip()
        json_str = match.group(2).strip()

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return self._fail(f"Invalid JSON: {e}")

        # Navigate the path
        try:
            result = self._navigate_path(data, path)
        except (KeyError, IndexError, TypeError) as e:
            return self._fail(f"Path '{path}' not found: {e}")

        if isinstance(result, (dict, list)):
            indent = self._config.get("indent", 2)
            result_str = json.dumps(result, indent=indent, ensure_ascii=False)
        else:
            result_str = str(result)

        return self._ok(f"Result for '{path}':\n\n{result_str}")

    def _navigate_path(self, data, path):
        """Navigate a dot-notation path through JSON data."""
        parts = re.split(r'[.\[\]]', path)
        parts = [p for p in parts if p]  # Remove empty strings

        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current[part]
            elif isinstance(current, list):
                current = current[int(part)]
            else:
                raise TypeError(f"Cannot index into {type(current).__name__}")
        return current

    # ── Helpers ──────────────────────────────────────────────────

    def _extract_json(self, command):
        """Extract JSON string from the command."""
        # Look for JSON-like content (starts with { or [)
        match = re.search(r'([{\[][\s\S]*[}\]])', command)
        if match:
            return match.group(1)

        # Strip command prefix and see if the rest is JSON
        for prefix in ["format json", "prettify json", "validate json",
                        "minify json", "parse json", "compact json"]:
            if command.lower().startswith(prefix):
                remainder = command[len(prefix):].strip()
                if remainder:
                    return remainder

        return ""

    def _ok(self, msg):
        return {"success": True, "response": msg,
                "actions_taken": [{"action": "json_formatter"}], "spoken": False}

    def _fail(self, msg):
        return {"success": False, "response": msg,
                "actions_taken": [], "spoken": False}
