// LernSperre – GNOME-Shell-Erweiterung
//
// Aufgaben:
//  * meldet dem LernSperre-Dienst regelmäßig alle Fenster (Titel, App-ID, WM_CLASS, Fokus)
//  * zeigt die Restzeit im Panel
//  * legt bei einer Sperre ein Vollbild-Overlay über alles, das nur verschwindet,
//    solange Anki vorne ist
//
// LernSperre ist ein unabhängiges Projekt und nicht mit Anki oder Ankitects verbunden.

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const BUS_NAME = 'io.github.janiktest.LernSperre';
const OBJECT_PATH = '/io/github/janiktest/LernSperre';
const IFACE_XML = `
<node>
  <interface name="io.github.janiktest.LernSperre">
    <method name="ReportWindows"><arg type="s" name="windows_json" direction="in"/></method>
    <method name="GetState"><arg type="s" name="state_json" direction="out"/></method>
    <method name="LockNow"/>
    <method name="Reset"/>
    <method name="Reload"/>
    <method name="Pause"><arg type="u" name="minutes" direction="in"/></method>
    <method name="Resume"/>
    <method name="SetBonus"><arg type="b" name="on" direction="in"/></method>
    <method name="Quit"/>
    <signal name="StateChanged"><arg type="s" name="state_json"/></signal>
  </interface>
</node>`;
const LernSperreProxy = Gio.DBusProxy.makeProxyWrapper(IFACE_XML);

const GITHUB_URL = 'https://github.com/janiktest/lernsperre';
const GUIDE_URL = `${GITHUB_URL}/blob/main/docs/ANLEITUNG.md`;
const DEFAULT_ICONS = {free: '⏳', locked: '🔒', paused: '☕', learning: '▶', learning_paused: '⏸'};
const REPORT_INTERVAL_S = 2;
const ANKI_START_GRACE_MS = 30000;
const WATCHED_TYPES = [
    Meta.WindowType.NORMAL,
    Meta.WindowType.DIALOG,
    Meta.WindowType.MODAL_DIALOG,
    Meta.WindowType.UTILITY,
];

