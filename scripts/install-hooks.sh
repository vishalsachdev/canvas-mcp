#!/usr/bin/env bash
# Point git at the repo's tracked hooks directory.
#
# `core.hooksPath` is per-clone local config, so every contributor runs this
# once. It is deliberately not automatic: silently installing executables that
# run on someone's commits is not something a `pip install` should do.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
git -C "$repo_root" config core.hooksPath .githooks
chmod +x "$repo_root"/.githooks/*

echo "✓ core.hooksPath -> .githooks"
echo "  Installed: $(cd "$repo_root/.githooks" && ls | tr '\n' ' ')"
echo
echo "  To uninstall: git config --unset core.hooksPath"
