import sqlite3
import time

from lernsperre.anki import AnkiActivity
from lernsperre.config import DEFAULT_CONFIG, parse_config
from lernsperre.engine import Engine, Signals, detect_activity
from lernsperre.matcher import Player, Window, title_matches, url_matches

CFG = parse_config(DEFAULT_CONFIG)

FF_YT = Window(title="Katzen – YouTube — Mozilla Firefox", app_id="firefox_firefox", focused=True)
FF_DOC = Window(title="Python docs — Mozilla Firefox", app_id="firefox_firefox", focused=True)
ANKI = Window(title="Benutzer 1 - Anki", app_id="net.ankiweb.Anki", wm_class="anki", focused=True)
TERM = Window(title="Terminal", app_id="org.gnome.Ptyxis", focused=True)


def run(engine, sig, seconds, start=1000.0, last_answer_fn=None):
    events = []
    for i in range(int(seconds)):
        now = start + i
        if last_answer_fn:
            sig.last_answer = last_answer_fn(now)
        events += engine.tick(now, 1.0, sig)
    return events


def test_default_targets():
    names = [t.name for t in CFG.targets]
    assert names == ["YouTube", "Instagram", "TikTok", "Netflix", "Reddit", "X/Twitter"]
    assert CFG.allowed_minutes == 20 and CFG.learn_minutes == 5


def test_title_and_url_matching():
    assert title_matches("Startseite / X — Mozilla Firefox", ["re:/ X( [—-] |$)"])
    assert not title_matches("Ordner / Xylophon", ["re:/ X( [—-] |$)"])
    assert url_matches("https://www.youtube.com/watch?v=1", ["youtube.com"])
    assert not url_matches("https://notyoutube.com/", ["youtube.com"])


def test_counts_only_when_target_in_front():
    e = Engine(CFG)
    run(e, Signals(windows=[FF_DOC]), 30)
    assert e.state.used == 0
    run(e, Signals(windows=[FF_YT]), 30)
    assert e.state.used == 30


def test_background_playback_counts():
    yt_bg = Window(title="Musik – YouTube — Mozilla Firefox", app_id="firefox_firefox")
    ff = Player("org.mpris.MediaPlayer2.firefox.instance_1_2", playing=True, desktop_entry="firefox", title="Musik")
    sig = Signals(windows=[TERM, yt_bg], players=[ff])
    act = detect_activity(CFG, sig)
    assert act.target == "YouTube" and act.reason == "Wiedergabe im Hintergrund"
    ff.playing = False
    assert detect_activity(CFG, sig).target is None


def test_warn_then_lock():
    e = Engine(CFG)
    events = run(e, Signals(windows=[FF_YT]), 20 * 60)
    kinds = [ev[0] for ev in events]
    assert kinds.count("warn") == 1 and kinds[-1] == "locked"
    assert e.state.mode == "locked"


def test_learning_only_counts_in_anki_with_recent_answers():
    e = Engine(CFG)
    e.lock(1000.0)
    # Anki vorne, aber noch keine Antwort seit der Sperre -> zählt nicht
    run(e, Signals(windows=[ANKI], last_answer=900.0), 30, start=1000)
    assert e.state.learned == 0
    # Antworten alle 10 s -> zählt
    run(e, Signals(windows=[ANKI]), 60, start=1100, last_answer_fn=lambda now: now - (now % 10))
    assert e.state.learned == 60
    # Anki offen, aber 2 min keine Antwort -> zählt nach idle_seconds nicht mehr
    run(e, Signals(windows=[ANKI], last_answer=1159.0), 120, start=1160)
    assert e.state.learned == 60 + 60
    # Anderes Fenster vorne -> zählt nicht
    run(e, Signals(windows=[TERM]), 30, start=1300, last_answer_fn=lambda now: now)
    assert e.state.learned == 120


def test_unlock_after_learn_time_resets_counter():
    e = Engine(CFG)
    run(e, Signals(windows=[FF_YT]), 20 * 60)
    events = run(e, Signals(windows=[ANKI]), 5 * 60 + 5, start=5000, last_answer_fn=lambda now: now)
    assert ("unlocked",) in events
    assert e.state.mode == "free" and e.state.used == 0 and not e.state.warned


