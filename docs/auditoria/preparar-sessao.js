// Mantém o panorama fechado para medir uma janela desocluída no display isolado.
import GLib from 'gi://GLib';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as Scripting from 'resource:///org/gnome/shell/ui/scripting.js';

export const METRICS = {};

export async function run() {
    if (GLib.getenv('SPOT_AUDIT_ISOLATED') !== '1')
        throw new Error('Sessão não isolada');
    Main.overview.hide();
    await Scripting.sleep(700);
    GLib.file_set_contents(GLib.getenv('SPOT_AUDIT_READY'), 'ready');
    while (true)
        await Scripting.sleep(500);
}
