#!/usr/bin/env bash
# One-shot release script for ecosystem-wide changes.
#
# Usage:
#   ./scripts/release.sh "Remove variable keyword"
#   ./scripts/release.sh "Remove variable keyword" --push
#
# Steps:
#   1. Run rac tests
#   2. Validate all statute repos parse
#   3. Commit changes across all repos
#   4. Optionally push and deploy website
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RAC_DIR="$ROOT/rac"
MSG="${1:?Usage: release.sh \"commit message\" [--push]}"
PUSH="${2:-}"

REPOS=(rac-us rac-us-ny rac-us-tx rac-us-ca rac-ca rac-syntax rac-compile)

echo "=== Step 1: Run rac tests ==="
cd "$RAC_DIR"
PYTHONPATH=src python -m pytest tests/ -q || { echo "FAIL: tests"; exit 1; }
echo

echo "=== Step 2: Validate all statute repos ==="
python scripts/validate_all.py || { echo "FAIL: cross-repo validation"; exit 1; }
echo

echo "=== Step 3: Commit changes ==="
# Commit rac itself
cd "$RAC_DIR"
if ! git diff --quiet --cached || ! git diff --quiet; then
    git add -A
    git commit -m "$MSG

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
    echo "  rac: committed"
else
    echo "  rac: clean"
fi

# Commit statute repos
for repo in "${REPOS[@]}"; do
    REPO_DIR="$ROOT/$repo"
    if [ ! -d "$REPO_DIR" ]; then
        echo "  $repo: not found, skipping"
        continue
    fi
    cd "$REPO_DIR"
    if ! git diff --quiet --cached || ! git diff --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
        git add -A
        git commit -m "$MSG

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
        echo "  $repo: committed"
    else
        echo "  $repo: clean"
    fi
done

# Commit website
SITE_DIR="$ROOT/rules.foundation"
if [ -d "$SITE_DIR" ]; then
    cd "$SITE_DIR"
    if ! git diff --quiet --cached || ! git diff --quiet; then
        git add -A
        git commit -m "$MSG

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
        echo "  rules.foundation: committed"
    else
        echo "  rules.foundation: clean"
    fi
fi
echo

if [ "$PUSH" = "--push" ]; then
    echo "=== Step 4: Push all repos ==="
    cd "$RAC_DIR"
    BRANCH=$(git branch --show-current)
    git push origin "$BRANCH" 2>&1 && echo "  rac: pushed" || echo "  rac: push failed"

    for repo in "${REPOS[@]}"; do
        REPO_DIR="$ROOT/$repo"
        [ ! -d "$REPO_DIR" ] && continue
        cd "$REPO_DIR"
        BRANCH=$(git branch --show-current)
        # Try origin first, fall back to other remotes
        git push origin "$BRANCH" 2>&1 && echo "  $repo: pushed" || {
            REMOTE=$(git remote | head -1)
            git push "$REMOTE" "$BRANCH" 2>&1 && echo "  $repo: pushed ($REMOTE)" || echo "  $repo: push failed"
        }
    done

    if [ -d "$SITE_DIR" ]; then
        cd "$SITE_DIR"
        BRANCH=$(git branch --show-current)
        git push origin "$BRANCH" 2>&1 && echo "  rules.foundation: pushed"

        echo
        echo "=== Step 5: Deploy website ==="
        bunx vercel --prod 2>&1 | tail -5
    fi
else
    echo "Dry run — pass --push to push and deploy."
fi

echo
echo "Done."
