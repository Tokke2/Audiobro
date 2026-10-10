#!/usr/bin/env bash
# setup_github.sh — ställer in GitHub för nästa Arena-chatt
# Frågar Username/Repo + Token och fixar allt automatiskt
# Kör: chmod +x setup_github.sh && ./setup_github.sh
set -e

echo "=========================================="
echo " Audiobro — setup GitHub för Arena-chatt"
echo "=========================================="
echo ""

# Fråga Username/Repo
read -p "GitHub Username (t.ex. Tokke2): " GH_USER
read -p "Repo-namn (t.ex. Audiobro): " GH_REPO
if [[ -z "$GH_USER" || -z "$GH_REPO" ]]; then
  echo "Fel: Username och Repo måste fyllas i"
  exit 1
fi
GH_REMOTE="github.com/${GH_USER}/${GH_REPO}.git"

# Fråga Token (dolt)
echo ""
echo "Skapa token på: https://github.com/settings/tokens/new"
echo "  -> Tokens (classic) -> Generate -> bocka 'repo' -> kopiera github_pat_..."
echo ""
read -s -p "Klistra GitHub PAT (github_pat_...): " GH_TOKEN
echo ""
if [[ -z "$GH_TOKEN" ]]; then
  echo "Fel: Token tom"
  exit 1
fi
if [[ ! "$GH_TOKEN" =~ ^github_pat_ && ! "$GH_TOKEN" =~ ^ghp_ ]]; then
  echo "Varning: Token ser inte ut som github_pat_ / ghp_ — fortsätter ändå"
fi

# Spara token säkert
TOKEN_FILE="$HOME/.audiobro_github_token"
echo -n "$GH_TOKEN" > "$TOKEN_FILE"
chmod 600 "$TOKEN_FILE"
echo "✓ Token sparad till $TOKEN_FILE (600)"

# Krypterad backup om pass finns
if [[ -f "$HOME/.audiobro_token_pass" ]]; then
  PASS=$(cat "$HOME/.audiobro_token_pass")
  if command -v openssl >/dev/null 2>&1; then
    echo -n "$GH_TOKEN" | openssl enc -aes-256-cbc -salt -pbkdf2 -pass pass:"$PASS" -out "${TOKEN_FILE}.enc" 2>/dev/null && echo "✓ Krypterad backup: ${TOKEN_FILE}.enc"
  fi
fi

# Fråga git identity
echo ""
read -p "Git user.name [Audiobro Bot]: " GIT_NAME
GIT_NAME=${GIT_NAME:-"Audiobro Bot"}
read -p "Git user.email [bot@audiobro.local]: " GIT_EMAIL
GIT_EMAIL=${GIT_EMAIL:-"bot@audiobro.local"}
git config --global user.name "$GIT_NAME" 2>/dev/null || git config user.name "$GIT_NAME"
git config --global user.email "$GIT_EMAIL" 2>/dev/null || git config user.email "$GIT_EMAIL"
echo "✓ Git identity: $GIT_NAME <$GIT_EMAIL>"

# Sätt remote
echo ""
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Git-repo hittat i $(pwd)"
  if git remote get-url origin >/dev/null 2>&1; then
    echo "Byter origin -> https://oauth2:***@$GH_REMOTE"
    git remote set-url origin "https://oauth2:${GH_TOKEN}@${GH_REMOTE}"
  else
    echo "Lägger till origin -> $GH_REMOTE"
    git remote add origin "https://oauth2:${GH_TOKEN}@${GH_REMOTE}"
  fi
else
  echo "Inget git-repo här — klonar $GH_USER/$GH_REPO ..."
  read -p "Klona till /home/user/$GH_REPO ? [Y/n]: " DO_CLONE
  if [[ "$DO_CLONE" != "n" && "$DO_CLONE" != "N" ]]; then
    git clone "https://oauth2:${GH_TOKEN}@${GH_REMOTE}" "$HOME/$GH_REPO"
    echo "✓ Klonad till $HOME/$GH_REPO"
    echo "  cd $HOME/$GH_REPO och kör setup_github.sh igen om du vill ställa in remote där"
  else
    echo "Hoppar kloning — sätt remote manuellt senare med:"
    echo "  git remote add origin https://oauth2:\$(cat ~/.audiobro_github_token)@github.com/${GH_USER}/${GH_REPO}.git"
  fi
fi

# Testa koppling
echo ""
echo "Testar koppling..."
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if git ls-remote origin >/dev/null 2>&1; then
    echo "✓ Koppling OK — kan läsa från $GH_REMOTE"
    git fetch origin --dry-run 2>&1 | head -5
    echo ""
    echo "Klart! Testa push med:"
    echo "  touch test.txt && git add test.txt && git commit -m test && git push origin main"
    echo "  (ta bort test.txt sedan)"
  else
    echo "✗ Kunde inte nå $GH_REMOTE — kolla Username/Repo och att token har 'repo'-rättigheter"
    exit 1
  fi
else
  echo "Inget repo att testa — men token och remote är sparade för nästa kloning"
fi

echo ""
echo "=========================================="
echo " Klart! Nästa chatt kan nu pusha till"
echo " $GH_USER/$GH_REPO"
echo " Token: $TOKEN_FILE"
echo "=========================================="
