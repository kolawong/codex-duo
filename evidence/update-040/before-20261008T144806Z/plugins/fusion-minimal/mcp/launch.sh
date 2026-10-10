#!/bin/sh
# Resolve the packaged entrypoint without external utilities or shell profiles.
set -eu
# The bundled Codex CLI wrapper also needs system utilities. This affects only
# this server and its children, never the user or host configuration.
PATH="${PATH:+$PATH:}/usr/bin:/bin:/usr/sbin:/sbin"
export PATH
fusion_dir=$(CDPATH= cd -P -- "${0%/*}" && pwd)
fusion_path_python=$(command -v python3 2>/dev/null || :)
for fusion_python in "$fusion_path_python" /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    [ -n "$fusion_python" ] && [ -x "$fusion_python" ] || continue
    if "$fusion_python" -B -c 'import sys; sys.exit(sys.version_info < (3, 11))' </dev/null 2>/dev/null; then
        exec "$fusion_python" -B "$fusion_dir/server.py" "$@"
    fi
done
printf '%s\n' 'Fusion requires an existing Python 3.11+ (PATH, /opt/homebrew/bin, or /usr/local/bin). No runtime was installed.' >&2
exit 127
