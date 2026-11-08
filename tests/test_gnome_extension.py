from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('gjs'), 'gjs is unavailable')
class GnomePlacementTests(unittest.TestCase):
    def test_wayland_placement_and_signal_cleanup(self):
        source = (Path(__file__).resolve().parents[1] / 'data/gnome-extension/extension.js').read_text()
        source = '\n'.join(line for line in source.splitlines() if not line.startswith('import '))
        source = source.replace('export default class', 'class')
        script = '''
const Extension = class {};
const Gio = {DBus: {session: {}}, DBusExportedObject: {wrapJSObject: () => ({export() {}, unexport() {}})}};
const Meta = {WindowClientType: {WAYLAND: 1}};
const signals = [];
const disconnected = [];
const global = {
    get_pointer: () => [-100, 100],
    window_manager: {
        connect: (signal, callback) => { signals.push([signal, callback]); return 42; },
        disconnect: id => disconnected.push(id),
    },
    display: {connect: () => 43, disconnect: () => {}},
};
const GObject = {signal_handlers_block_matched: () => {}, signal_handlers_unblock_matched: () => {}};
const Main = {
    layoutManager: {monitors: [{x: 0, y: 0, width: 1920, height: 1080},
                              {x: -1920, y: 0, width: 1920, height: 1080}]},
    overview: {show() {}, toggle() {}},
};
function assert(value) { if (!value) throw new Error('placement assertion failed'); }
'''
        script += source + '''
const extension = new SpotExtension();
let settings = {pointer_monitor: true};
extension.settings = () => settings;
let moved = null;
const window = {
    get_gtk_application_id: () => 'org.spot.Launcher',
    get_transient_for: () => null,
    get_client_type: () => Meta.WindowClientType.WAYLAND,
    get_frame_rect: () => ({x: 100, y: 200, width: 580, height: 100}),
    move_frame: (...args) => { moved = args; },
};
extension.enable();
assert(signals[0][0] === 'map');
signals[0][1](null, {meta_window: window});
assert(JSON.stringify(moved) === JSON.stringify([false, -1250, 328]));
for (const overrides of [{pointer_monitor: false}]) {
    settings = overrides;
    moved = null;
    extension.placeOnPointerMonitor({meta_window: window});
    assert(moved === null);
}
settings = {super_launcher: true, pointer_monitor: false, remember_position: true};
extension.placeOnPointerMonitor({meta_window: window});
assert(JSON.stringify(moved) === JSON.stringify([false, -1250, 328]));
extension.placeOnPointerMonitor({meta_window: window}, 400, 80);
assert(JSON.stringify(moved) === JSON.stringify([false, 10, 190]));
moved = null;
settings = {pointer_monitor: true};
window.get_client_type = () => 0;
extension.placeOnPointerMonitor({meta_window: window});
assert(moved === null);
window.get_client_type = () => Meta.WindowClientType.WAYLAND;
window.get_transient_for = () => ({});
extension.placeOnPointerMonitor({meta_window: window});
assert(moved === null);
extension.disable();
assert(disconnected[0] === 42);
'''
        subprocess.run(['gjs', '-c', script], check=True, capture_output=True, text=True, timeout=10)
