"""Ações locais usando os controles fornecidos pelo desktop Linux."""
from dataclasses import dataclass
import os
import shutil

from gi.repository import Gio
from src import _
from src.tools import normalize_text


@dataclass(frozen=True)
class SystemAction:
    title: str
    subtitle: str
    icon: str
    command: tuple
    confirm: bool = False


def system_actions(query):
    query = normalize_text(query)
    if not query:
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
        if query not in ("sistema", "system", "systeme", "sistema operativo") and not any(
            query in normalize_text(label) for label in (title, *aliases.split("|"))
        ):
            continue
        commands = sorted(commands, key=lambda command: not command[0].startswith(prefixes))
        command = next((command for command in commands if shutil.which(command[0])), None)
        if command:
            results.append(SystemAction(title, subtitle, icon, command, confirm))
    return results


def execute_action(action, complete):
    """Espera sem bloquear GTK e informa falhas do comando ao usuário."""
    try:
        if action.command[0] not in ("systemctl", "loginctl"):
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
