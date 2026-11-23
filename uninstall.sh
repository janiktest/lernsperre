#!/usr/bin/env bash
# LernSperre entfernen. Einstellungen und Statistik bleiben erhalten
# (~/.config/lernsperre, ~/.local/share/lernsperre/state.db).
set -uo pipefail

UUID="lernsperre@janiktest.github.io"
gnome-extensions disable "$UUID" 2>/dev/null
rm -rf "$HOME/.local/share/gnome-shell/extensions/$UUID"
systemctl --user disable --now lernsperre.service 2>/dev/null
rm -f "$HOME/.config/systemd/user/lernsperre.service"
systemctl --user daemon-reload
rm -rf "$HOME/.local/share/lernsperre/app"
rm -f "$HOME/.local/bin/lernsperre"
echo "LernSperre entfernt. Einstellungen liegen weiter in ~/.config/lernsperre."
