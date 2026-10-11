#!/bin/bash
set -euo pipefail
MACOS_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$MACOS_DIR/.." && pwd)"
APP="$MACOS_DIR/dist/Codex Duo.app"
swift build --package-path "$MACOS_DIR" -c release
BIN_DIR="$(swift build --package-path "$MACOS_DIR" -c release --show-bin-path)"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/fusion/scripts" "$APP/Contents/Resources/fusion/templates" "$APP/Contents/Resources/fusion/references"
cp "$BIN_DIR/FusionMenu" "$APP/Contents/MacOS/FusionMenu"
cp "$MACOS_DIR/Sources/FusionMenu/Resources/bridge.py" "$APP/Contents/Resources/bridge.py"
rm -rf "$APP/Contents/Resources/Brand"
cp -R "$MACOS_DIR/Sources/FusionMenu/Resources/Brand" "$APP/Contents/Resources/Brand"
# Regenerate from Brand/AppIcon.svg with rsvg-convert + iconutil when the artwork changes.
cp "$MACOS_DIR/Assets/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"
for name in fusion.py fusion_selection.py fusion_service.py fusion_projects.py fusion_defaults.py fusion_parallel.py fusion_planner.py; do
    cp "$PROJECT_ROOT/plugins/fusion-minimal/skills/fusion/scripts/$name" "$APP/Contents/Resources/fusion/scripts/$name"
done
cp "$PROJECT_ROOT/plugins/fusion-minimal/skills/fusion/templates/task.json" "$APP/Contents/Resources/fusion/templates/task.json"
cp "$PROJECT_ROOT/plugins/fusion-minimal/skills/fusion/templates/fusion_planner.toml" "$APP/Contents/Resources/fusion/templates/fusion_planner.toml"
cp "$PROJECT_ROOT/plugins/fusion-minimal/skills/fusion/references/planner-host.md" "$APP/Contents/Resources/fusion/references/planner-host.md"
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
/usr/libexec/PlistBuddy -c 'Add :CFBundleIdentifier string io.kola.fusion.menu' "$PLIST"
/usr/libexec/PlistBuddy -c 'Add :CFBundleName string Codex Duo' "$PLIST"
/usr/libexec/PlistBuddy -c 'Add :CFBundleDisplayName string Codex Duo' "$PLIST"
/usr/libexec/PlistBuddy -c 'Add :CFBundleExecutable string FusionMenu' "$PLIST"
/usr/libexec/PlistBuddy -c 'Add :CFBundlePackageType string APPL' "$PLIST"
/usr/libexec/PlistBuddy -c 'Add :CFBundleIconFile string AppIcon' "$PLIST"
/usr/libexec/PlistBuddy -c 'Add :CFBundleShortVersionString string 0.7.0' "$PLIST"
/usr/libexec/PlistBuddy -c 'Add :CFBundleVersion string 7' "$PLIST"
/usr/libexec/PlistBuddy -c 'Add :LSMinimumSystemVersion string 14.0' "$PLIST"
/usr/libexec/PlistBuddy -c 'Add :LSUIElement bool true' "$PLIST"
/usr/libexec/PlistBuddy -c 'Add :NSHighResolutionCapable bool true' "$PLIST"
# plutil receives the project path as one argument (including spaces or quotes).
/usr/bin/plutil -insert FusionProjectRoot -string "$PROJECT_ROOT" "$PLIST"
/usr/bin/codesign --force --deep --sign - "$APP"
printf 'Built: %s\n' "$APP"
