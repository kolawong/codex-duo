#!/usr/bin/env python3
"""Read-only stdio protocol probe. Never starts a thread or model turn."""
import json
import os
from pathlib import Path
import selectors
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
CLI = "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"


def probe(extra, read_plugin=False):
    # Independent short-lived stdio process; no connection to the desktop daemon.
    with tempfile.TemporaryFile(mode="w+b") as errors:
        process = subprocess.Popen([CLI, "app-server", "--stdio", "--strict-config",
                                    "-c", "features.hooks=false",
                                    "-c", 'sqlite_home="' + str(ROOT / "evidence/current/probe-state") + '"',
                                    *extra],
                                   cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=errors, bufsize=0)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        notifications = []
        buffer = b""

        def send(message):
            process.stdin.write((json.dumps(message) + "\n").encode())
            process.stdin.flush()

        def request(identifier, method, params):
            nonlocal buffer
            send({"id": identifier, "method": method, "params": params})
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                if b"\n" not in buffer:
                    if not selector.select(max(0, deadline - time.monotonic())):
                        break
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        raise RuntimeError("app-server exited before response")
                    buffer += chunk
                    continue
                line, buffer = buffer.split(b"\n", 1)
                reply = json.loads(line)
                if reply.get("id") == identifier:
                    return reply
                # Retain method names only; no transcripts, auth, or notification payloads.
                if "method" in reply:
                    notifications.append(reply["method"])
            raise RuntimeError("app-server response timeout")

        output = {"methods_requested": [], "model_calls": 0, "thread_starts": 0}
        try:
            output["methods_requested"].append("initialize")
            initialized = request(1, "initialize", {
                "clientInfo": {"name": "codex_duo_offline_probe", "title": "Codex Duo Offline Probe", "version": "0.1.0"},
                "capabilities": {"experimentalApi": True}})
            output["initialize_error"] = initialized.get("error")
            send({"method": "initialized", "params": {}})
            output["methods_requested"].append("config/read")
            reply = request(2, "config/read", {"cwd": str(ROOT), "includeLayers": False})
            output["config_error"] = reply.get("error")
            config = reply.get("result", {}).get("config", {})
            output["effective_config"] = {k: config[k] for k in [
                "model", "model_reasoning_effort", "agents"] if k in config}
            if read_plugin and not reply.get("error"):
                output["methods_requested"].append("plugin/read")
                plugin = request(3, "plugin/read", {
                    "pluginName": "codex-duo",
                    "marketplacePath": str(ROOT / ".agents/plugins/marketplace.json")})
                output["plugin_error"] = plugin.get("error")
                # Select identity and skills only; a read never installs the plugin.
                detail = plugin.get("result", {})
                output["plugin_result_keys"] = sorted(detail)
                def select(value):
                    if isinstance(value, list):
                        return [select(x) for x in value]
                    if isinstance(value, dict):
                        return {k: select(v) for k, v in value.items() if k in [
                            "plugin", "name", "version", "id", "skills", "path", "enabled",
                            "installed", "description", "displayName", "marketplaceName"]}
                    return value
                output["plugin_detail"] = select(detail)
        except (RuntimeError, BrokenPipeError, ValueError) as error:
            output["probe_error"] = str(error)
        finally:
            selector.close()
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
            errors.seek(0)
            stderr = errors.read().decode(errors="replace")
            output["stderr_byte_count"] = len(stderr)
            output["startup_errors"] = [line[:300] for line in stderr.splitlines()
                                        if line.startswith("Error:")]
            output["notification_methods"] = sorted(set(notifications))
        return output


if __name__ == "__main__":
    valid = probe(["-c", "agents.enabled=false", "-c", "agents.max_concurrent_threads_per_session=1",
                   "-c", 'agents.default_subagent_model="gpt-6-luna"',
                   "-c", 'agents.default_subagent_reasoning_effort="high"'], read_plugin=True)
    negative = probe(["-c", "codex_duo_unknown_config_sentinel=true"])
    result = {"valid": valid, "negative_unknown_key": negative,
              "note": "No thread/new, turn/start, model inference, plugin install, or hook trust request."}
    (ROOT / "evidence/current").mkdir(parents=True, exist_ok=True)
    (ROOT / "evidence/current/native-probe.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
