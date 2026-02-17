"""FileOrganizerTalent — search, sort, and organize files on disk.

Sort downloads by file type, find large files, and list directory contents.
No external dependencies.

Examples:
    "organize my downloads folder"
    "find large files in documents"
    "list files in C:/Users/me/Desktop"
    "sort downloads by type"
    "find pdf files in my documents"
"""

import os
import shutil
import re
from datetime import datetime
from talents.base import BaseTalent


class FileOrganizerTalent(BaseTalent):
    name = "file_organizer"
    description = "Search, move, and organize files on disk"
    keywords = [
        "organize", "sort files", "find file", "find files", "large files",
        "list files", "file organizer", "clean up", "sort downloads",
        "find pdf", "find images", "find documents",
    ]
    priority = 42

    _EXCLUSIONS = [
        "remind", "timer", "email", "note", "weather", "hue",
        "light", "search", "news", "todo", "task", "pomodoro",
    ]

    # Common file type categories
    _TYPE_MAP = {
        "images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico", ".tiff"],
        "documents": [".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".xls", ".xlsx", ".csv", ".ppt", ".pptx"],
        "audio": [".mp3", ".wav", ".flac", ".ogg", ".aac", ".wma", ".m4a"],
        "video": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm"],
        "archives": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"],
        "code": [".py", ".js", ".ts", ".html", ".css", ".java", ".cpp", ".c", ".rs", ".go"],
        "executables": [".exe", ".msi", ".bat", ".sh", ".cmd"],
    }

    def get_config_schema(self) -> dict:
        return {
            "fields": [
                {"key": "default_directory", "label": "Default Directory",
                 "type": "string", "default": ""},
                {"key": "large_file_mb", "label": "Large File Threshold (MB)",
                 "type": "int", "default": 100, "min": 1, "max": 10000},
                {"key": "max_results", "label": "Max Results to Show",
                 "type": "int", "default": 20, "min": 5, "max": 100},
            ]
        }

    def can_handle(self, command: str) -> bool:
        cmd = command.lower()
        if any(ex in cmd for ex in self._EXCLUSIONS):
            return False
        return any(kw in cmd for kw in self.keywords)

    def execute(self, command: str, context: dict) -> dict:
        cmd = command.lower().strip()

        # Extract directory from command
        directory = self._extract_path(command)

        # Organize / sort by type
        if any(p in cmd for p in ["organize", "sort by type", "sort files", "sort downloads",
                                   "clean up"]):
            if not directory:
                return self._fail("Which folder should I organize? Please include a path.")
            return self._organize_by_type(directory)

        # Find large files
        if "large file" in cmd or "big file" in cmd:
            if not directory:
                directory = self._config.get("default_directory", "")
            if not directory:
                return self._fail("Which folder should I search? Please include a path.")
            return self._find_large_files(directory)

        # Find files by extension
        ext_match = re.search(r'find\s+(\w+)\s+files?', cmd)
        if ext_match:
            file_type = ext_match.group(1)
            if not directory:
                directory = self._config.get("default_directory", "")
            if not directory:
                return self._fail("Which folder should I search? Please include a path.")
            return self._find_by_type(directory, file_type)

        # List files
        if any(p in cmd for p in ["list files", "show files", "what files", "what's in"]):
            if not directory:
                return self._fail("Which folder should I list? Please include a path.")
            return self._list_files(directory)

        return self._fail(
            "I can organize folders by type, find large files, find files by type, "
            "or list directory contents. Please be more specific.")

    # ── Organize by type ─────────────────────────────────────────

    def _organize_by_type(self, directory):
        if not os.path.isdir(directory):
            return self._fail(f"Directory not found: {directory}")

        moved = {}
        errors = 0

        for fname in os.listdir(directory):
            fpath = os.path.join(directory, fname)
            if not os.path.isfile(fpath):
                continue

            ext = os.path.splitext(fname)[1].lower()
            category = "other"
            for cat, exts in self._TYPE_MAP.items():
                if ext in exts:
                    category = cat
                    break

            dest_dir = os.path.join(directory, category)
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, fname)

            try:
                if not os.path.exists(dest_path):
                    shutil.move(fpath, dest_path)
                    moved.setdefault(category, 0)
                    moved[category] = moved[category] + 1
            except Exception:
                errors += 1

        if not moved:
            return self._ok("No files to organize in that folder.")

        lines = [f"Organized {sum(moved.values())} files in {os.path.basename(directory)}:\n"]
        for cat, count in sorted(moved.items()):
            lines.append(f"  {cat}/  \u2190 {count} file(s)")
        if errors:
            lines.append(f"\n({errors} file(s) could not be moved)")

        return self._ok("\n".join(lines))

    # ── Find large files ─────────────────────────────────────────

    def _find_large_files(self, directory):
        if not os.path.isdir(directory):
            return self._fail(f"Directory not found: {directory}")

        threshold_mb = self._config.get("large_file_mb", 100)
        threshold = threshold_mb * 1024 * 1024
        max_results = self._config.get("max_results", 20)
        large = []

        try:
            for root, dirs, files in os.walk(directory):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    try:
                        size = os.path.getsize(fpath)
                        if size >= threshold:
                            large.append((fpath, size))
                    except OSError:
                        continue
        except PermissionError:
            return self._fail(f"Permission denied accessing {directory}")

        if not large:
            return self._ok(f"No files larger than {threshold_mb} MB found in {directory}.")

        large.sort(key=lambda x: x[1], reverse=True)
        lines = [f"Files larger than {threshold_mb} MB in {os.path.basename(directory)}:\n"]
        for fpath, size in large[:max_results]:
            size_mb = size / (1024 * 1024)
            rel = os.path.relpath(fpath, directory)
            lines.append(f"  {size_mb:,.1f} MB \u2014 {rel}")

        if len(large) > max_results:
            lines.append(f"\n  ...and {len(large) - max_results} more")

        return self._ok("\n".join(lines))

    # ── Find by type ─────────────────────────────────────────────

    def _find_by_type(self, directory, file_type):
        if not os.path.isdir(directory):
            return self._fail(f"Directory not found: {directory}")

        max_results = self._config.get("max_results", 20)

        # Map type name to extensions
        extensions = set()
        file_type_lower = file_type.lower()

        # Check if it's a category name
        if file_type_lower in self._TYPE_MAP:
            extensions = set(self._TYPE_MAP[file_type_lower])
        else:
            # Check for common aliases
            aliases = {
                "pdf": [".pdf"], "image": self._TYPE_MAP["images"],
                "photo": self._TYPE_MAP["images"], "picture": self._TYPE_MAP["images"],
                "video": self._TYPE_MAP["video"], "music": self._TYPE_MAP["audio"],
                "audio": self._TYPE_MAP["audio"], "zip": [".zip", ".rar", ".7z"],
                "python": [".py"], "javascript": [".js"],
            }
            extensions = set(aliases.get(file_type_lower, [f".{file_type_lower}"]))

        found = []
        try:
            for root, dirs, files in os.walk(directory):
                for fname in files:
                    ext = os.path.splitext(fname)[1].lower()
                    if ext in extensions:
                        fpath = os.path.join(root, fname)
                        try:
                            size = os.path.getsize(fpath)
                            found.append((fpath, size))
                        except OSError:
                            found.append((fpath, 0))
        except PermissionError:
            return self._fail(f"Permission denied accessing {directory}")

        if not found:
            return self._ok(f"No {file_type} files found in {directory}.")

        found.sort(key=lambda x: x[1], reverse=True)
        lines = [f"Found {len(found)} {file_type} file(s) in {os.path.basename(directory)}:\n"]
        for fpath, size in found[:max_results]:
            size_str = f"{size / 1024:.0f} KB" if size < 1024 * 1024 else f"{size / (1024*1024):.1f} MB"
            rel = os.path.relpath(fpath, directory)
            lines.append(f"  {rel} ({size_str})")

        if len(found) > max_results:
            lines.append(f"\n  ...and {len(found) - max_results} more")

        return self._ok("\n".join(lines))

    # ── List files ───────────────────────────────────────────────

    def _list_files(self, directory):
        if not os.path.isdir(directory):
            return self._fail(f"Directory not found: {directory}")

        max_results = self._config.get("max_results", 20)
        entries = []

        try:
            for name in os.listdir(directory):
                fpath = os.path.join(directory, name)
                is_dir = os.path.isdir(fpath)
                try:
                    size = os.path.getsize(fpath) if not is_dir else 0
                    mtime = os.path.getmtime(fpath)
                except OSError:
                    size, mtime = 0, 0
                entries.append((name, is_dir, size, mtime))
        except PermissionError:
            return self._fail(f"Permission denied accessing {directory}")

        if not entries:
            return self._ok(f"{directory} is empty.")

        # Dirs first, then files sorted by name
        entries.sort(key=lambda e: (not e[1], e[0].lower()))

        lines = [f"Contents of {os.path.basename(directory)} ({len(entries)} items):\n"]
        for name, is_dir, size, mtime in entries[:max_results]:
            if is_dir:
                lines.append(f"  \U0001f4c1 {name}/")
            else:
                size_str = f"{size / 1024:.0f} KB" if size < 1024 * 1024 else f"{size / (1024*1024):.1f} MB"
                lines.append(f"  \U0001f4c4 {name} ({size_str})")

        if len(entries) > max_results:
            lines.append(f"\n  ...and {len(entries) - max_results} more")

        return self._ok("\n".join(lines))

    # ── Helpers ──────────────────────────────────────────────────

    def _extract_path(self, command):
        """Try to extract a filesystem path from the command."""
        # Look for explicit paths (C:\..., /home/..., ~/...)
        path_match = re.search(r'(?:in|from|at|to)\s+([A-Za-z]:[/\\][^\s,]+|/[^\s,]+|~[/\\][^\s,]+)', command)
        if path_match:
            path = path_match.group(1)
            path = os.path.expanduser(path)
            return path

        # Check for known folder names
        known = {
            "downloads": os.path.expanduser("~/Downloads"),
            "desktop": os.path.expanduser("~/Desktop"),
            "documents": os.path.expanduser("~/Documents"),
            "pictures": os.path.expanduser("~/Pictures"),
            "music": os.path.expanduser("~/Music"),
            "videos": os.path.expanduser("~/Videos"),
        }
        cmd_lower = command.lower()
        for name, path in known.items():
            if name in cmd_lower:
                return path

        return self._config.get("default_directory", "")

    def _ok(self, msg):
        return {"success": True, "response": msg,
                "actions_taken": [{"action": "file_organizer"}], "spoken": False}

    def _fail(self, msg):
        return {"success": False, "response": msg,
                "actions_taken": [], "spoken": False}
