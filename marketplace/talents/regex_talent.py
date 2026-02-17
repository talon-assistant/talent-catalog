"""RegexTalent — test regex patterns and build them from descriptions.

Test patterns against text, see matches highlighted, and use the LLM
to build regex patterns from natural language descriptions.

Examples:
    "test regex \\d{3}-\\d{4} against text call 555-1234 today"
    "build a regex that matches email addresses"
    "regex help me match dates like 2024-01-15"
    "explain regex ^[a-z]+@[a-z]+\\.[a-z]{2,}$"
"""

import re
from talents.base import BaseTalent


class RegexTalent(BaseTalent):
    name = "regex_talent"
    description = "Test regex patterns and build them from descriptions using LLM"
    keywords = [
        "regex", "regular expression", "regexp", "pattern match",
        "test regex", "build regex", "explain regex", "test pattern",
    ]
    priority = 41

    _EXCLUSIONS = [
        "remind", "timer", "email", "note", "weather", "hue",
        "light", "search", "news", "todo", "task", "pomodoro",
        "docker", "github", "repo",
    ]

    _BUILD_SYSTEM_PROMPT = (
        "You are a regex expert. The user will describe a pattern they want to match. "
        "Return ONLY a JSON object with these keys:\n"
        '  "pattern": the regex pattern string\n'
        '  "flags": any flags needed (e.g., "i" for case-insensitive, "" for none)\n'
        '  "explanation": a brief explanation of how the pattern works\n'
        '  "examples": list of 2-3 example strings that would match\n'
        "\nReturn ONLY the JSON object, no markdown code fences."
    )

    _EXPLAIN_SYSTEM_PROMPT = (
        "You are a regex expert. The user will give you a regex pattern. "
        "Explain what it matches in clear, simple language. "
        "Break down each part of the pattern. Keep it concise."
    )

    def get_config_schema(self) -> dict:
        return {}

    def can_handle(self, command: str) -> bool:
        cmd = command.lower()
        if any(ex in cmd for ex in self._EXCLUSIONS):
            return False
        return any(kw in cmd for kw in self.keywords)

    def execute(self, command: str, context: dict) -> dict:
        cmd = command.lower().strip()

        # Test regex: "test regex PATTERN against ТЕКСТ"
        if any(p in cmd for p in ["test regex", "test pattern", "try regex"]):
            return self._test_regex(command)

        # Build regex: "build a regex that matches..."
        if any(p in cmd for p in ["build regex", "build a regex", "create regex",
                                   "make regex", "make a regex", "write regex",
                                   "regex for", "regex that match",
                                   "regex to match", "help me match"]):
            return self._build_regex(command, context)

        # Explain regex
        if any(p in cmd for p in ["explain regex", "explain pattern",
                                   "what does regex", "what does this regex"]):
            return self._explain_regex(command, context)

        # Default: if they give a pattern-like thing, try to test it
        if re.search(r'[\\.\[\]{}()+*?^$|]', command):
            return self._test_regex(command)

        return self._fail(
            "I can test, build, or explain regex patterns.\n"
            "  \u2022 Test: 'test regex \\d+ against text abc 123 def'\n"
            "  \u2022 Build: 'build a regex that matches email addresses'\n"
            "  \u2022 Explain: 'explain regex ^\\w+@\\w+\\.\\w+$'")

    # ── Test regex ───────────────────────────────────────────────

    def _test_regex(self, command):
        # Try to split pattern and test text
        # Formats: "test regex PATTERN against TEXT"
        #          "test regex PATTERN on TEXT"
        #          "PATTERN against TEXT"

        splits = re.split(r'\s+(?:against|on|with|in)\s+(?:text\s+)?', command, maxsplit=1, flags=re.IGNORECASE)

        if len(splits) < 2:
            return self._fail(
                "Please provide both a pattern and text.\n"
                "Format: 'test regex PATTERN against text YOUR TEXT'")

        pattern_part = splits[0]
        test_text = splits[1].strip()

        # Clean pattern: remove "test regex", "try regex" prefix
        pattern = re.sub(r'^(?:test|try)\s+(?:regex|pattern)\s*', '', pattern_part, flags=re.IGNORECASE).strip()

        if not pattern:
            return self._fail("No pattern provided.")
        if not test_text:
            return self._fail("No test text provided.")

        try:
            matches = list(re.finditer(pattern, test_text))
        except re.error as e:
            return self._fail(f"Invalid regex pattern: {e}")

        lines = [f"Pattern: `{pattern}`", f"Text: \"{test_text}\"\n"]

        if not matches:
            lines.append("No matches found.")
        else:
            lines.append(f"Found {len(matches)} match(es):\n")
            for i, m in enumerate(matches[:20]):
                groups = m.groups()
                if groups:
                    group_str = " | groups: " + ", ".join(
                        f"({j+1})={g}" for j, g in enumerate(groups) if g is not None)
                else:
                    group_str = ""
                lines.append(
                    f"  {i+1}. \"{m.group()}\" at position {m.start()}-{m.end()}{group_str}")

        return self._ok("\n".join(lines))

    # ── Build regex ──────────────────────────────────────────────

    def _build_regex(self, command, context):
        llm = context.get("llm")
        if not llm:
            return self._fail("LLM not available to build regex patterns.")

        # Strip prefixes
        description = command
        for prefix in ["build a regex", "build regex", "create a regex", "create regex",
                        "make a regex", "make regex", "write a regex", "write regex",
                        "regex for", "regex that matches", "regex to match",
                        "help me match"]:
            if description.lower().startswith(prefix):
                description = description[len(prefix):].strip()
                break

        response = llm.generate(
            f"Build a regex pattern for: {description}",
            system_prompt=self._BUILD_SYSTEM_PROMPT,
            temperature=0.2,
        )

        # Try to parse JSON
        import json
        try:
            json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                pattern = data.get("pattern", "")
                explanation = data.get("explanation", "")
                examples = data.get("examples", [])
                flags = data.get("flags", "")

                lines = [f"Pattern: `{pattern}`"]
                if flags:
                    lines.append(f"Flags: {flags}")
                if explanation:
                    lines.append(f"\n{explanation}")
                if examples:
                    lines.append("\nExample matches:")
                    for ex in examples:
                        lines.append(f"  \u2713 \"{ex}\"")

                return self._ok("\n".join(lines))
        except (json.JSONDecodeError, AttributeError):
            pass

        # Fallback: just return LLM response as-is
        return self._ok(response)

    # ── Explain regex ────────────────────────────────────────────

    def _explain_regex(self, command, context):
        llm = context.get("llm")
        if not llm:
            return self._fail("LLM not available to explain regex patterns.")

        # Extract pattern
        pattern = command
        for prefix in ["explain regex", "explain pattern", "explain this regex",
                        "what does regex", "what does this regex", "what does"]:
            if pattern.lower().startswith(prefix):
                pattern = pattern[len(prefix):].strip()
                break
        pattern = pattern.strip("`'\"")

        if not pattern:
            return self._fail("Please provide a regex pattern to explain.")

        response = llm.generate(
            f"Explain this regex pattern: {pattern}",
            system_prompt=self._EXPLAIN_SYSTEM_PROMPT,
            temperature=0.3,
        )

        return self._ok(f"Pattern: `{pattern}`\n\n{response}")

    # ── Helpers ──────────────────────────────────────────────────

    def _ok(self, msg):
        return {"success": True, "response": msg,
                "actions_taken": [{"action": "regex"}], "spoken": False}

    def _fail(self, msg):
        return {"success": False, "response": msg,
                "actions_taken": [], "spoken": False}
