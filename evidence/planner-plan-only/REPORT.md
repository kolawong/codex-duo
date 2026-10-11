# Plan-only implementation validation

Date: 2026-10-11. Base: `b695221b36b1586f282fc4526f5d20ecd2b1f6e3`.
Branch: `feat/readonly-plan-only`.

## Implemented

- Independent explicit Planner request/result lifecycle and immutable code/model snapshots.
- Durable shared Planner budget; failed launches count; one active reservation; restart safety.
- Baseline/content-hash revalidation, duplicate completion handling and stale-plan rejection.
- Fail-closed host capability-report validation; no Planner-to-Worker automatic transition.
- Official-format `fusion_planner` custom-agent companion and documented host adapter path.
- Opt-in Planner model/effort/budget settings in Swift, Web, MCP settings and CLI tooling.
- Legacy configuration and `selected_model` semantics retained; existing Worker path unchanged.

## Passed in Linux cloud, no model calls

- `python3 -B -m unittest discover -s tests -v`: 148 tests, 1 platform skip.
- `node native-build/build.mjs`: rebuilt the checked-in self-contained MCP panel.
- `node native-build/test-panel.mjs`: both HTTP and MCP controller behavior.
- `node native-build/test-panel.cjs`: 8 JSDOM interaction checks, including save/discard and no dispatch.
- `FUSION_CODEX_CLI=<strict catalog fixture> node native-build/test-client.mjs`:
  official MCP SDK transport and routing checks. The fixture permits only catalog/version reads.
- `python3 -B tools/validate_static.py --installed --global-config-sha256 <current cloud baseline>`:
  35 structural checks. No global config was changed. Default validation assumptions refer
  to another machine's historical configuration and are inapplicable in this cloud checkout.
- `git diff --check`.

Planner tests include real Git fixture repositories, settings snapshots, process restarts,
concurrent reservations, capability mismatch, failed model receipts, strict result schema,
MCP/CLI lifecycle routing, tracked/untracked/index/HEAD changes, ignored scoped files,
symlink/size/count/submodule bounds, tampered hashes and duplicate/conflicting results.

## Not verified / remaining acceptance

- No real model or native Planner was launched. Offline fixtures do not establish model
  provenance, account model access, effective sandbox enforcement or native role discovery.
- The native role must be used only when trusted host information establishes its effective
  read-only/no-escalation permissions and absent external/child-agent tools. A TOML file
  alone is insufficient because parent runtime overrides may win; unsupported hosts block.
- `swift test --package-path macos` and macOS app packaging were not run: Swift/macOS are
  unavailable here. Two added native model compatibility tests remain to be run on macOS.
- Real browser layout/screenshot verification was blocked by Chromium UNIX socket EPERM,
  including the permitted retry. DOM behavior checks passed but are not visual QA.
- Raw SDK execution without the fixture fails because this Linux machine does not contain
  the configured macOS bundled model-catalog CLI; this is not a model-runtime test.

See `plugins/fusion-minimal/skills/fusion/references/planner-host.md` for the concrete
supported-host dispatch procedure and the required fail-closed checks. Plans return to the
current chat for human review. Implementation requires separate explicit approval and a
fresh ordinary Worker task after code-baseline revalidation.