def test_media_paused_while_locked():
    e = Engine(CFG)
    e.lock(0)
    ff = Player("org.mpris.MediaPlayer2.firefox", playing=True)
    assert ("pause_media",) in e.tick(1, 1, Signals(windows=[FF_YT], players=[ff]))


def test_big_time_jump_not_counted():
    e = Engine(CFG)
    e.tick(0, 3600, Signals(windows=[FF_YT]))
    assert e.state.used == 0


def test_anki_activity_reads_revlog(tmp_path):
    prof = tmp_path / "Benutzer 1"
    prof.mkdir()
    db = prof / "collection.anki2"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE revlog (id INTEGER PRIMARY KEY, cid INTEGER)")
    con.commit()
    act = AnkiActivity(search_dirs=[tmp_path])
    assert act.last_answer(time.time()) is None
    t = time.time()
    con.execute("INSERT INTO revlog VALUES (?, 1)", (int(t * 1000),))
    con.commit()
    assert abs(act.last_answer(time.time()) - t) < 0.01
    assert act.path == db


def cfg_with(**kw):
    import dataclasses
    return dataclasses.replace(parse_config(DEFAULT_CONFIG), **kw)


def test_pause_stops_counting_and_ends():
    e = Engine(CFG)
    assert e.pause(1000, 1) == [("paused", 1)]
    run(e, Signals(windows=[FF_YT]), 30, start=1000)
    assert e.state.used == 0 and e.snapshot()["paused"]
    events = run(e, Signals(windows=[FF_YT]), 40, start=1030)
    assert ("resumed",) in events and e.state.used > 0


def test_no_pause_while_locked_and_lock_clears_pause():
    e = Engine(CFG)
    e.pause(0, 30)
    e.lock(10)
    assert e.state.paused_until == 0
    assert e.pause(20, 15) == []


def test_cards_mode_unlocks_by_card_count_without_time():
    e = Engine(cfg_with(learn_minutes=None, min_cards=3))
    e.lock(0)
    e.tick(1, 1, Signals(windows=[TERM], cards_since_lock=2))
    assert e.state.mode == "locked"
    assert e.tick(2, 1, Signals(windows=[TERM], cards_since_lock=3)) == [("unlocked",)]


def test_both_mode_needs_time_and_cards():
    e = Engine(cfg_with(min_cards=2, learn_minutes=1))
    e.lock(0)
    run(e, Signals(windows=[ANKI], cards_since_lock=5), 30, start=1, last_answer_fn=lambda n: n)
    assert e.state.mode == "locked"  # Karten reichen, Zeit noch nicht
    events = run(e, Signals(windows=[ANKI], cards_since_lock=5), 40, start=31, last_answer_fn=lambda n: n)
    assert ("unlocked",) in events


def test_unlock_mode_follows_uncommented_options():
    assert parse_config("learn_minutes = 3\n").unlock_mode == "time"
    assert parse_config("# learn_minutes = 3\nmin_cards = 7\n").unlock_mode == "cards"
    both = parse_config("learn_minutes = 3\nmin_cards = 7\n")
    assert both.unlock_mode == "both" and both.min_cards == 7
    none = parse_config("# learn_minutes = 3\n# min_cards = 7\n")
    assert none.unlock_mode == "time" and none.learn_minutes == 5  # Standard


def test_commented_out_options_are_not_added_back():
    from lernsperre.config import add_missing_options
    text = DEFAULT_CONFIG.replace("learn_minutes = 5 ", "# learn_minutes = 5 ").replace("# min_cards = 20", "min_cards = 20")
    assert add_missing_options(text) == text
    assert parse_config(text).unlock_mode == "cards"


