#!/usr/bin/env python3
"""Validate the minimal package and companion config, without executing models."""
import hashlib
import os
import argparse
import json
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/codex-duo"


def validate_stdio_command(command, plugin_root):
    """Codex portable command rules; the SDK alone does not validate these."""
    if not isinstance(command, str) or not command or '\\' in command:
        raise ValueError('invalid portable stdio command')
    if '/' not in command:
        return
    relative = Path(command)
    if not command.startswith('./') or '..' in relative.parts:
        raise ValueError('stdio command must be a bare executable or contained ./ path')
    root = Path(plugin_root).resolve()
    target = root / relative
    if not target.resolve().is_relative_to(root) or not target.is_file():
        raise ValueError('stdio command escapes the plugin or is missing')
    if not os.access(target, os.X_OK):
        raise ValueError('stdio launcher must be executable')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installed', action='store_true', help='Expect the approved plugin to be enabled')
    parser.add_argument('--global-config-sha256', help='Explicit pre-change hash for this authorized update')
    args = parser.parse_args()
    checks = []
    def check(condition, message):
        if not condition:
            raise ValueError(message)
        checks.append(message)

    manifest = json.loads((PLUGIN / "plugin.json").read_text())
    overlay = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text())
    check(manifest["name"] == PLUGIN.name == overlay["name"], "plugin identity matches")
    check(bool(re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"])), "semantic version")
    check(all(manifest[k] == overlay[k] for k in ["name", "version", "description"]),
          "portable and compatibility identity synchronized")
    interface = manifest["extensions"]["com.openai"]["interface"]
    check(interface == overlay["interface"], "presentation synchronized")
    check(len(interface["shortDescription"]) <= 30, "subtitle at most 30 characters")
    check(len(interface["defaultPrompt"]) <= 128, "default prompt accepted by native host")
    check(not any(k in manifest for k in ["skills", "interface", "mcpServers", "apps"]),
          "portable manifest avoids compatibility-only fields")
    check(overlay["skills"] == "./skills/", "compatibility skill root")
    skill = PLUGIN / "skills/codex-duo/SKILL.md"
    parts = skill.read_text().split("---", 2)
    frontmatter = dict(line.split(":", 1) for line in parts[1].strip().splitlines())
    check(frontmatter.get("name", "").strip() == skill.parent.name, "skill name matches folder")
    check(bool(frontmatter.get("description", "").strip()), "skill has trigger description")
    for path in ["../workflow/references/contract.md", "../workflow/templates/task.json", "../workflow/scripts/codex_duo.py"]:
        check((skill.parent / path).is_file(), "skill resource exists: " + path)
    config = tomllib.loads((ROOT / ".codex/config.toml").read_text())
    agent = tomllib.loads((ROOT / ".codex/agents/codex_duo_worker.toml").read_text())
    check("model" not in config and "model_reasoning_effort" not in config,
          "project config cannot override the user-selected chat model or effort")
    check(all(isinstance(agent.get(k), str) and agent[k] for k in [
        "name", "description", "developer_instructions"]), "custom agent required fields")
    check(agent["name"] == "codex_duo_worker", "custom agent name matches filename")
    check(config["agents"]["enabled"] is True, "native worker capability enabled for authorized tasks")
    check("model" not in agent and "model_reasoning_effort" not in agent, "companion agent cannot override saved worker settings")
    check(config["agents"]["max_concurrent_threads_per_session"] == 1, "one worker limit prepared")
    check(config["plugins"]["codex-duo@codex-duo-local"]["enabled"] is args.installed,
          "plugin enablement matches requested validation mode")
    check(config["features"]["hooks"] is False, "project hooks disabled")
    market = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
    check(market["name"] == "codex-duo-local", "marketplace name matches enable key")
    entry = market["plugins"][0]
    check((ROOT / entry["source"]["path"]).resolve() == PLUGIN, "marketplace source resolves")
    check(not any(p.is_symlink() for p in PLUGIN.rglob("*")), "package has no symlinks")
    check(not any(p.name in ["hooks.json", ".app.json"] for p in PLUGIN.rglob("*")),
          "no Hooks or hosted app dependency")
    mcp = json.loads((PLUGIN / 'mcp.json').read_text())['mcpServers']['codex-duo']
    legacy = json.loads((PLUGIN / '.mcp.json').read_text())['mcpServers']['codex-duo']
    check(mcp['type'] == 'stdio' and 'url' not in mcp, 'MCP uses local stdio without a network listener')
    validate_stdio_command(mcp['command'], PLUGIN)
    check(True, 'portable stdio command satisfies executable/path rules')
    check({k: v for k, v in mcp.items() if k != 'type'} == legacy, 'MCP compatibility command synchronized')
    check(overlay['mcpServers'] == './.mcp.json', 'compatibility MCP reference resolves')
    check(mcp['command'] == './mcp/launch.sh' and mcp['args'] == ['--project-root', '${PLUGIN_ROOT}'],
          'MCP startup root exists in the installed plugin; tools use explicit chat project roots')
    check((PLUGIN / 'mcp/server.py').is_file() and (PLUGIN / 'ui/model-desk.html').is_file(),
          'packaged MCP entrypoint and built view exist')
    version = re.search(r"^VERSION = '([^']+)'", (PLUGIN / 'mcp/server.py').read_text(), re.M)
    check(version is not None and version.group(1) == manifest['version'], 'MCP server version matches package')
    check('src="/app.js"' not in (PLUGIN / 'ui/model-desk.html').read_text(), 'MCP view is self contained')
    baseline = json.loads((ROOT / "evidence/local-capabilities.json").read_text())
    after = hashlib.sha256((Path.home() / '.codex/config.toml').read_bytes()).hexdigest()
    expected_hash = args.global_config_sha256 or baseline["global_config_sha256_before"]
    check(bool(re.fullmatch(r'[0-9a-f]{64}', expected_hash)), 'valid explicit or historical configuration baseline')
    check(after == expected_hash, "global config hash unchanged from selected baseline")
    result = {"status": "passed", "check_count": len(checks), "checks": checks,
              "model_calls": 0, "global_config_sha256_after": after,
              "limitations": ["Structural checks; not the full Agent Plugins schema validator.",
                              "Named custom agent auto-discovery and independent model allocation telemetry remain unverified."]}
    (ROOT / "evidence/current").mkdir(parents=True, exist_ok=True)
    (ROOT / "evidence/current/static-validation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
