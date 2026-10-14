#!/bin/bash
set -euo pipefail
MACOS_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$MACOS_DIR/.." && pwd)"
APP="$MACOS_DIR/dist/Codex Duo.app"
python3 -B "$MACOS_DIR/generate-icons.py"
swift build --package-path "$MACOS_DIR" -c release
BIN_DIR="$(swift build --package-path "$MACOS_DIR" -c release --show-bin-path)"
# Generated bundle only: rebuilding must not retain an old executable/resources.
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/workflow/scripts" "$APP/Contents/Resources/workflow/templates" "$APP/Contents/Resources/workflow/references"
cp "$BIN_DIR/CodexDuoMenu" "$APP/Contents/MacOS/CodexDuoMenu"
cp "$MACOS_DIR/Sources/CodexDuoMenu/Resources/bridge.py" "$APP/Contents/Resources/bridge.py"
rm -rf "$APP/Contents/Resources/Brand"
cp -R "$MACOS_DIR/Sources/CodexDuoMenu/Resources/Brand" "$APP/Contents/Resources/Brand"
# Generated from the exact SVG used by the title header; never use a stale ICNS.
cp "$MACOS_DIR/Assets/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"
for name in codex_duo.py codex_duo_selection.py codex_duo_service.py codex_duo_projects.py codex_duo_defaults.py codex_duo_parallel.py codex_duo_planner.py codex_duo_planner_session.py codex_duo_migration.py codex_duo_completion.py codex_duo_worker.py; do
    cp "$PROJECT_ROOT/plugins/codex-duo/skills/workflow/scripts/$name" "$APP/Contents/Resources/workflow/scripts/$name"
done
cp "$PROJECT_ROOT/plugins/codex-duo/skills/workflow/templates/task.json" "$APP/Contents/Resources/workflow/templates/task.json"
cp "$PROJECT_ROOT/plugins/codex-duo/skills/workflow/templates/codex_duo_planner.toml" "$APP/Contents/Resources/workflow/templates/codex_duo_planner.toml"
cp "$PROJECT_ROOT/plugins/codex-duo/skills/workflow/references/planner-host.md" "$APP/Contents/Resources/workflow/references/planner-host.md"
# Also ship SwiftPM's resource bundle so Bundle.module works in packaged builds.
for resource in "$BIN_DIR"/*.bundle; do
    if [ -d "$resource" ]; then cp -R "$resource" "$APP/Contents/Resources/"; fi
done
PLIST="$APP/Contents/Info.plist"
cat > "$PLIST" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict/></plist>
PLIST
/usr/libexec/PlistBuddy -c 'Add :CFBundleIdentifier string io.kola.codex-duo.menu' "$PLIST"
/usr/libexec/PlistBuddy -c 'Add :CFBundleName string Codex Duo' "$PLIST"
/usr/libexec/PlistBuddy -c 'Add :CFBundleDisplayName string Codex Duo' "$PLIST"
/usr/libexec/PlistBuddy -c 'Add :CFBundleExecutable string CodexDuoMenu' "$PLIST"
/usr/libexec/PlistBuddy -c 'Add :CFBundlePackageType string APPL' "$PLIST"
/usr/libexec/PlistBuddy -c 'Add :CFBundleIconFile string AppIcon' "$PLIST"
/usr/libexec/PlistBuddy -c 'Add :CFBundleShortVersionString string 0.10.0' "$PLIST"
/usr/libexec/PlistBuddy -c 'Add :CFBundleVersion string 17' "$PLIST"
/usr/libexec/PlistBuddy -c 'Add :LSMinimumSystemVersion string 14.0' "$PLIST"
/usr/libexec/PlistBuddy -c 'Add :LSUIElement bool true' "$PLIST"
/usr/libexec/PlistBuddy -c 'Add :NSHighResolutionCapable bool true' "$PLIST"
# plutil receives the project path as one argument (including spaces or quotes).
/usr/bin/plutil -insert CodexDuoProjectRoot -string "$PROJECT_ROOT" "$PLIST"
/usr/bin/codesign --force --deep --sign - "$APP"
printf 'Built: %s\n' "$APP"