def test_migrate_0_2_0_unlock_mode():
    from pathlib import Path
    from lernsperre.config import add_missing_options, migrate_unlock_mode
    old = (Path(__file__).parent / "old_config_0_2_0.toml").read_text()
    for mode, expected in [("time", "time"), ("cards", "cards"), ("both", "both")]:
        text = add_missing_options(migrate_unlock_mode(old.replace('unlock_mode = "time"', f'unlock_mode = "{mode}"')))
        cfg = parse_config(text)
        assert "unlock_mode" not in text and cfg.unlock_mode == expected
        assert len(cfg.targets) == 6
    assert migrate_unlock_mode(DEFAULT_CONFIG) == DEFAULT_CONFIG


def test_old_config_gets_new_options():
    from lernsperre.config import add_missing_options
    old = 'allowed_minutes = 10\n\n[[targets]]\nname = "YouTube"\ntitles = ["YouTube"]\n'
    new = add_missing_options(old)
    cfg = parse_config(new)
    assert cfg.allowed_minutes == 10 and cfg.unlock_mode == "time" and cfg.icon_locked == "🔒"
    assert [t.name for t in cfg.targets] == ["YouTube"]
    assert add_missing_options(DEFAULT_CONFIG) == DEFAULT_CONFIG


def test_cards_since(tmp_path):
    prof = tmp_path / "p"
    prof.mkdir()
    con = sqlite3.connect(prof / "collection.anki2")
    con.execute("CREATE TABLE revlog (id INTEGER PRIMARY KEY, cid INTEGER)")
    con.executemany("INSERT INTO revlog VALUES (?, 1)", [(1000_000,), (2000_000,), (3000_000,)])
    con.commit()
    act = AnkiActivity(search_dirs=[tmp_path])
    assert act.cards_since(1500) == 2


def test_anki_activity_when_anki_locks_database(tmp_path):
    """Die Anki-Desktop-App sperrt ihre Datenbank exklusiv; dann wird eine Kopie gelesen."""
    prof = tmp_path / "Benutzer 1"
    prof.mkdir()
    db = prof / "collection.anki2"
    anki = sqlite3.connect(db, isolation_level=None)
    anki.execute("PRAGMA locking_mode=exclusive")
    anki.execute("PRAGMA journal_mode=wal")
    anki.execute("CREATE TABLE revlog (id INTEGER PRIMARY KEY, cid INTEGER)")
    anki.execute("CREATE TABLE cards (id INTEGER PRIMARY KEY, x TEXT)")
    anki.execute("INSERT INTO cards VALUES (1, 'a')")
    cache = tmp_path / "cache"
    act = AnkiActivity(search_dirs=[tmp_path], cache_dir=cache)
    act.reset()
    t0 = time.time()
    assert act.poll(t0, t0) == (None, 0)
    assert act.mode == "kopie"
    original = (db.read_bytes(), (prof / "collection.anki2-wal").read_bytes())
    anki.execute("UPDATE cards SET x = 'Deck geöffnet' WHERE id = 1")  # keine Antwort
    assert act.poll(t0 + 1, t0) == (None, 0)
    ids = [int(t0 * 1000) + 100 + i for i in range(3)]
    for i, ms in enumerate(ids):  # drei Antworten
        anki.execute("INSERT INTO revlog VALUES (?, 1)", (ms,))
        last, cards = act.poll(t0 + 2 + i, t0)
        assert last == ms / 1000 and cards == i + 1
    anki.execute("DELETE FROM revlog WHERE id = ?", (ids[-1],))  # Rückgängig
    assert act.poll(t0 + 10, t0)[1] == 2
    # Antworten von vor der Sperre zählen nicht
    assert act.poll(t0 + 11, t0 + 5)[1] == 0
    assert db.stat().st_size == len(original[0])  # Ankis Hauptdatei unverändert
    act.cleanup()
    assert not cache.exists()
    anki.close()
    # Anki zu: wieder direkt lesen
    assert act.poll(t0 + 100, t0)[1] == 2 and act.mode == "direkt"


