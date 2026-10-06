#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_dir"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Repository has modified or staged changes; refusing to update: $repo_dir" >&2
  exit 2
fi

unexpected_untracked="$(git status --porcelain | awk '$1 == "??" && $2 != "update-repo.sh" {print}')"
if [[ -n "$unexpected_untracked" ]]; then
  echo "Repository has untracked files; refusing to update: $repo_dir" >&2
  printf '%s\n' "$unexpected_untracked" >&2
  exit 2
fi

git fetch --prune upstream
git pull --ff-only upstream master
git push origin master
echo "Synchronized $(git rev-parse --short HEAD) at $(date -Is)"
