"""DockerTalent — manage Docker containers and images via natural language.

List, start, stop, restart, and inspect containers. List and remove images.
Requires the Docker SDK for Python.

Examples:
    "list docker containers"
    "start container myapp"
    "stop container myapp"
    "show docker images"
    "docker logs for myapp"
    "restart container myapp"
"""

import re
from talents.base import BaseTalent

try:
    import docker
    _HAS_DOCKER = True
except ImportError:
    _HAS_DOCKER = False


class DockerTalent(BaseTalent):
    name = "docker_talent"
    description = "List, start, stop, and inspect Docker containers and images"
    keywords = [
        "docker", "container", "containers", "image", "images",
        "docker logs", "docker start", "docker stop", "docker restart",
    ]
    priority = 47

    _EXCLUSIONS = [
        "remind", "timer", "email", "note", "weather", "hue",
        "light", "search", "news", "todo", "task", "pomodoro",
        "github", "repo", "pull request",
    ]

    def __init__(self):
        super().__init__()
        self._client = None

    def get_config_schema(self) -> dict:
        return {
            "fields": [
                {"key": "docker_host", "label": "Docker Host (leave empty for default)",
                 "type": "string", "default": ""},
                {"key": "log_lines", "label": "Log Lines to Show",
                 "type": "int", "default": 30, "min": 5, "max": 200},
            ]
        }

    def update_config(self, config: dict) -> None:
        self._config = config
        self._client = None

    def _get_client(self):
        if self._client is None:
            host = self._config.get("docker_host", "")
            try:
                if host:
                    self._client = docker.DockerClient(base_url=host)
                else:
                    self._client = docker.from_env()
            except Exception as e:
                print(f"   [Docker] Connection error: {e}")
                return None
        return self._client

    def can_handle(self, command: str) -> bool:
        cmd = command.lower()
        if any(ex in cmd for ex in self._EXCLUSIONS):
            return False
        return any(kw in cmd for kw in self.keywords)

    def execute(self, command: str, context: dict) -> dict:
        if not _HAS_DOCKER:
            return self._fail("Docker SDK not installed. Run: pip install docker")

        client = self._get_client()
        if not client:
            return self._fail(
                "Cannot connect to Docker. Is Docker running?")

        cmd = command.lower().strip()
        container_name = self._extract_container(cmd)

        try:
            # Logs
            if "log" in cmd:
                if not container_name:
                    return self._fail("Which container? e.g., 'docker logs for myapp'")
                return self._show_logs(client, container_name)

            # Start
            if "start" in cmd and container_name:
                return self._start_container(client, container_name)

            # Stop
            if "stop" in cmd and container_name:
                return self._stop_container(client, container_name)

            # Restart
            if "restart" in cmd and container_name:
                return self._restart_container(client, container_name)

            # Inspect container
            if ("inspect" in cmd or "info" in cmd or "details" in cmd) and container_name:
                return self._inspect_container(client, container_name)

            # List images
            if "image" in cmd:
                return self._list_images(client)

            # List containers (default)
            return self._list_containers(client)

        except docker.errors.NotFound:
            return self._fail(f"Container '{container_name}' not found.")
        except docker.errors.APIError as e:
            return self._fail(f"Docker API error: {e.explanation}")
        except Exception as e:
            return self._fail(f"Docker error: {e}")

    # ── List containers ──────────────────────────────────────────

    def _list_containers(self, client):
        containers = client.containers.list(all=True)

        if not containers:
            return self._ok("No Docker containers found.")

        lines = ["Docker Containers:\n"]
        for c in containers:
            status = c.status
            if status == "running":
                icon = "\U0001f7e2"
            elif status == "exited":
                icon = "\U0001f534"
            else:
                icon = "\U0001f7e1"

            name = c.name
            image = c.image.tags[0] if c.image.tags else c.short_id
            lines.append(f"  {icon} {name} ({image}) \u2014 {status}")

        return self._ok("\n".join(lines))

    # ── Start / Stop / Restart ───────────────────────────────────

    def _start_container(self, client, name):
        container = client.containers.get(name)
        if container.status == "running":
            return self._ok(f"Container '{name}' is already running.")
        container.start()
        return self._ok(f"Started container '{name}'.")

    def _stop_container(self, client, name):
        container = client.containers.get(name)
        if container.status != "running":
            return self._ok(f"Container '{name}' is not running (status: {container.status}).")
        container.stop()
        return self._ok(f"Stopped container '{name}'.")

    def _restart_container(self, client, name):
        container = client.containers.get(name)
        container.restart()
        return self._ok(f"Restarted container '{name}'.")

    # ── Logs ─────────────────────────────────────────────────────

    def _show_logs(self, client, name):
        container = client.containers.get(name)
        tail = self._config.get("log_lines", 30)
        logs = container.logs(tail=tail, timestamps=False).decode("utf-8", errors="replace")

        if not logs.strip():
            return self._ok(f"No logs for container '{name}'.")

        # Truncate if very long
        if len(logs) > 3000:
            logs = logs[-3000:]
            logs = "...(truncated)\n" + logs

        return self._ok(f"Logs for '{name}' (last {tail} lines):\n\n{logs}")

    # ── Inspect ──────────────────────────────────────────────────

    def _inspect_container(self, client, name):
        container = client.containers.get(name)
        attrs = container.attrs

        config = attrs.get("Config", {})
        state = attrs.get("State", {})
        network = attrs.get("NetworkSettings", {})

        lines = [f"Container: {name}\n"]
        lines.append(f"  Image: {config.get('Image', 'N/A')}")
        lines.append(f"  Status: {state.get('Status', 'N/A')}")
        lines.append(f"  Started: {state.get('StartedAt', 'N/A')[:19]}")

        # Ports
        ports = network.get("Ports", {})
        if ports:
            port_strs = []
            for container_port, bindings in ports.items():
                if bindings:
                    for b in bindings:
                        port_strs.append(f"{b['HostPort']}->{container_port}")
                else:
                    port_strs.append(container_port)
            lines.append(f"  Ports: {', '.join(port_strs)}")

        # Environment (filtered — no secrets)
        env = config.get("Env", [])
        safe_env = [e for e in env if not any(
            s in e.upper() for s in ["KEY", "SECRET", "PASSWORD", "TOKEN"])]
        if safe_env:
            lines.append(f"  Env vars: {len(env)} ({len(env) - len(safe_env)} hidden)")

        # Mounts
        mounts = attrs.get("Mounts", [])
        if mounts:
            lines.append(f"  Volumes: {len(mounts)}")
            for m in mounts[:3]:
                lines.append(f"    {m.get('Source', '?')} -> {m.get('Destination', '?')}")

        return self._ok("\n".join(lines))

    # ── List images ──────────────────────────────────────────────

    def _list_images(self, client):
        images = client.images.list()

        if not images:
            return self._ok("No Docker images found.")

        lines = ["Docker Images:\n"]
        for img in images[:20]:
            tags = ", ".join(img.tags) if img.tags else img.short_id
            size_mb = img.attrs.get("Size", 0) / (1024 * 1024)
            lines.append(f"  \U0001f4e6 {tags} ({size_mb:.0f} MB)")

        if len(images) > 20:
            lines.append(f"\n  ...and {len(images) - 20} more")

        return self._ok("\n".join(lines))

    # ── Helpers ──────────────────────────────────────────────────

    def _extract_container(self, cmd):
        # "container myapp", "for myapp", etc.
        match = re.search(r'(?:container|for|named?)\s+([a-zA-Z0-9_.-]+)', cmd)
        if match:
            name = match.group(1)
            if name not in ("my", "the", "a", "all", "docker"):
                return name
        # Last word after known verbs
        for verb in ["start", "stop", "restart", "inspect", "logs"]:
            match = re.search(rf'{verb}\s+([a-zA-Z0-9_.-]+)', cmd)
            if match:
                name = match.group(1)
                if name not in ("container", "docker", "the", "a", "my", "all", "for"):
                    return name
        return ""

    def _ok(self, msg):
        return {"success": True, "response": msg,
                "actions_taken": [{"action": "docker"}], "spoken": False}

    def _fail(self, msg):
        return {"success": False, "response": msg,
                "actions_taken": [], "spoken": False}
