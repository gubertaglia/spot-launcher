"""Ações locais usando os controles fornecidos pelo desktop Linux."""
from dataclasses import dataclass
import os
import shutil
from pathlib import Path

from gi.repository import Gio, GLib
from src import _
from src.tools import normalize_text
from src.search import search_score, search_text


@dataclass(frozen=True)
class SystemAction:
    title: str
    subtitle: str
    icon: str
    command: tuple
    confirm: bool = False
    score: float = 0.0


def system_actions(query):
    query = normalize_text(query)
    if not query:
        return []
    if any(term in query for term in ("spot", "launcher")) and any(
        term in query for term in ("reiniciar", "restart", "reset", "reboot", "redemarrer", "fechar", "close", "sair", "quit", "cerrar", "fermer", "quitter")
    ):
        return []
    caffeine_score = max(search_score(query, alias) for alias in ("caffeine", "cafeina"))
    if caffeine_score:
        for root in (Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")), Path('/usr/share')):
            directory = root / 'gnome-shell/extensions/caffeine@patapon.info/schemas'
            if not (directory / 'gschemas.compiled').exists():
                continue
            source = Gio.SettingsSchemaSource.new_from_directory(str(directory), Gio.SettingsSchemaSource.get_default(), False)
            schema = source.lookup('org.gnome.shell.extensions.caffeine', False)
            if schema and schema.has_key('cli-toggle'):
                settings = Gio.Settings.new_full(schema, None, None)
                enabled = settings.get_boolean('cli-toggle')
                actions = [SystemAction('Caffeine', _("Desativar Caffeine") if enabled else _("Ativar Caffeine"),
                                        'caffeine-cup-full-symbolic',
                                        ('gsettings', '--schemadir', str(directory), 'set',
                                         'org.gnome.shell.extensions.caffeine', 'cli-toggle',
                                         'false' if enabled else 'true'), score=caffeine_score)]
                if schema.has_key('duration-timer-list') and schema.has_key('duration-timer'):
                    durations = settings.get_value('duration-timer-list').unpack()
                    for index, seconds in enumerate((*durations, 0)):
                        label = _('Ativar Caffeine por tempo ilimitado') if seconds == 0 else _(
                            'Ativar Caffeine por %(duration)s min') % {'duration': seconds // 60}
                        actions.append(SystemAction(
                            label, _('Selecionar duração e ativar Caffeine'),
                            'caffeine-cup-full-symbolic',
                            ('caffeine-timer', str(directory), str(index)), score=caffeine_score))
                return actions
        return []
    actions = (
        (_("Configurações do sistema"), _("Abrir as preferências do desktop"),
         "preferences-system-symbolic", "configuracoes do sistema|system settings|configuracion del sistema|parametres du systeme",
         (("gnome-control-center",), ("systemsettings",), ("xfce4-settings-manager",), ("cinnamon-settings",), ("mate-control-center",)), False),
        (_("Forçar encerramento (Force Quit)"), _("Escolha um processo no monitor do sistema para encerrá-lo"),
         "application-exit-symbolic", "force quit|forcar encerramento|encerrar processo|monitor do sistema|task manager|forzar cierre|forcer a quitter",
         (("gnome-system-monitor",), ("plasma-systemmonitor",), ("xfce4-taskmanager",), ("mate-system-monitor",)), False),
        (_("Bloquear tela"), _("Bloquear a sessão atual"),
         "system-lock-screen-symbolic", "bloquear tela|tela de bloqueio|lock screen|bloquear pantalla|verrouiller l’écran|verrouiller l'ecran|verrouiller",
         (("loginctl", "lock-session"),), False),
        (_("Suspender"), _("Colocar o computador em suspensão"),
         "media-playback-pause-symbolic", "suspender|suspend|sleep|suspension|mettre en veille",
         (("systemctl", "suspend"),), False),
        (_("Reiniciar"), _("Reiniciar o computador"),
         "system-reboot-symbolic", "reiniciar|restart|reboot|redemarrer",
         (("systemctl", "reboot"),), True),
        (_("Desligar"), _("Desligar o computador"),
         "system-shutdown-symbolic", "desligar|shutdown|shut down|power off|apagar|eteindre",
         (("systemctl", "poweroff"),), True),
        (_("Sair da sessão"), _("Encerrar a sessão do desktop"),
         "system-log-out-symbolic", "sair da sessao|logout|log out|encerrar sessao|cerrar sesion|se deconnecter|deconnexion",
         (("gnome-session-quit", "--logout"), ("qdbus6", "org.kde.Shutdown", "/Shutdown", "logout"), ("xfce4-session-logout", "--logout"), ("cinnamon-session-quit", "--logout"), ("mate-session-save", "--logout-dialog")), True),
    )
    desktop = os.getenv("XDG_CURRENT_DESKTOP", "").lower()
    preferred = {"kde": ("systemsettings", "plasma-systemmonitor", "qdbus6"),
                 "xfce": ("xfce4-",), "cinnamon": ("cinnamon-",), "mate": ("mate-",)}
    prefixes = next((prefixes for name, prefixes in preferred.items() if name in desktop), ())
    results = []
    for title, subtitle, icon, aliases, commands, confirm in actions:
        score = max(search_score(query, label) for label in (title, *aliases.split("|")))
        if query in ("sistema", "system", "systeme", "sistema operativo"):
            score = 2050
        if not score:
            continue
        commands = sorted(commands, key=lambda command: not command[0].startswith(prefixes))
        command = next((command for command in commands if shutil.which(command[0])), None)
        if command:
            results.append(SystemAction(title, subtitle, icon, command, confirm, score))
    return sorted(results, key=lambda action: (-action.score, search_text(action.title)))


def execute_action(action, complete):
    """Espera sem bloquear GTK e informa falhas do comando ao usuário."""
    if action.command[0] == 'caffeine-timer':
        try:
            directory, index = action.command[1:]
            source = Gio.SettingsSchemaSource.new_from_directory(
                directory, Gio.SettingsSchemaSource.get_default(), False)
            schema = source.lookup('org.gnome.shell.extensions.caffeine', False)
            settings = Gio.Settings.new_full(schema, None, None)
            enabled = settings.get_boolean('cli-toggle')
            settings.set_int('duration-timer', int(index))
            if enabled:
                settings.set_boolean('cli-toggle', False)
                GLib.timeout_add(100, lambda: (settings.set_boolean('cli-toggle', True), GLib.SOURCE_REMOVE)[1])
            else:
                settings.set_boolean('cli-toggle', True)
            complete(None)
        except Exception as exc:
            complete(str(exc))
        return
    try:
        if action.command[0] not in ("systemctl", "loginctl", "gsettings"):
            Gio.Subprocess.new(action.command, Gio.SubprocessFlags.NONE)
            complete(None)
            return
        process = Gio.Subprocess.new(action.command, Gio.SubprocessFlags.STDERR_PIPE)
    except Exception as exc:
        complete(str(exc))
        return

    def finished(process, result):
        try:
            _, _, stderr = process.communicate_utf8_finish(result)
            error = None if process.get_successful() else (stderr or _("O comando do sistema falhou"))
        except Exception as exc:
            error = str(exc)
        complete(error)

    process.communicate_utf8_async(None, None, finished)
