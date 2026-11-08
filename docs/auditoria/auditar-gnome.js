// Executado apenas por sessao-isolada.py no GNOME headless descartável.
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import System from 'system';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as Scripting from 'resource:///org/gnome/shell/ui/scripting.js';
import * as Config from 'resource:///org/gnome/shell/misc/config.js';

export const METRICS = {};
const uuid = 'spot-launcher@spot.local';
const report = {version: Config.PACKAGE_VERSION, checks: {}, memory: []};

function assert(value, message) {
    if (!value)
        throw new Error(message);
}

function settings(value) {
    const directory = GLib.build_filenamev([GLib.get_user_config_dir(), 'spot-launcher']);
    GLib.mkdir_with_parents(directory, 0o700);
    GLib.file_set_contents(directory + '/config.json', JSON.stringify(value));
}

function save() {
    GLib.file_set_contents(GLib.getenv('SPOT_AUDIT_OUTPUT'), JSON.stringify(report, null, 2));
}

function memory(label) {
    System.gc();
    const [, bytes] = GLib.file_get_contents('/proc/self/smaps_rollup');
    const text = new TextDecoder().decode(bytes);
    const sample = {label};
    for (const key of ['Rss', 'Pss', 'Private_Clean', 'Private_Dirty', 'Swap', 'SwapPss'])
        sample[key + '_kib'] = Number(text.match(new RegExp(`^${key}:\\s+(\\d+)`, 'm'))[1]);
    report.memory.push(sample);
    save();
}

