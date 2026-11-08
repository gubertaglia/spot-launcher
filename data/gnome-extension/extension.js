import Gio from 'gi://Gio';
import GObject from 'gi://GObject';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

export default class SpotExtension extends Extension {
    settings() {
        try {
            const file = Gio.File.new_for_path(GLib.build_filenamev([GLib.get_user_config_dir(), 'spot-launcher', 'config.json']));
            const [, contents] = file.load_contents(null);
            return JSON.parse(new TextDecoder().decode(contents));
        } catch (_) {
            return {};
        }
    }

    placeOnPointerMonitor(actor, oldWidth = 0, oldHeight = 0) {
        const window = actor.meta_window;
        if (!window || window.get_gtk_application_id() !== 'org.spot.Launcher' ||
            window.get_transient_for() || window.get_client_type() !== Meta.WindowClientType.WAYLAND)
            return;
        const settings = this.settings();
        if (!settings.pointer_monitor && !settings.super_launcher)
            return;
        const frame = window.get_frame_rect();
        if (oldWidth > 0 && oldHeight > 0) {
            window.move_frame(false, Math.round(frame.x + (oldWidth - frame.width) / 2),
                Math.round(frame.y + (oldHeight - frame.height) / 2));
            return;
        }
        const [x, y] = global.get_pointer();
        const monitor = Main.layoutManager.monitors.find(m =>
            x >= m.x && x < m.x + m.width && y >= m.y && y < m.y + m.height);
        if (!monitor)
            return;
        window.move_frame(false,
            Math.round(monitor.x + Math.max(0, (monitor.width - frame.width) / 2)),
            Math.round(monitor.y + Math.max(0, monitor.height * 0.35 - frame.height / 2)));
    }

    Place(oldWidth, oldHeight) {
        for (const actor of global.get_window_actors()) {
            if (actor.visible)
                this.placeOnPointerMonitor(actor, oldWidth, oldHeight);
        }
    }

    enable() {
        this.placement = Gio.DBusExportedObject.wrapJSObject(
            '<node><interface name="org.spot.Launcher.Integration">' +
            '<method name="Place"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>' +
            '</interface></node>', this);
        this.placement.export(Gio.DBus.session, '/org/spot/Launcher/Integration');
        this.mapId = global.window_manager.connect('map', (_manager, actor) => this.placeOnPointerMonitor(actor));
        this.signalId = 'overlay-key';
        GObject.signal_handlers_block_matched(global.display, {signalId: this.signalId});
        this.overlay = global.display.connect('overlay-key', () => {
            const settings = this.settings();
            if (settings.super_launcher) {
                Gio.DBus.session.call('org.spot.Launcher', '/org/spot/Launcher',
                    'org.gtk.Actions', 'Activate',
                    new GLib.Variant('(sava{sv})', ['toggle', [], {}]), null,
                    Gio.DBusCallFlags.NONE, -1, null, null);
            } else if (!settings.disable_overview) {
                this.toggle.call(Main.overview);
            }
        });
        this.show = Main.overview.show;
        this.toggle = Main.overview.toggle;
        Main.overview.show = (...args) => {
            if (!this.settings().disable_overview)
                return this.show.apply(Main.overview, args);
        };
        Main.overview.toggle = (...args) => {
            if (!this.settings().disable_overview)
                return this.toggle.apply(Main.overview, args);
        };
    }

    disable() {
        this.placement.unexport();
        global.window_manager.disconnect(this.mapId);
        global.display.disconnect(this.overlay);
        GObject.signal_handlers_unblock_matched(global.display, {signalId: this.signalId});
        Main.overview.show = this.show;
        Main.overview.toggle = this.toggle;
    }
}
