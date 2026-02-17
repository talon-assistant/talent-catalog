"""PomodoroTalent — focus timer with work/break cycles and notifications.

Implements the Pomodoro technique with configurable durations.
Uses threading.Timer for countdown and plyer for desktop notifications.

Examples:
    "start pomodoro"
    "start a focus session"
    "pomodoro status"
    "stop pomodoro"
    "take a break"
"""

import threading
import time
from talents.base import BaseTalent

try:
    from plyer import notification as plyer_notification
    _HAS_PLYER = True
except ImportError:
    _HAS_PLYER = False


class PomodoroTalent(BaseTalent):
    name = "pomodoro"
    description = "Pomodoro technique timer with work/break cycles"
    keywords = [
        "pomodoro", "focus", "focus session", "focus timer",
        "work timer", "take a break", "start timer",
    ]
    priority = 44

    _EXCLUSIONS = [
        "remind", "alarm", "email", "note", "weather", "hue",
        "light", "search", "todo", "task",
    ]

    def __init__(self):
        super().__init__()
        self._timer = None
        self._state = "idle"  # idle | working | short_break | long_break
        self._session_count = 0
        self._started_at = 0
        self._duration = 0
        self._notify_cb = None

    def get_config_schema(self) -> dict:
        return {
            "fields": [
                {"key": "work_minutes", "label": "Work Duration (minutes)",
                 "type": "int", "default": 25, "min": 5, "max": 120},
                {"key": "short_break_minutes", "label": "Short Break (minutes)",
                 "type": "int", "default": 5, "min": 1, "max": 30},
                {"key": "long_break_minutes", "label": "Long Break (minutes)",
                 "type": "int", "default": 15, "min": 5, "max": 60},
                {"key": "sessions_before_long_break", "label": "Sessions Before Long Break",
                 "type": "int", "default": 4, "min": 2, "max": 10},
            ]
        }

    def can_handle(self, command: str) -> bool:
        cmd = command.lower()
        if any(ex in cmd for ex in self._EXCLUSIONS):
            return False
        return any(kw in cmd for kw in self.keywords)

    def execute(self, command: str, context: dict) -> dict:
        cmd = command.lower().strip()
        self._notify_cb = context.get("notify")

        # Stop / cancel
        if any(p in cmd for p in ["stop pomodoro", "cancel pomodoro", "stop timer",
                                   "cancel timer", "end session", "stop focus"]):
            return self._stop()

        # Status
        if any(p in cmd for p in ["pomodoro status", "timer status", "how much time",
                                   "time left", "time remaining"]):
            return self._status()

        # Take a break (manual)
        if "take a break" in cmd or "start break" in cmd:
            return self._start_break()

        # Start
        if any(p in cmd for p in ["start", "begin", "pomodoro", "focus"]):
            return self._start_work()

        return self._status()

    # ── Start work session ───────────────────────────────────────

    def _start_work(self):
        if self._state == "working":
            elapsed = int(time.time() - self._started_at)
            remaining = max(0, self._duration - elapsed)
            return self._ok(f"Already in a work session! {remaining // 60}m {remaining % 60}s remaining.")

        work_min = self._config.get("work_minutes", 25)
        self._duration = work_min * 60
        self._state = "working"
        self._started_at = time.time()

        self._cancel_timer()
        self._timer = threading.Timer(self._duration, self._on_work_done)
        self._timer.daemon = True
        self._timer.start()

        self._session_count += 1
        return self._ok(f"Pomodoro #{self._session_count} started! Focus for {work_min} minutes.")

    def _on_work_done(self):
        self._state = "idle"
        self._notify("Pomodoro Complete!", "Time for a break. Great work!")
        print(f"   [Pomodoro] Work session #{self._session_count} complete!")

    # ── Break ────────────────────────────────────────────────────

    def _start_break(self):
        if self._state in ("short_break", "long_break"):
            elapsed = int(time.time() - self._started_at)
            remaining = max(0, self._duration - elapsed)
            return self._ok(f"Already on a break! {remaining // 60}m {remaining % 60}s remaining.")

        long_every = self._config.get("sessions_before_long_break", 4)
        if self._session_count > 0 and self._session_count % long_every == 0:
            break_min = self._config.get("long_break_minutes", 15)
            self._state = "long_break"
            label = "Long break"
        else:
            break_min = self._config.get("short_break_minutes", 5)
            self._state = "short_break"
            label = "Short break"

        self._duration = break_min * 60
        self._started_at = time.time()

        self._cancel_timer()
        self._timer = threading.Timer(self._duration, self._on_break_done)
        self._timer.daemon = True
        self._timer.start()

        return self._ok(f"{label} started! Relax for {break_min} minutes.")

    def _on_break_done(self):
        self._state = "idle"
        self._notify("Break Over!", "Ready to start another focus session?")
        print("   [Pomodoro] Break complete!")

    # ── Stop ─────────────────────────────────────────────────────

    def _stop(self):
        if self._state == "idle":
            return self._ok("No active pomodoro session.")

        prev_state = self._state
        self._cancel_timer()
        self._state = "idle"

        if prev_state == "working":
            return self._ok(f"Work session stopped. Completed {self._session_count} session(s) total.")
        else:
            return self._ok("Break stopped.")

    # ── Status ───────────────────────────────────────────────────

    def _status(self):
        if self._state == "idle":
            return self._ok(
                f"No active session. {self._session_count} session(s) completed today.")

        elapsed = int(time.time() - self._started_at)
        remaining = max(0, self._duration - elapsed)
        mins, secs = remaining // 60, remaining % 60

        state_labels = {
            "working": "Focused work",
            "short_break": "Short break",
            "long_break": "Long break",
        }
        label = state_labels.get(self._state, self._state)

        return self._ok(
            f"{label} in progress \u2014 {mins}m {secs}s remaining.\n"
            f"Sessions completed: {self._session_count}")

    # ── Helpers ──────────────────────────────────────────────────

    def _cancel_timer(self):
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _notify(self, title, message):
        if _HAS_PLYER:
            try:
                plyer_notification.notify(
                    title=title, message=message,
                    app_name="Talon", timeout=10)
            except Exception:
                pass
        if self._notify_cb:
            try:
                self._notify_cb(title, message)
            except Exception:
                pass

    def _ok(self, msg):
        return {"success": True, "response": msg,
                "actions_taken": [{"action": "pomodoro"}], "spoken": False}
