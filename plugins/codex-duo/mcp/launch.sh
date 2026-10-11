#!/bin/sh
# Resolve the packaged entrypoint without external utilities or shell profiles.
set -eu
# The bundled Codex CLI wrapper also needs system utilities. This affects only
# this server and its children, never the user or host configuration.
PATH="${PATH:+$PATH:}/usr/bin:/bin:/usr/sbin:/sbin"
export PATH
codex_duo_dir=$(CDPATH= cd -P -- "${0%/*}" && pwd)
codex_duo_try_python() {
    codex_duo_candidate=$1
    shift
    [ -x "$codex_duo_candidate" ] || return 0
    if "$codex_duo_candidate" -B -c 'import sys; sys.exit(sys.version_info < (3, 11))' </dev/null 2>/dev/null; then
        exec "$codex_duo_candidate" -B "$codex_duo_dir/server.py" "$@"
    fi
}
codex_duo_path_python=$(command -v python3 2>/dev/null || :)
for codex_duo_python in "$codex_duo_path_python" /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    [ -n "$codex_duo_python" ] && [ -x "$codex_duo_python" ] || continue
    codex_duo_try_python "$codex_duo_python" "$@"
done
# Homebrew versioned formulae need not provide an unversioned python3. Preserve
# the original candidates above, then search versioned names without utilities,
# shell profiles, runtime installation, or changes to the caller's PATH.
codex_duo_python_paths="$PATH:/opt/homebrew/bin:/usr/local/bin"
while [ -n "$codex_duo_python_paths" ]; do
    codex_duo_python_dir=${codex_duo_python_paths%%:*}
    case "$codex_duo_python_paths" in
        *:*) codex_duo_python_paths=${codex_duo_python_paths#*:} ;;
        *) codex_duo_python_paths='' ;;
    esac
    [ -n "$codex_duo_python_dir" ] || continue
    for codex_duo_python in "$codex_duo_python_dir"/python3.[0-9]*; do
        codex_duo_minor=${codex_duo_python##*/python3.}
        case "$codex_duo_minor" in ''|*[!0-9]*) continue ;; esac
        codex_duo_try_python "$codex_duo_python" "$@"
    done
done
printf '%s\n' 'Codex Duo requires an existing Python 3.11+ (PATH, /opt/homebrew/bin, or /usr/local/bin). No runtime was installed.' >&2
exit 127
