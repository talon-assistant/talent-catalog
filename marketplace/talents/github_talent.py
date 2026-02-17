"""GitHubTalent — browse repos, PRs, issues, and notifications via GitHub API.

Uses PyGithub for API access. Requires a personal access token configured
in the talent settings.

Examples:
    "show my github notifications"
    "list pull requests for myuser/myrepo"
    "show issues in myuser/myrepo"
    "github status of myuser/myrepo"
    "list my github repos"
"""

import re
from talents.base import BaseTalent

try:
    from github import Github, GithubException
    _HAS_GITHUB = True
except ImportError:
    _HAS_GITHUB = False


class GitHubTalent(BaseTalent):
    name = "github_talent"
    description = "Check repository status, PRs, issues, and notifications via GitHub API"
    keywords = [
        "github", "repo", "repository", "pull request", "pull requests",
        "issue", "issues", "pr", "prs", "commit", "commits",
        "github notifications", "my repos",
    ]
    priority = 48

    _EXCLUSIONS = [
        "remind", "timer", "email", "note", "weather", "hue",
        "light", "search", "news", "todo", "task", "pomodoro",
    ]

    def __init__(self):
        super().__init__()
        self._client = None

    def get_config_schema(self) -> dict:
        return {
            "fields": [
                {"key": "access_token", "label": "GitHub Personal Access Token",
                 "type": "password", "default": ""},
                {"key": "default_repo", "label": "Default Repository (owner/repo)",
                 "type": "string", "default": ""},
                {"key": "max_results", "label": "Max Results",
                 "type": "int", "default": 10, "min": 3, "max": 50},
            ]
        }

    def update_config(self, config: dict) -> None:
        self._config = config
        self._client = None  # Force re-auth

    def _get_client(self):
        if self._client is None:
            token = self._config.get("access_token", "")
            if not token:
                return None
            self._client = Github(token)
        return self._client

    def can_handle(self, command: str) -> bool:
        cmd = command.lower()
        if any(ex in cmd for ex in self._EXCLUSIONS):
            return False
        return any(kw in cmd for kw in self.keywords)

    def execute(self, command: str, context: dict) -> dict:
        if not _HAS_GITHUB:
            return self._fail("PyGithub is not installed. Run: pip install PyGithub")

        client = self._get_client()
        if not client:
            return self._fail(
                "GitHub access token not configured. "
                "Set it in the GitHub talent settings (gear icon).")

        cmd = command.lower().strip()
        repo_name = self._extract_repo(command)

        try:
            # Notifications
            if "notification" in cmd:
                return self._show_notifications(client)

            # List user repos
            if any(p in cmd for p in ["my repo", "list repo", "my github repo"]):
                return self._list_repos(client)

            # Pull requests
            if any(p in cmd for p in ["pull request", "pr", "prs"]):
                if not repo_name:
                    return self._fail("Which repository? Use format: owner/repo")
                return self._list_prs(client, repo_name)

            # Issues
            if "issue" in cmd:
                if not repo_name:
                    return self._fail("Which repository? Use format: owner/repo")
                return self._list_issues(client, repo_name)

            # Commits
            if "commit" in cmd:
                if not repo_name:
                    return self._fail("Which repository? Use format: owner/repo")
                return self._list_commits(client, repo_name)

            # Repo status (default)
            if repo_name:
                return self._repo_status(client, repo_name)

            return self._fail(
                "I can show notifications, list repos, PRs, issues, or commits. "
                "Try: 'show my github repos' or 'list PRs for owner/repo'")

        except GithubException as e:
            return self._fail(f"GitHub API error: {e.data.get('message', str(e))}")
        except Exception as e:
            return self._fail(f"GitHub error: {e}")

    # ── Notifications ────────────────────────────────────────────

    def _show_notifications(self, client):
        max_results = self._config.get("max_results", 10)
        notifications = list(client.get_user().get_notifications()[:max_results])

        if not notifications:
            return self._ok("No unread GitHub notifications.")

        lines = [f"GitHub Notifications ({len(notifications)}):\n"]
        for n in notifications:
            repo = n.repository.full_name
            reason = n.reason.replace("_", " ")
            lines.append(f"  \u2022 [{repo}] {n.subject.title} ({reason})")

        return self._ok("\n".join(lines))

    # ── List repos ───────────────────────────────────────────────

    def _list_repos(self, client):
        max_results = self._config.get("max_results", 10)
        user = client.get_user()
        repos = list(user.get_repos(sort="updated")[:max_results])

        if not repos:
            return self._ok("No repositories found.")

        lines = [f"Your repositories (showing {len(repos)}):\n"]
        for r in repos:
            stars = f"\u2b50{r.stargazers_count}" if r.stargazers_count else ""
            private = " \U0001f512" if r.private else ""
            lang = f" ({r.language})" if r.language else ""
            lines.append(f"  \u2022 {r.full_name}{private}{lang} {stars}")

        return self._ok("\n".join(lines))

    # ── Pull requests ────────────────────────────────────────────

    def _list_prs(self, client, repo_name):
        max_results = self._config.get("max_results", 10)
        repo = client.get_repo(repo_name)
        prs = list(repo.get_pulls(state="open")[:max_results])

        if not prs:
            return self._ok(f"No open pull requests in {repo_name}.")

        lines = [f"Open PRs in {repo_name} ({len(prs)}):\n"]
        for pr in prs:
            status = "\U0001f7e2" if pr.mergeable else "\U0001f534"
            lines.append(f"  {status} #{pr.number}: {pr.title} (by {pr.user.login})")

        return self._ok("\n".join(lines))

    # ── Issues ───────────────────────────────────────────────────

    def _list_issues(self, client, repo_name):
        max_results = self._config.get("max_results", 10)
        repo = client.get_repo(repo_name)
        issues = list(repo.get_issues(state="open")[:max_results])

        # Filter out pull requests (GitHub API returns PRs as issues too)
        issues = [i for i in issues if not i.pull_request]

        if not issues:
            return self._ok(f"No open issues in {repo_name}.")

        lines = [f"Open issues in {repo_name} ({len(issues)}):\n"]
        for issue in issues:
            labels = " ".join(f"[{l.name}]" for l in issue.labels[:3])
            lines.append(f"  \u2022 #{issue.number}: {issue.title} {labels}")

        return self._ok("\n".join(lines))

    # ── Commits ──────────────────────────────────────────────────

    def _list_commits(self, client, repo_name):
        max_results = self._config.get("max_results", 10)
        repo = client.get_repo(repo_name)
        commits = list(repo.get_commits()[:max_results])

        if not commits:
            return self._ok(f"No commits found in {repo_name}.")

        lines = [f"Recent commits in {repo_name}:\n"]
        for c in commits:
            sha = c.sha[:7]
            msg = c.commit.message.split("\n")[0][:60]
            author = c.commit.author.name if c.commit.author else "unknown"
            lines.append(f"  {sha} {msg} ({author})")

        return self._ok("\n".join(lines))

    # ── Repo status ──────────────────────────────────────────────

    def _repo_status(self, client, repo_name):
        repo = client.get_repo(repo_name)

        lines = [f"Repository: {repo.full_name}\n"]
        if repo.description:
            lines.append(f"  {repo.description}\n")
        lines.append(f"  \u2b50 Stars: {repo.stargazers_count}")
        lines.append(f"  \U0001f534 Open issues: {repo.open_issues_count}")
        lines.append(f"  \U0001f501 Forks: {repo.forks_count}")
        if repo.language:
            lines.append(f"  \U0001f4bb Language: {repo.language}")
        lines.append(f"  \U0001f4c5 Last push: {repo.pushed_at.strftime('%Y-%m-%d %H:%M') if repo.pushed_at else 'N/A'}")

        # Recent activity
        try:
            latest = list(repo.get_commits()[:1])
            if latest:
                c = latest[0]
                lines.append(f"  \U0001f4dd Last commit: {c.commit.message.split(chr(10))[0][:50]}")
        except Exception:
            pass

        return self._ok("\n".join(lines))

    # ── Helpers ──────────────────────────────────────────────────

    def _extract_repo(self, command):
        # Look for owner/repo pattern
        match = re.search(r'(?:for|in|of|repo)\s+([\w.-]+/[\w.-]+)', command)
        if match:
            return match.group(1)
        # Standalone owner/repo
        match = re.search(r'([\w.-]+/[\w.-]+)', command)
        if match:
            candidate = match.group(1)
            # Avoid matching things like "pull/request"
            if candidate.count("/") == 1 and len(candidate) > 3:
                return candidate
        return self._config.get("default_repo", "")

    def _ok(self, msg):
        return {"success": True, "response": msg,
                "actions_taken": [{"action": "github"}], "spoken": False}

    def _fail(self, msg):
        return {"success": False, "response": msg,
                "actions_taken": [], "spoken": False}
