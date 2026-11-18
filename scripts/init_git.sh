#!/usr/bin/env bash
# Initializes a local Git repository and optionally pushes it to a remote.
#
# Usage:
#   ./scripts/init_git.sh
#   ./scripts/init_git.sh https://github.com/<user>/<repo>.git
#
# Create an EMPTY remote repository first (no README/license).

set -euo pipefail

REMOTE_URL="${1:-}"
BRANCH="${BRANCH:-main}"
MESSAGE="${MESSAGE:-Initial commit: Telegram Mini App + aiogram marketplace MVP}"

fail() {
  echo "ERROR: $1" >&2
  exit 1
}

command -v git >/dev/null 2>&1 || fail "git was not found in PATH"

[ -f "app/main.py" ] && [ -f "pyproject.toml" ] \
  || fail "Run this script from the project root (the folder that contains app/ and pyproject.toml)."

if [ ! -d ".git" ]; then
  echo "Initializing Git repository in $(pwd)..."
  git init >/dev/null
  git symbolic-ref HEAD "refs/heads/$BRANCH"
else
  echo "Git repository already exists."
fi

if [ -z "$(git config user.email || true)" ]; then
  fail 'Set your Git identity first: git config --global user.name "Your Name"; git config --global user.email "you@example.com"'
fi

if [ -f ".env" ]; then
  echo "WARNING: .env exists but is ignored by .gitignore and will not be committed."
fi

git add --all

LEAKED="$(git ls-files '.env' '.env.*' | grep -v '^\.env\.example$' || true)"
if [ -n "$LEAKED" ]; then
  fail "A real environment file is staged: $LEAKED. Remove it with: git rm --cached <file>"
fi

if git diff --cached --quiet; then
  echo "Nothing to commit."
else
  git commit -m "$MESSAGE"
fi

if [ -n "$REMOTE_URL" ]; then
  if git remote | grep -qx "origin"; then
    git remote set-url origin "$REMOTE_URL"
  else
    git remote add origin "$REMOTE_URL"
  fi
  echo "Pushing branch '$BRANCH' to $REMOTE_URL ..."
  git push -u origin "$BRANCH"
  echo "Done. Repository is available at $REMOTE_URL"
else
  cat <<EOF

Local repository is ready. To publish it:
  1. Create an EMPTY repository on GitHub/GitLab (without README/license).
  2. git remote add origin https://github.com/<user>/<repo>.git
  3. git push -u origin $BRANCH

Or rerun this script with the URL:
  ./scripts/init_git.sh https://github.com/<user>/<repo>.git
EOF
fi
