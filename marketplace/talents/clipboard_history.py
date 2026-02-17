"""ClipboardHistoryTalent — track and manage clipboard history.

Monitors clipboard changes and stores recent entries for retrieval.
Uses pyperclip for cross-platform clipboard access.

Examples:
    "show clipboard history"
    "paste item 3 from clipboard"
    "search clipboard for url"
    "clear clipboard history"
    "copy that again"
"""

import threading
import time
from datetime import datetime
from talents.base import BaseTalent

try:
    import pyperclip
    _HAS_PYPERCLIP = True
except ImportError:
    _HAS_PYPERCLIP = False


class ClipboardHistoryTalent(BaseTalent):
    name = "clipboard_history"
    description = "Track clipboard history and paste from previous entries"
    keywords = [
        "clipboard", "clipboard history", "paste history", "copy history",
        "last copied", "previous copy", "clear clipboard",
        "search clipboard", "show clipboard",
    ]
    priority = 43

    _EXCLUSIONS = [
        "remind", "timer", "email", "note", "weather", "hue",
        "light", "search", "news", "todo", "task", "pomodoro",
        "organize", "file",
    ]

    def __init__(self):
        super().__init__()
        self._history = []  # list of {"text": ..., "timestamp": ...}
        self._max_entries = 50
        self._monitor_thread = None
        self._running = False
        self._last_content = ""

    def get_config_schema(self) -> dict:
        return {
            "fields": [
                {"key": "max_entries", "label": "Max History Entries",
                 "type": "int", "default": 50, "min": 10, "max": 500},
                {"key": "auto_monitor", "label": "Auto-Monitor Clipboard",
                 "type": "bool", "default": True},
                {"key": "monitor_interval", "label": "Monitor Interval (seconds)",
                 "type": "float", "default": 1.0, "min": 0.5, "max": 10.0, "step": 0.5},
            ]
        }

    def initialize(self, config: dict) -> None:
        self._max_entries = self._config.get("max_entries", 50)
        if self._config.get("auto_monitor", True):
            self._start_monitor()

    def update_config(self, config: dict) -> None:
        self._config = config
        self._max_entries = config.get("max_entries", 50)
        if config.get("auto_monitor", True):
            self._start_monitor()
        else:
            self._stop_monitor()

    def can_handle(self, command: str) -> bool:
        cmd = command.lower()
        if any(ex in cmd for ex in self._EXCLUSIONS):
            return False
        return any(kw in cmd for kw in self.keywords)

    def execute(self, command: str, context: dict) -> dict:
        if not _HAS_PYPERCLIP:
            return self._fail("pyperclip is not installed. Run: pip install pyperclip")

        cmd = command.lower().strip()

        # Clear history
        if "clear" in cmd and "clipboard" in cmd:
            return self._clear()

        # Search clipboard
        if "search" in cmd and "clipboard" in cmd:
            query = cmd.split("search clipboard", 1)[-1].strip()
            query = query.lstrip("for ").strip()
            return self._search(query)

        # Paste specific item
        import re
        num_match = re.search(r'(?:paste|use|get)\s+(?:item\s+)?(\d+)', cmd)
        if num_match:
            index = int(num_match.group(1)) - 1  # 1-based to 0-based
            return self._paste_item(index)

        # Paste last / previous
        if any(p in cmd for p in ["last copied", "previous copy", "copy again",
                                   "paste previous", "paste last"]):
            return self._paste_item(1)  # Second most recent (index 1)

        # Show history (default)
        return self._show_history()

    # ── Show history ─────────────────────────────────────────────

    def _show_history(self):
        # Grab current clipboard and add if new
        self._check_clipboard()

        if not self._history:
            return self._ok("Clipboard history is empty.")

        lines = [f"Clipboard History ({len(self._history)} entries):\n"]
        for i, entry in enumerate(self._history[:15]):
            text = entry["text"]
            preview = text[:60].replace("\n", " ")
            if len(text) > 60:
                preview += "..."
            ts = entry.get("timestamp", "")
            lines.append(f"  {i + 1}. {preview}  ({ts})")

        if len(self._history) > 15:
            lines.append(f"\n  ...and {len(self._history) - 15} older entries")
        lines.append("\nSay 'paste item N' to copy an entry back to clipboard.")

        return self._ok("\n".join(lines))

    # ── Paste item ───────────────────────────────────────────────

    def _paste_item(self, index):
        self._check_clipboard()

        if index < 0 or index >= len(self._history):
            return self._fail(f"No clipboard entry at position {index + 1}.")

        entry = self._history[index]
        text = entry["text"]

        try:
            pyperclip.copy(text)
        except Exception as e:
            return self._fail(f"Failed to copy to clipboard: {e}")

        preview = text[:80].replace("\n", " ")
        if len(text) > 80:
            preview += "..."
        return self._ok(f"Copied to clipboard: {preview}")

    # ── Search ───────────────────────────────────────────────────

    def _search(self, query):
        if not query:
            return self._fail("What should I search for in clipboard history?")

        query_lower = query.lower()
        matches = []
        for i, entry in enumerate(self._history):
            if query_lower in entry["text"].lower():
                matches.append((i, entry))

        if not matches:
            return self._ok(f"No clipboard entries matching \"{query}\".")

        lines = [f"Found {len(matches)} match(es) for \"{query}\":\n"]
        for idx, entry in matches[:10]:
            preview = entry["text"][:60].replace("\n", " ")
            if len(entry["text"]) > 60:
                preview += "..."
            lines.append(f"  {idx + 1}. {preview}")

        return self._ok("\n".join(lines))

    # ── Clear ────────────────────────────────────────────────────

    def _clear(self):
        count = len(self._history)
        self._history.clear()
        return self._ok(f"Cleared {count} clipboard entries.")

    # ── Clipboard monitoring ─────────────────────────────────────

    def _check_clipboard(self):
        """Check clipboard for new content and add to history."""
        if not _HAS_PYPERCLIP:
            return
        try:
            content = pyperclip.paste()
            if content and content != self._last_content:
                self._last_content = content
                self._history.insert(0, {
                    "text": content,
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                })
                # Trim to max
                if len(self._history) > self._max_entries:
                    self._history = self._history[:self._max_entries]
        except Exception:
            pass

    def _start_monitor(self):
        if self._running:
            return
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def _stop_monitor(self):
        self._running = False

    def _monitor_loop(self):
        interval = self._config.get("monitor_interval", 1.0)
        while self._running:
            self._check_clipboard()
            time.sleep(interval)

    # ── Helpers ──────────────────────────────────────────────────

    def _ok(self, msg):
        return {"success": True, "response": msg,
                "actions_taken": [{"action": "clipboard"}], "spoken": False}

    def _fail(self, msg):
        return {"success": False, "response": msg,
                "actions_taken": [], "spoken": False}
