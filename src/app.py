import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")

from gi.repository import Adw, Gio, GLib

GLib.set_application_name("SpotLauncher")
GLib.set_prgname("SpotLauncher")


# Filtra os avisos internos inofensivos do Wayland/Gdk
def _silence_gdk_warnings(domain, level, message, user_data):
    if domain == "Gdk" and "frame_timings" in message:
        return
    GLib.log_default_handler(domain, level, message, user_data)


GLib.log_set_handler(
    "Gdk", GLib.LogLevelFlags.LEVEL_WARNING, _silence_gdk_warnings, None
)


class SpotApplication(Adw.Application):

    def __init__(self):
        super().__init__(
            application_id="org.spot.Launcher",
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.indexer = None
        self.window = None
        self.reopen_preferences = False
        self.restart_launcher = False

        # Conecta aos sinais nativos de ciclo de vida (imune a segfaults)
        self.connect("startup", self._on_startup)
        self.connect("activate", self._on_activate)
        self.connect("shutdown", self._on_shutdown)
        self.connect("command-line", self._on_command_line)

    def _on_startup(self, app):
        """Inicializa os módulos e mantém o daemon residente na memória."""
        # Garante que o aplicativo nunca morra mesmo com a janela escondida
        self.hold()

        # Registra a ação D-Bus "toggle" para ser acionada instantaneamente
        toggle_action = Gio.SimpleAction.new("toggle", None)
        toggle_action.connect("activate", self._on_toggle_action)
        self.add_action(toggle_action)

    def _launcher(self):
        if self.window is None:
            from src.indexer import AppIndexer
            from src.window import LauncherWindow

            self.indexer = AppIndexer()
            self.window = LauncherWindow(self, self.indexer)
        return self.window

    def _on_activate(self, app):
        """Disparado se o usuário clicar no ícone do aplicativo no sistema."""
        self._launcher().show_launcher()

    def _on_command_line(self, app, command_line):
        """Controla os argumentos de terminal e de inicialização."""
        args = command_line.get_arguments()

        # Se ligou o PC pelo Autostart: NÃO FAZ NADA VISUAL, fica quieto em segundo plano!
        if "--daemon" in args or "-d" in args:
            self._launcher()
            return 0

        if "--preferences" in args:
            self._launcher().show_launcher()
            self.window.open_preferences()
            return 0

        # Se foi o atalho do teclado
        if "--toggle" in args or "-t" in args:
            self._launcher().toggle_launcher()
        else:
            self._launcher().show_launcher()

        return 0

    def _on_toggle_action(self, action, parameter):
        """Disparado via chamada de atalho nativo D-Bus."""
        self._launcher().toggle_launcher()

    def _on_shutdown(self, app):
        if self.window:
            self.window.close_services()