function fmt(seconds) {
    const s = Math.max(0, Math.round(seconds));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

function windowIds(w) {
    const app = Shell.WindowTracker.get_default().get_window_app(w);
    return [w.get_gtk_application_id(), w.get_sandboxed_app_id(), app?.get_id()]
        .filter(Boolean)
        .join(' ');
}

export default class LernSperreExtension extends Extension {
    enable() {
        this._state = null;
        this._grab = null;
        this._graceUntil = 0;
        this._signals = [];

        this._buildIndicator();
        this._buildOverlay();

        this._proxy = new LernSperreProxy(
            Gio.DBus.session, BUS_NAME, OBJECT_PATH,
            (proxy, error) => {
                if (error || !this._proxy)
                    return;
                this._stateSignal = proxy.connectSignal('StateChanged',
                    (_p, _sender, [json]) => this._onState(json));
                this._ownerSignal = proxy.connect('notify::g-name-owner', () => {
                    if (!proxy.g_name_owner)
                        this._onState(null);
                    else
                        this._report();
                });
                this._report();
            },
            null, Gio.DBusProxyFlags.DO_NOT_AUTO_START);

        this._signals.push([global.display,
            global.display.connect('notify::focus-window', () => this._onFocusChanged())]);
        this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, REPORT_INTERVAL_S, () => {
            this._report();
            return GLib.SOURCE_CONTINUE;
        });
        this._render();
    }

    disable() {
        if (this._timer) {
            GLib.source_remove(this._timer);
            this._timer = 0;
        }
        if (this._emergencyTimer) {
            GLib.source_remove(this._emergencyTimer);
            this._emergencyTimer = 0;
        }
        if (this._graceTimer) {
            GLib.source_remove(this._graceTimer);
            this._graceTimer = 0;
        }
        for (const [obj, id] of this._signals)
            obj.disconnect(id);
        this._signals = [];
        if (this._proxy) {
            if (this._stateSignal)
                this._proxy.disconnectSignal(this._stateSignal);
            if (this._ownerSignal)
                this._proxy.disconnect(this._ownerSignal);
        }
        this._proxy = null;
        this._setModal(false);
        this._overlay?.destroy();
        this._overlay = null;
        this._indicator?.destroy();
        this._indicator = null;
        this._state = null;
    }

    // --- Fenster melden ---------------------------------------------------
    _collectWindows() {
        const focus = global.display.focus_window;
        return global.get_window_actors()
            .map(a => a.meta_window)
            .filter(w => w && WATCHED_TYPES.includes(w.get_window_type()))
            .map(w => ({
                title: w.get_title() ?? '',
                wm_class: w.get_wm_class() ?? '',
                app_id: windowIds(w),
                focused: w === focus,
                minimized: w.minimized,
            }));
    }

    _report() {
        if (!this._proxy?.g_name_owner)
            return;
        try {
            this._proxy.ReportWindowsRemote(JSON.stringify(this._collectWindows()), () => {});
        } catch (e) {
            console.debug(`LernSperre: ReportWindows fehlgeschlagen: ${e}`);
        }
    }

    _onFocusChanged() {
        // Während Anki startet, darf kein anderes Fenster nach vorne
        const focus = global.display.focus_window;
        if (this._state?.mode === 'locked' && Date.now() < this._graceUntil &&
            focus && !this._isAnki(focus))
            focus.minimize();
        this._report();
        this._render();
    }

    _isAnki(w) {
        if (!w)
            return false;
        const ids = `${windowIds(w)} ${w.get_wm_class() ?? ''}`.toLowerCase();
        const patterns = this._state?.anki_app_ids ?? ['net.ankiweb.anki', 'anki'];
        return patterns.some(p => p && ids.includes(p.toLowerCase()));
    }

    // --- Zustand vom Dienst -----------------------------------------------
    _onState(json) {
        try {
            this._state = json ? JSON.parse(json) : null;
        } catch (e) {
            this._state = null;
        }
        this._render();
    }

    _render() {
        if (!this._indicator)
            return;
        const s = this._state;
        const locked = s?.mode === 'locked';

        // Panel
        this._label.remove_style_class_name('lernsperre-panel-locked');
        this._label.remove_style_class_name('lernsperre-panel-warn');
        const icons = {...DEFAULT_ICONS, ...(s?.icons ?? {})};
        const withTime = (icon, secs) => (s?.show_time === false || secs === null ? icon : `${icon} ${fmt(secs)}`);
        if (!s) {
            this._label.text = 'LS –';
            this._statusItem.label.text = 'LernSperre läuft nicht';
        } else if (locked) {
            const goal = this._lockProgress(s);
            const learnIcon = s.learning_active ? icons.learning : icons.learning_paused;
            const secs = s.unlock_mode === 'cards' ? null : s.learn_remaining;
            let text = withTime(icons.locked, secs);
            if (s.unlock_mode !== 'time')
                text += ` ${s.cards_done}/${s.min_cards}`;
            this._label.text = `${text} ${learnIcon}`;
            this._label.add_style_class_name('lernsperre-panel-locked');
            this._statusItem.label.text = `Gesperrt – ${goal}`;
        } else if (s.paused) {
            this._label.text = withTime(icons.paused, s.paused_remaining);
            this._statusItem.label.text = `Pausiert – noch ${fmt(s.paused_remaining)}`;
        } else {
            this._label.text = withTime(icons.free, s.remaining);
            if (s.remaining <= 60)
                this._label.add_style_class_name('lernsperre-panel-warn');
            this._statusItem.label.text = s.target
                ? `Zählt gerade: ${s.target} (${s.reason}) – noch ${fmt(s.remaining)}`
                : `Noch ${fmt(s.remaining)} von ${fmt(s.allowed)} erlaubt`;
        }
        if (s?.bonus_on && !locked)
            this._statusItem.label.text += `\nBonuszeit: ${s.bonus_progress} von ${s.bonus_cards} Karten bis +${s.bonus_minutes} min`;
        if (s?.config_error)
            this._statusItem.label.text += `\n⚠ ${s.config_error}`;
        this._updateMenu(s, locked);

        // Overlay
        const focus = global.display.focus_window;
        let show = locked && !this._isAnki(focus);
        if (show && Date.now() < this._graceUntil)
            show = false; // Anki startet gerade
        if (this._isAnki(focus))
            this._graceUntil = 0;
        if (locked) {
            this._goalLabel.text = `${s.unlock_goal} in Anki, dann geht es weiter.`;
            this._timeLabel.text = this._lockProgress(s);
            let hint = s.unlock_mode === 'cards'
                ? 'Es zählen alle Karten, die du seit der Sperre beantwortest.'
                : `Die Lernzeit läuft nur, solange Anki vorne ist und du Karten beantwortest (Pause nach ${Math.round(s.idle_seconds)} s ohne Antwort).`;
            if (s.anki_note)
                hint = `Hinweis: ${s.anki_note}`;
            this._hintLabel.text = hint;
        }
        this._setOverlayVisible(show);
    }

    _lockProgress(s) {
        const parts = [];
        if (s.unlock_mode !== 'cards')
            parts.push(`noch ${fmt(s.learn_remaining)}`);
        if (s.unlock_mode !== 'time')
            parts.push(`${s.cards_done} von ${s.min_cards} Karten`);
        return parts.join(' · ');
    }

    _updateMenu(s, locked) {
        const running = !!s;
        this._lockItem.visible = running && !locked;
        this._resetItem.visible = running && !locked;
        this._pauseMenu.visible = running && !locked && !s.paused;
        this._resumeItem.visible = running && !!s?.paused;
        this._quitItem.visible = running && !locked;
        this._startItem.visible = !running;
        this._bonusItem.visible = running && s.bonus_on !== undefined;
        if (running && s.bonus_on !== undefined) {
            this._bonusItem.setToggleState(!!s.bonus_on);
            this._bonusItem.label.text = `Bonuszeit durch Lernen (${s.bonus_cards} Karten = ${s.bonus_minutes} min)`;
        }

        const key = JSON.stringify(s?.pause_minutes ?? []);
        if (running && key !== this._pauseKey) {
            this._pauseKey = key;
            this._pauseMenu.menu.removeAll();
            for (const m of s.pause_minutes) {
                const item = new PopupMenu.PopupMenuItem(`${m} Minuten`);
                item.connect('activate', () => this._proxy?.PauseRemote(m, () => {}));
                this._pauseMenu.menu.addMenuItem(item);
            }
        }
    }

    _launchUri(uri) {
        try {
            Gio.AppInfo.launch_default_for_uri(uri, global.create_app_launch_context(0, -1));
            return true;
        } catch (e) {
            console.debug(`LernSperre: ${uri} nicht geöffnet: ${e}`);
            return false;
        }
    }

    _openSettings() {
        const path = this._state?.config_path ??
            GLib.build_filenamev([GLib.get_user_config_dir(), 'lernsperre', 'config.toml']);
        const editor = (this._state?.editor ?? '').trim();
        const commands = [];
        if (editor)
            commands.push([...editor.split(/\s+/), path]);
        for (const cmd of commands) {
            try {
                Gio.Subprocess.new(cmd, Gio.SubprocessFlags.NONE);
                return;
            } catch (e) {
                console.debug(`LernSperre: ${cmd[0]} nicht gefunden`);
            }
        }
        // Standard-Texteditor (TOML wird als Text geöffnet)
        const textApp = Gio.AppInfo.get_default_for_type('text/plain', false);
        if (textApp) {
            try {
                textApp.launch([Gio.File.new_for_path(path)], global.create_app_launch_context(0, -1));
                return;
            } catch (e) {
                console.debug(`LernSperre: Texteditor nicht gestartet: ${e}`);
            }
        }
        for (const cmd of [['gnome-text-editor', path], ['gedit', path]]) {
            try {
                Gio.Subprocess.new(cmd, Gio.SubprocessFlags.NONE);
                return;
            } catch (e) {
                // nächsten probieren
            }
        }
        this._launchUri(Gio.File.new_for_path(path).get_uri());
    }

    _run(argv) {
        try {
            Gio.Subprocess.new(argv, Gio.SubprocessFlags.NONE);
        } catch (e) {
            console.error(`LernSperre: ${argv.join(' ')} fehlgeschlagen: ${e}`);
        }
    }

    // Menüpunkt, der einen Befehl ausführt. Beim Drüberfahren zeigt er den Befehl.
    _commandItem(label, command) {
        const item = new PopupMenu.PopupMenuItem(label);
        item.connect('notify::hover', () => {
            item.label.text = item.hover ? `$ ${command}` : label;
        });
        item.connect('activate', () => this._run(['sh', '-c', command]));
        return item;
    }

    // --- Panel ------------------------------------------------------------
    _buildIndicator() {
        this._indicator = new PanelMenu.Button(0.0, 'LernSperre', false);
        this._label = new St.Label({text: 'LS –', y_align: Clutter.ActorAlign.CENTER});
        this._indicator.add_child(this._label);

        this._statusItem = new PopupMenu.PopupMenuItem('', {reactive: false});
        this._indicator.menu.addMenuItem(this._statusItem);
        this._indicator.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        const anki = new PopupMenu.PopupMenuItem('Anki öffnen');
        anki.connect('activate', () => this._openAnki());
        this._indicator.menu.addMenuItem(anki);

        this._lockItem = new PopupMenu.PopupMenuItem('Sperre jetzt aktivieren');
        this._lockItem.connect('activate', () => this._proxy?.LockNowRemote(() => {}));
        this._indicator.menu.addMenuItem(this._lockItem);

        this._pauseMenu = new PopupMenu.PopupSubMenuMenuItem('Pausieren');
        this._indicator.menu.addMenuItem(this._pauseMenu);
        this._pauseKey = null;

        this._resumeItem = new PopupMenu.PopupMenuItem('Pause beenden');
        this._resumeItem.connect('activate', () => this._proxy?.ResumeRemote(() => {}));
        this._indicator.menu.addMenuItem(this._resumeItem);

        this._bonusItem = new PopupMenu.PopupSwitchMenuItem('Bonuszeit durch Lernen', false);
        this._bonusItem.connect('toggled', (_item, on) => this._proxy?.SetBonusRemote(on, () => {}));
        this._indicator.menu.addMenuItem(this._bonusItem);

        this._resetItem = new PopupMenu.PopupMenuItem('Zähler zurücksetzen');
        this._resetItem.connect('activate', () => this._proxy?.ResetRemote(() => {}));
        this._indicator.menu.addMenuItem(this._resetItem);

        this._indicator.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        const settings = new PopupMenu.PopupMenuItem('Einstellungen');
        settings.connect('activate', () => this._openSettings());
        this._indicator.menu.addMenuItem(settings);

        const guide = new PopupMenu.PopupMenuItem('Anleitung');
        guide.connect('activate', () => this._launchUri(GUIDE_URL));
        this._indicator.menu.addMenuItem(guide);

        const github = new PopupMenu.PopupMenuItem('GitHub-Seite');
        github.connect('activate', () => this._launchUri(GITHUB_URL));
        this._indicator.menu.addMenuItem(github);

        this._indicator.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        this._quitItem = new PopupMenu.PopupMenuItem('LernSperre beenden');
        this._quitItem.connect('activate', () => this._proxy?.QuitRemote(() => {}));
        this._indicator.menu.addMenuItem(this._quitItem);

        this._startItem = this._commandItem('LernSperre starten', 'systemctl --user start lernsperre');
        this._indicator.menu.addMenuItem(this._startItem);

        this._indicator.menu.addMenuItem(this._commandItem(
            'Dienst neu starten', 'systemctl --user restart lernsperre'));
        this._indicator.menu.addMenuItem(this._commandItem(
            'Erweiterung neu laden',
            `gnome-extensions disable ${this.uuid} && gnome-extensions enable ${this.uuid}`));

        Main.panel.addToStatusArea(this.uuid, this._indicator);
    }

    // --- Overlay ----------------------------------------------------------
    _buildOverlay() {
        this._overlay = new St.Widget({
            style_class: 'lernsperre-overlay',
            reactive: true,
            can_focus: true,
            visible: false,
        });
        // Das Overlay dunkelt alle Bildschirme ab; Text und Knöpfe stehen nur
        // auf dem Hauptbildschirm (this._primaryArea).
        this._overlay.add_constraint(new Clutter.BindConstraint({
            source: global.stage,
            coordinate: Clutter.BindCoordinate.ALL,
        }));
        this._primaryArea = new St.Widget({layout_manager: new Clutter.BinLayout()});
        this._overlay.add_child(this._primaryArea);

        const box = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'lernsperre-box',
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
        });
        box.add_child(new St.Label({text: 'Zeit zum Lernen', style_class: 'lernsperre-title'}));
        box.add_child(new St.Label({
            text: 'Die erlaubte Zeit ist um.',
            style_class: 'lernsperre-text',
        }));
        this._goalLabel = new St.Label({text: '', style_class: 'lernsperre-text'});
        box.add_child(this._goalLabel);
        this._timeLabel = new St.Label({text: '', style_class: 'lernsperre-time'});
        box.add_child(this._timeLabel);
        this._hintLabel = new St.Label({text: '', style_class: 'lernsperre-text'});
        this._hintLabel.clutter_text.line_wrap = true;
        box.add_child(this._hintLabel);

        const button = new St.Button({
            label: 'Anki öffnen',
            style_class: 'lernsperre-button',
            x_align: Clutter.ActorAlign.CENTER,
            can_focus: true,
        });
        button.connect('clicked', () => this._openAnki());
        box.add_child(button);
        this._button = button;

        // Notausgang, falls Anki nicht startet. Braucht zwei Klicks.
        this._emergency = new St.Button({
            label: 'Notfall: Sperre aufheben',
            style_class: 'lernsperre-emergency',
            x_align: Clutter.ActorAlign.CENTER,
        });
        this._emergency.connect('clicked', () => this._onEmergency());
        box.add_child(this._emergency);

        box.add_child(new St.Label({
            text: 'LernSperre ist ein unabhängiges Projekt und nicht mit Anki oder Ankitects verbunden.',
            style_class: 'lernsperre-text',
            opacity: 140,
        }));

        this._primaryArea.add_child(box);
        Main.layoutManager.addTopChrome(this._overlay);
        this._placeOverlay();
        this._signals.push([Main.layoutManager,
            Main.layoutManager.connect('monitors-changed', () => this._placeOverlay())]);
    }

    _placeOverlay() {
        const m = Main.layoutManager.primaryMonitor;
        if (!m || !this._primaryArea)
            return;
        this._primaryArea.set_position(m.x, m.y);
        this._primaryArea.set_size(m.width, m.height);
        this._hintLabel.style = `max-width: ${Math.round(m.width * 0.6)}px;`;
    }

    _setOverlayVisible(show) {
        if (!this._overlay || this._overlay.visible === show)
            return;
        if (show) {
            if (Main.overview.visible)
                Main.overview.hide();
            this._overlay.show();
            this._setModal(true);
            this._button.grab_key_focus();
        } else {
            this._setModal(false);
            this._overlay.hide();
        }
    }

    _setModal(on) {
        if (on && !this._grab) {
            this._grab = Main.pushModal(this._overlay, {actionMode: Shell.ActionMode.NONE});
        } else if (!on && this._grab) {
            Main.popModal(this._grab);
            this._grab = null;
        }
    }

    _launchAnki() {
        // 1. Läuft Anki schon? Dann nur nach vorne holen.
        const running = global.get_window_actors()
            .map(a => a.meta_window)
            .filter(w => w && w.get_window_type() === Meta.WindowType.NORMAL && this._isAnki(w))
            .sort((a, b) => b.get_user_time() - a.get_user_time());
        if (running.length) {
            Main.activateWindow(running[0]);
            return;
        }
        // 2. Eigener Befehl aus den Einstellungen (anki_launch)
        const cmd = this._state?.anki_launch_argv ?? [];
        if (cmd.length) {
            Gio.Subprocess.new(cmd, Gio.SubprocessFlags.NONE);
            return;
        }
        // 3. Desktop-Datei (anki_desktop_id), sonst Flatpak
        const desktopId = this._state?.anki_desktop_id ?? 'net.ankiweb.Anki.desktop';
        const app = Shell.AppSystem.get_default().lookup_app(desktopId);
        if (app)
            app.activate();
        else
            Gio.Subprocess.new(['flatpak', 'run', 'net.ankiweb.Anki'], Gio.SubprocessFlags.NONE);
    }

    _onEmergency() {
        if (!this._emergencyArmed) {
            this._emergencyArmed = true;
            this._emergency.label = 'Wirklich aufheben? Nochmal klicken';
            this._emergencyTimer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 5, () => {
                this._emergencyTimer = 0;
                this._emergencyArmed = false;
                if (this._emergency)
                    this._emergency.label = 'Notfall: Sperre aufheben';
                return GLib.SOURCE_REMOVE;
            });
            return;
        }
        this._emergencyArmed = false;
        this._emergency.label = 'Notfall: Sperre aufheben';
        this._proxy?.ResetRemote(() => {});
    }

    _openAnki() {
        const focus = global.display.focus_window;
        if (this._state?.mode === 'locked' && focus && !this._isAnki(focus))
            focus.minimize();
        this._graceUntil = Date.now() + ANKI_START_GRACE_MS;
        this._setOverlayVisible(false);

        try {
            this._launchAnki();
        } catch (e) {
            console.error(`LernSperre: Anki konnte nicht gestartet werden: ${e}`);
            this._graceUntil = 0;
        }
        // Nach Ablauf der Schonfrist erneut prüfen
        if (this._graceTimer)
            GLib.source_remove(this._graceTimer);
        this._graceTimer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, ANKI_START_GRACE_MS + 100, () => {
            this._graceTimer = 0;
            this._render();
            return GLib.SOURCE_REMOVE;
        });
    }
}