def test_bonus_time_for_voluntary_cards():
    e = Engine(cfg_with(bonus_cards=10, bonus_minutes=5))
    run(e, Signals(windows=[FF_YT]), 600, start=0)  # 10 min geschaut
    # aus: Karten bringen nichts
    e.tick(600, 1, Signals(windows=[ANKI], cards_since_bonus=30))
    assert e.state.used == 600
    assert e.set_bonus(601, True) == [("bonus", True)]
    e.tick(602, 1, Signals(windows=[ANKI], cards_since_bonus=9))
    assert e.state.used == 600
    ev = e.tick(603, 1, Signals(windows=[ANKI], cards_since_bonus=10))
    assert ev == [("bonus_gained", 5)] and e.state.used == 300
    e.tick(604, 1, Signals(windows=[ANKI], cards_since_bonus=10))  # nicht doppelt
    assert e.state.used == 300
    ev = e.tick(605, 1, Signals(windows=[ANKI], cards_since_bonus=31))  # zwei Pakete auf einmal
    assert ev == [("bonus_gained", 10)] and e.state.used == -300
    snap = e.snapshot()
    assert snap["remaining"] == 20 * 60 + 300 and snap["bonus_progress"] == 1 and snap["bonus_gained_minutes"] == 15


def test_bonus_not_during_lock_and_restarts_after_unlock():
    e = Engine(cfg_with(bonus_cards=10, bonus_minutes=5))
    e.set_bonus(0, True)
    e.lock(10)
    e.tick(11, 1, Signals(windows=[ANKI], cards_since_bonus=50, cards_since_lock=0))
    assert e.state.bonus_rewards == 0  # Karten in der Sperre zählen fürs Entsperren, nicht als Bonus
    run(e, Signals(windows=[ANKI]), 5 * 60 + 5, start=20, last_answer_fn=lambda n: n)
    assert e.state.mode == "free" and e.state.bonus_since >= 20 and e.state.bonus_cards == 0
    e.set_bonus(400, False)
    e.tick(401, 1, Signals(windows=[ANKI], cards_since_bonus=10))
    assert e.state.used == 0


def test_bonus_options_in_config():
    cfg = parse_config(DEFAULT_CONFIG)
    assert cfg.bonus_cards == 10 and cfg.bonus_minutes == 5
    from lernsperre.config import add_missing_options
    old = 'allowed_minutes = 10\n\n[[targets]]\nname = "YouTube"\ntitles = ["YouTube"]\n'
    assert "bonus_cards = 10" in add_missing_options(old)


def test_bonus_stops_when_target_starts_and_refuses_while_running():
    e = Engine(cfg_with(bonus_cards=10, bonus_minutes=5))
    e.tick(0, 1, Signals(windows=[FF_YT]))
    ev = e.set_bonus(1, True)
    assert ev[0][0] == "bonus_refused" and "YouTube" in ev[0][1] and not e.state.bonus_on
    e.tick(2, 1, Signals(windows=[ANKI]))
    assert e.set_bonus(3, True) == [("bonus", True)]
    # YouTube im Hintergrund abspielen beendet den Modus auch
    yt_bg = Window(title="Musik – YouTube — Mozilla Firefox", app_id="firefox_firefox")
    ff = Player("org.mpris.MediaPlayer2.firefox.instance_1_2", playing=True, desktop_entry="firefox", title="Musik")
    ev = e.tick(4, 1, Signals(windows=[ANKI, yt_bg], players=[ff], cards_since_bonus=10))
    assert ev[0][0] == "bonus_stopped" and "YouTube" in ev[0][1]
    assert not e.state.bonus_on and e.state.bonus_rewards == 0  # keine Bonuszeit mehr gutgeschrieben


def test_bonus_stops_on_lock_and_cannot_start_while_locked():
    e = Engine(CFG)
    e.set_bonus(0, True)
    ev = e.lock(5)
    assert ("locked",) in ev and any(k == "bonus_stopped" for k, *_ in ev) and not e.state.bonus_on
    assert e.set_bonus(6, True)[0][0] == "bonus_refused"


def test_bonus_also_stops_while_paused():
    e = Engine(CFG)
    e.set_bonus(0, True)
    e.pause(1, 15)
    ev = e.tick(2, 1, Signals(windows=[FF_YT]))
    assert any(k == "bonus_stopped" for k, *_ in ev)
