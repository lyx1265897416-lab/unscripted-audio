#!/bin/zsh
# 把 app/ 同步到 docs/（GitHub Pages 从 docs/ 发布）并推送；docs/relay.json 由 relay_sync.py 管，不覆盖
set -e
cd "$(dirname "$0")"
rsync -a --delete --exclude relay.json --exclude '*.bak*' app/ docs/
git add -A
git commit -m "${1:-更新}

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" || true
git -c credential.helper= -c credential.helper='!gh auth git-credential' push https://github.com/lyx1265897416-lab/unscripted-audio.git main
