#!/usr/bin/env bash
# LernSperre installieren (nur für den aktuellen Benutzer, kein sudo nötig).
set -euo pipefail

cd "$(dirname "$0")"
UUID="lernsperre@janiktest.github.io"
APP_DIR="$HOME/.local/share/lernsperre/app"
EXT_DIR="$HOME/.local/share/gnome-shell/extensions/$UUID"
UNIT_DIR="$HOME/.config/systemd/user"
BIN_DIR="$HOME/.local/bin"

echo "==> Prüfe Voraussetzungen"
if ! /usr/bin/python3 -c 'import gi; gi.require_version("Gio", "2.0"); from gi.repository import Gio' 2>/dev/null; then
    echo "python3-gi fehlt. Bitte installieren: sudo apt install python3-gi" >&2
    exit 1
fi
if ! flatpak info net.ankiweb.Anki >/dev/null 2>&1; then
    echo "Hinweis: Anki als Flatpak (net.ankiweb.Anki) nicht gefunden. LernSperre sucht trotzdem auch ~/.local/share/Anki2."
fi

echo "==> Dienst nach $APP_DIR"
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR"
cp -r daemon/lernsperre "$APP_DIR/"
find "$APP_DIR" -name '__pycache__' -prune -exec rm -rf {} +

echo "==> Befehl lernsperre nach $BIN_DIR"
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/lernsperre" <<EOF
#!/bin/sh
PYTHONPATH="$APP_DIR" exec /usr/bin/python3 -m lernsperre "\$@"
EOF
chmod +x "$BIN_DIR/lernsperre"

echo "==> Tab-Vervollständigung"
install -D -m 644 packaging/completions/lernsperre.bash "$HOME/.local/share/bash-completion/completions/lernsperre"

echo "==> Einstellungen anlegen (falls noch nicht vorhanden)"
PYTHONPATH="$APP_DIR" /usr/bin/python3 -m lernsperre config

echo "==> systemd-User-Dienst mit Autostart"
mkdir -p "$UNIT_DIR"
cp systemd/lernsperre.service "$UNIT_DIR/"
systemctl --user daemon-reload
systemctl --user enable lernsperre.service
systemctl --user restart lernsperre.service

echo "==> GNOME-Erweiterung nach $EXT_DIR"
rm -rf "$EXT_DIR"
mkdir -p "$EXT_DIR"
cp gnome-extension/$UUID/* "$EXT_DIR/"
if gnome-extensions enable "$UUID" 2>/dev/null; then
    echo "Erweiterung aktiviert."
else
    echo "GNOME kennt die neue Erweiterung erst nach einer Neuanmeldung (Wayland)."
    echo "Bitte ab- und wieder anmelden und dann ausführen: gnome-extensions enable $UUID"
fi

cat <<EOF

Fertig. LernSperre läuft im Hintergrund.
  Zustand:       lernsperre status
  Einstellungen: $(PYTHONPATH="$APP_DIR" /usr/bin/python3 -m lernsperre config)  (danach: lernsperre reload)
  Sperre testen: lernsperre lock
  Notfall:       lernsperre reset   (z. B. aus einer Konsole mit Strg+Alt+F3)

LernSperre ist ein unabhängiges Projekt und nicht mit Anki oder Ankitects verbunden.
EOF
