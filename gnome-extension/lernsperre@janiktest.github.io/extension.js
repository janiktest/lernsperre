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
    <signal name="StateChanged"><arg type="s" name="state_json"/></signal>
  </interface>
</node>`;
const LernSperreProxy = Gio.DBusProxy.makeProxyWrapper(IFACE_XML);

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
        if (!s) {
            this._label.text = 'LS –';
            this._statusItem.label.text = 'LernSperre-Dienst läuft nicht';
        } else if (locked) {
            this._label.text = `🔒 ${fmt(s.learn_remaining)}${s.learning_active ? ' ▶' : ' ⏸'}`;
            this._label.add_style_class_name('lernsperre-panel-locked');
            this._statusItem.label.text = s.learning_active
                ? `Lernzeit läuft: noch ${fmt(s.learn_remaining)}`
                : `Lernzeit pausiert: Anki vorne haben und Karten beantworten (noch ${fmt(s.learn_remaining)})`;
        } else {
            this._label.text = `⏳ ${fmt(s.remaining)}`;
            if (s.remaining <= 60)
                this._label.add_style_class_name('lernsperre-panel-warn');
            this._statusItem.label.text = s.target
                ? `Zählt gerade: ${s.target} (${s.reason}) – noch ${fmt(s.remaining)}`
                : `Noch ${fmt(s.remaining)} von ${fmt(s.allowed)} erlaubt`;
        }
        this._lockItem.visible = !!s && !locked;
        this._resetItem.visible = !!s && !locked;

        // Overlay
        const focus = global.display.focus_window;
        let show = locked && !this._isAnki(focus);
        if (show && Date.now() < this._graceUntil)
            show = false; // Anki startet gerade
        if (this._isAnki(focus))
            this._graceUntil = 0;
        if (locked) {
            this._timeLabel.text = fmt(s.learn_remaining);
            this._hintLabel.text = s.anki_note
                ? `Hinweis: ${s.anki_note}`
                : `Die Lernzeit läuft nur, solange Anki vorne ist und du Karten beantwortest (Pause nach ${Math.round(s.idle_seconds)} s ohne Antwort).`;
        }
        this._setOverlayVisible(show);
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

        this._resetItem = new PopupMenu.PopupMenuItem('Zähler zurücksetzen');
        this._resetItem.connect('activate', () => this._proxy?.ResetRemote(() => {}));
        this._indicator.menu.addMenuItem(this._resetItem);

        Main.panel.addToStatusArea(this.uuid, this._indicator);
    }

    // --- Overlay ----------------------------------------------------------
    _buildOverlay() {
        this._overlay = new St.Widget({
            style_class: 'lernsperre-overlay',
            reactive: true,
            can_focus: true,
            visible: false,
            layout_manager: new Clutter.BinLayout(),
        });
        this._overlay.add_constraint(new Clutter.BindConstraint({
            source: global.stage,
            coordinate: Clutter.BindCoordinate.ALL,
        }));

        const box = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'lernsperre-box',
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
        });
        box.add_child(new St.Label({text: 'Zeit zum Lernen', style_class: 'lernsperre-title'}));
        box.add_child(new St.Label({
            text: 'Die erlaubte Zeit ist um. Lerne jetzt in Anki, dann geht es weiter.',
            style_class: 'lernsperre-text',
        }));
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

        this._overlay.add_child(box);
        Main.layoutManager.addTopChrome(this._overlay);
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

        const desktopId = this._state?.anki_desktop_id ?? 'net.ankiweb.Anki.desktop';
        const app = Shell.AppSystem.get_default().lookup_app(desktopId);
        try {
            if (app)
                app.activate();
            else
                Gio.Subprocess.new(['flatpak', 'run', 'net.ankiweb.Anki'], Gio.SubprocessFlags.NONE);
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
