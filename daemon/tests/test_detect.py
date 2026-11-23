import os
import subprocess
import sys
from pathlib import Path

from lernsperre.anki import resolve_launch
from lernsperre.detect import set_options, toml_str
from lernsperre.config import DEFAULT_CONFIG, parse_config

DAEMON = Path(__file__).resolve().parents[1]


def _exe(path: Path, body: str = "#!/bin/sh\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    path.chmod(0o755)
    return path


def _fake_home(tmp_path: Path) -> dict:
    home = tmp_path / "home"
    bin_ = tmp_path / "bin"
    _exe(bin_ / "flatpak", "#!/bin/sh\nprintf 'net.ankiweb.Anki\\t25.09.2\\tsystem\\n'\n")
    _exe(bin_ / "snap", "#!/bin/sh\nprintf 'Name Version Rev\\nanki-woodrow 2.1.66 40\\n'\n")
    _exe(home / ".local/share/AnkiProgramFiles/.venv/bin/anki")
    _exe(home / "Applications/Anki-25.02.AppImage")
    (home / ".var/app/net.ankiweb.Anki/data/Anki2/Benutzer 1").mkdir(parents=True)
    (home / ".var/app/net.ankiweb.Anki/data/Anki2/Benutzer 1/collection.anki2").write_text("")
    (home / ".local/share/Anki2/Janik").mkdir(parents=True)
    (home / ".local/share/Anki2/Janik/collection.anki2").write_text("")
    (home / "snap/anki-woodrow/40/.local/share/Anki2/S").mkdir(parents=True)
    (home / "snap/anki-woodrow/40/.local/share/Anki2/S/collection.anki2").write_text("")
    env = dict(os.environ, HOME=str(home), PATH=f"{bin_}:/usr/bin:/bin", PYTHONPATH=str(DAEMON),
               XDG_CONFIG_HOME=str(home / ".config"), XDG_DATA_DIRS=str(tmp_path / "none"))
    return env


def _cli(env, *args):
    return subprocess.run([sys.executable, "-m", "lernsperre", *args], env=env,
                          capture_output=True, text=True, cwd=DAEMON, timeout=30)


def test_detect_ankis_lists_all_kinds(tmp_path):
    out = _cli(_fake_home(tmp_path), "detect-ankis").stdout
    assert "Flatpak: net.ankiweb.Anki 25.09.2 (system)" in out
    assert "flatpak run net.ankiweb.Anki" in out
    assert "Snap: anki-woodrow 2.1.66" in out and "snap run anki-woodrow" in out
    assert "Anki-Launcher (ankiweb.net)" in out
    assert "AppImage" in out
    assert "Profil „Benutzer 1“" in out and "Profil „Janik“" in out and "Profil „S“" in out


def test_use_anki_writes_config(tmp_path):
    env = _fake_home(tmp_path)
    res = _cli(env, "use-anki", "1")
    assert res.returncode == 0, res.stderr
    cfg_file = Path(env["XDG_CONFIG_HOME"]) / "lernsperre/config.toml"
    cfg = parse_config(cfg_file.read_text())
    assert cfg.anki_launch == "flatpak run net.ankiweb.Anki"
    assert cfg.anki_collection.endswith("Benutzer 1/collection.anki2")
    assert len(cfg.targets) == 6  # Ziele unverändert
    assert _cli(env, "use-anki", "99").returncode == 1


def test_set_options_keeps_targets_and_comments():
    text = set_options(DEFAULT_CONFIG, {"anki_launch": toml_str("/opt/anki/anki"), "neu": "1"})
    cfg = parse_config(text)
    assert cfg.anki_launch == "/opt/anki/anki" and len(cfg.targets) == 6
    assert "# Welches Anki gestartet wird" in text


def test_resolve_launch(tmp_path):
    assert resolve_launch("") == []
    assert resolve_launch("flatpak run net.ankiweb.Anki") == ["flatpak", "run", "net.ankiweb.Anki"]
    exe = _exe(tmp_path / "anki-dir/bin/anki")
    assert resolve_launch(str(tmp_path / "anki-dir")) == [str(exe)]
    img = _exe(tmp_path / "imgs/Anki.AppImage")
    assert resolve_launch(str(tmp_path / "imgs")) == [str(img)]
    import pytest
    (tmp_path / "leer").mkdir()
    with pytest.raises(ValueError):
        resolve_launch(str(tmp_path / "leer"))


def test_reset_config_with_backup(tmp_path):
    env = _fake_home(tmp_path)
    cfg_file = Path(env["XDG_CONFIG_HOME"]) / "lernsperre/config.toml"
    cfg_file.parent.mkdir(parents=True)
    old = (DAEMON / "tests/old_config_0_2_0.toml").read_text().replace("allowed_minutes = 20", "allowed_minutes = 35")
    cfg_file.write_text(old)
    res = _cli(env, "reset-config", "--behalten")
    assert res.returncode == 0, res.stderr
    assert parse_config(cfg_file.read_text()).allowed_minutes == 35
    assert "unlock_mode" not in cfg_file.read_text()
    backups = list(cfg_file.parent.glob("config.toml.bak-*"))
    assert len(backups) == 1 and backups[0].read_text() == old
    assert _cli(env, "reset-config").returncode == 0
    assert cfg_file.read_text() == DEFAULT_CONFIG


def test_fresh_config_keeps_values_and_targets():
    from lernsperre.config import fresh_config
    old = DEFAULT_CONFIG.replace("icon_free = \"⏳\"", "icon_free = \"🎬\"") + '\n[[targets]]\nname = "Twitch"\ntitles = ["Twitch"]\n'
    cfg = parse_config(fresh_config(old))
    assert cfg.icon_free == "🎬" and cfg.targets[-1].name == "Twitch" and len(cfg.targets) == 7
    assert parse_config(fresh_config(DEFAULT_CONFIG)).unlock_mode == "time"
