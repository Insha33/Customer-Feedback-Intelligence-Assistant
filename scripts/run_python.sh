#!/bin/sh

if command -v uv >/dev/null 2>&1; then
  uv_path="$(command -v uv)"
elif [ -n "${HOME:-}" ] && [ -x "${HOME}/.local/bin/uv" ]; then
  uv_path="${HOME}/.local/bin/uv"
elif [ -n "${HOME:-}" ] && [ -x "${HOME}/.cargo/bin/uv" ]; then
  uv_path="${HOME}/.cargo/bin/uv"
else
  printf '%s\n' \
    'Error: uv is required but was not found.' \
    'Install it with: brew install uv' \
    'Official alternatives: https://docs.astral.sh/uv/getting-started/installation/' >&2
  exit 127
fi

exec "${uv_path}" run python "$@"
