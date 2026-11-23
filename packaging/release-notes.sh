#!/usr/bin/env bash
# Gibt den CHANGELOG-Abschnitt einer Version aus (für die Release-Beschreibung).
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="$1"
DEB="$2"
awk -v v="## $VERSION " 'index($0, v) == 1 {on=1; next} /^## / && on {exit} on' CHANGELOG.md
cat <<EOT

---

**Installieren / Updaten:** \`$DEB\` herunterladen und

\`\`\`bash
sudo apt install ./Downloads/$DEB
\`\`\`

Anleitung: https://github.com/janiktest/lernsperre/blob/main/docs/ANLEITUNG.md
EOT
