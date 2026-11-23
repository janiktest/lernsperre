#!/usr/bin/env bash
# Baut dist/lernsperre_<version>_all.deb (braucht nur dpkg-deb).
set -euo pipefail
cd "$(dirname "$0")/.."
UUID="lernsperre@janiktest.github.io"
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' daemon/lernsperre/__init__.py)
ROOT=$(mktemp -d)
trap 'rm -rf "$ROOT"' EXIT

install -d "$ROOT/DEBIAN" "$ROOT/usr/lib/lernsperre" "$ROOT/usr/bin" \
    "$ROOT/usr/lib/systemd/user" "$ROOT/usr/share/gnome-shell/extensions/$UUID" \
    "$ROOT/usr/share/doc/lernsperre"

cp -r daemon/lernsperre "$ROOT/usr/lib/lernsperre/"
find "$ROOT" -name '__pycache__' -prune -exec rm -rf {} +

cat > "$ROOT/usr/bin/lernsperre" <<'SH'
#!/bin/sh
PYTHONPATH=/usr/lib/lernsperre exec /usr/bin/python3 -m lernsperre "$@"
SH
chmod 755 "$ROOT/usr/bin/lernsperre"

sed -e '/^Environment=PYTHONPATH=/d' -e 's|^ExecStart=.*$|ExecStart=/usr/bin/lernsperre run|' \
    systemd/lernsperre.service > "$ROOT/usr/lib/systemd/user/lernsperre.service"

cp gnome-extension/$UUID/* "$ROOT/usr/share/gnome-shell/extensions/$UUID/"
install -D -m 644 packaging/completions/lernsperre.bash "$ROOT/usr/share/bash-completion/completions/lernsperre"
install -D -m 644 packaging/completions/_lernsperre "$ROOT/usr/share/zsh/vendor-completions/_lernsperre"
cp README.md LICENSE CHANGELOG.md docs/ANLEITUNG.md "$ROOT/usr/share/doc/lernsperre/"

sed "s/@VERSION@/$VERSION/" packaging/debian/control.in > "$ROOT/DEBIAN/control"
install -m 755 packaging/debian/postinst packaging/debian/prerm "$ROOT/DEBIAN/"

find "$ROOT/usr" -type d -exec chmod 755 {} +
find "$ROOT/usr" -type f ! -path '*/usr/bin/*' -exec chmod 644 {} +

mkdir -p dist
OUT="dist/lernsperre_${VERSION}_all.deb"
dpkg-deb --root-owner-group --build "$ROOT" "$OUT" >/dev/null
echo "$OUT"
