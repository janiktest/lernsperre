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
