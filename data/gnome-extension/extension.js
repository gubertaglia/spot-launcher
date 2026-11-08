import Gio from 'gi://Gio';
import GObject from 'gi://GObject';
import GLib from 'gi://GLib';
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

    enable() {
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
        global.display.disconnect(this.overlay);
        GObject.signal_handlers_unblock_matched(global.display, {signalId: this.signalId});
        Main.overview.show = this.show;
        Main.overview.toggle = this.toggle;
    }
}