export async function run() {
    assert(GLib.getenv('SPOT_AUDIT_ISOLATED') === '1', 'Sessão não isolada');
    const extension = Main.extensionManager.lookup(uuid);
    report.checks.loaded = !!extension?.stateObj;
    report.checks.initialState = extension?.state;
    report.checks.initialErrors = extension?.errors;
    save();
    assert(extension?.stateObj, 'A extensão não carregou');
    const instance = extension.stateObj;
    const originalShow = instance.show;
    assert(typeof originalShow === 'function', 'enable não concluiu');
    report.checks.overviewPatched = Main.overview.show !== originalShow;
    assert(report.checks.overviewPatched, 'Método do panorama não alterado');

    settings({pointer_monitor: true});
    Main.overview.hide();
    await Scripting.sleep(300);
    global.display.emit('overlay-key');
    await Scripting.sleep(700);
    report.checks.normalSuperOpensOverview = Main.overview.visible;
    assert(Main.overview.visible, 'Super deixou de abrir panorama com configuração normal');
    Main.overview.hide();
    await Scripting.sleep(700);
    settings(null);
    global.display.emit('overlay-key');
    await Scripting.sleep(400);
    report.checks.nullConfigBreaksSuper = !Main.overview.visible;
    Main.overview.hide();
    await Scripting.sleep(700);
    settings({});
    global.display.emit('overlay-key');
    await Scripting.sleep(700);
    report.checks.validConfigRestoresSuper = Main.overview.visible;
    assert(report.checks.nullConfigBreaksSuper === (GLib.getenv('SPOT_AUDIT_FIXED') !== '1') && report.checks.validConfigRestoresSuper,
        'Reprodução de configuração null mudou');
    Main.overview.hide();
    await Scripting.sleep(700);
    settings({disable_overview: true});
    global.display.emit('overlay-key');
    await Scripting.sleep(400);
    report.checks.disabledOverviewStaysHidden = !Main.overview.visible;
    assert(!Main.overview.visible, 'Panorama desabilitado abriu');

    // Ausência do launcher não pode derrubar o Shell.
    settings({super_launcher: true});
    global.display.emit('overlay-key');
    await Scripting.sleep(400);
    report.checks.superWithoutLauncherShellSurvived = true;

    const mapped = [];
    const signal = global.window_manager.connect('map', (_manager, actor) => {
        const window = actor.meta_window;
        if (window.get_gtk_application_id() === 'org.spot.Launcher') {
            const frame = window.get_frame_rect();
            mapped.push({x: frame.x, y: frame.y, width: frame.width, height: frame.height,
                clientType: window.get_client_type()});
        }
    });
    settings({pointer_monitor: true});
    const launcher = new Gio.SubprocessLauncher({flags: Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE});
    launcher.setenv('GDK_BACKEND', 'wayland', true);
    launcher.setenv('GSK_RENDERER', 'cairo', true);
    const root = GLib.getenv('SPOT_AUDIT_ROOT');
    const sample = GLib.getenv('SPOT_AUDIT_OUTPUT') + '.client.json';
    const process = launcher.spawnv(['python3', '-B', root + '/docs/auditoria/medir-interface.py', 'startup', sample]);
    await new Promise((resolve, reject) => process.communicate_utf8_async(null, null, (child, result) => {
        try {
            const [, stdout, stderr] = child.communicate_utf8_finish(result);
            report.checks.clientExit = child.get_exit_status();
            report.checks.clientLog = (stdout + stderr).slice(-2000);
            resolve();
        } catch (error) {
            reject(error);
        }
    }));
    global.window_manager.disconnect(signal);
    report.checks.waylandMap = mapped;
    assert(mapped.length > 0 && report.checks.clientExit === 0, 'Cliente Wayland não mapeou');

    // Lifecycle real pelo gerenciador, incluindo seu mecanismo de rebase.
    settings({});
    memory('before_cycles');
    const exports = [];
    for (let i = 0; i < 200; i++) {
        exports.push(new WeakRef(instance.placement));
        await Main.extensionManager._callExtensionDisableWithRebase(uuid);
        assert(Main.overview.show === originalShow, 'disable não restaurou panorama');
        await Main.extensionManager._callExtensionEnable(uuid);
        if ([49, 99, 199].includes(i)) {
            await Scripting.sleep(250);
            memory(`after_${i + 1}_cycles`);
        }
    }
    await Scripting.sleep(2000);
    memory('after_settle');
    report.checks.oldExportsAlive = exports.filter(reference => reference.deref()).length;
    report.checks.enableDisableCycles = 200;
    await Main.extensionManager._callExtensionDisableWithRebase(uuid);
    report.checks.restoredOverview = Main.overview.show === originalShow;
    report.checks.disconnectedOverlay = !GObject.signal_handler_is_connected(global.display, instance.overlay);
    report.checks.disconnectedMap = !GObject.signal_handler_is_connected(global.window_manager, instance.mapId);
    assert(report.checks.disconnectedOverlay && report.checks.disconnectedMap, 'Sinais não desconectados');
    global.display.emit('overlay-key');
    await Scripting.sleep(700);
    report.checks.superAfterDisable = Main.overview.visible;
    assert(Main.overview.visible, 'Super não restaurado após disable');
    Main.overview.hide();
    const otherUuid = 'audit-hook@spot.invalid';
    const manager = Main.extensionManager;
    await manager._callExtensionEnable(otherUuid);
    assert(manager.lookup(otherUuid)?.stateObj, 'Fixture concorrente não carregou');
    await manager._callExtensionEnable(uuid);
    await manager._callExtensionDisableWithRebase(otherUuid);
    assert(instance.show === originalShow, 'Rebase perdeu método original com Spot ativo');
    await manager._callExtensionEnable(otherUuid);
    await manager._callExtensionDisableWithRebase(uuid);
    assert(Main.overview.show === manager.lookup(otherUuid).stateObj.wrapper,
        'Desativar Spot removeu hook concorrente');
    Main.overview.show();
    assert(global.__spotAuditOtherCalls > 0, 'Hook concorrente não executou');
    await manager._callExtensionDisableWithRebase(otherUuid);
    assert(Main.overview.show === originalShow, 'Método original não restaurado ao fim');
    Main.overview.hide();
    delete global.__spotAuditOtherCalls;
    report.checks.competingOverviewHookRebase = true;
    save();
}
