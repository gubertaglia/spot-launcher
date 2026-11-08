from dataclasses import dataclass, field
import time
from typing import List, Optional

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio
from src import _
from src.terminal import get_default_terminal


@dataclass
class AppEntry:
    id: str
    name: str
    description: str
    icon_name: str
    is_terminal: bool
    app_info: Gio.AppInfo
    keywords: List[str] = field(default_factory=list)


class AppIndexer:

    def __init__(self):
        self._apps: List[AppEntry] = []
        self._monitor = Gio.AppInfoMonitor.get()
        # Escuta se novos programas foram instalados enquanto o app roda
        self._monitor.connect("changed", self._on_system_apps_changed)
        self.reload()

    def reload(self) -> float:
        """Lê todos os aplicativos do sistema e Flatpaks em memória.

        Retorna o tempo gasto em milissegundos.
        """
        start = time.perf_counter()
        all_apps = Gio.AppInfo.get_all()

        loaded: List[AppEntry] = []
        for app in all_apps:
            # Ignora apps que o sistema marca para não exibir (NoDisplay=true ou OnlyShowIn)
            if not app.should_show():
                continue

            # Nome e descrição já chegam automaticamente no idioma do sistema (ex: Português)
            name = app.get_name() or ""
            description = app.get_description() or ""
            app_id = app.get_id() or ""

            # Resolução do ícone do sistema
            icon = app.get_icon()
            icon_name = (
                icon.to_string()
                if icon
                else "application-x-executable-symbolic"
            )

            # Detecta se é um app que precisa de terminal (ex: htop)
            is_terminal = False
            keywords: List[str] = []
            if isinstance(app, Gio.DesktopAppInfo):
                is_terminal = app.get_boolean("Terminal")
                raw_keywords = app.get_keywords()
                if raw_keywords:
                    keywords = list(raw_keywords)

            loaded.append(
                AppEntry(
                    id=app_id,
                    name=name,
                    description=description,
                    icon_name=icon_name,
                    is_terminal=is_terminal,
                    app_info=app,
                    keywords=keywords,
                )
            )

        self._apps = loaded
        elapsed_ms = (time.perf_counter() - start) * 1000
        return elapsed_ms

    def get_apps(self) -> List[AppEntry]:
        """Retorna a lista atual de aplicativos indexados."""
        return self._apps

    def launch(self, entry: AppEntry) -> bool:
        """Executa o aplicativo de forma limpa pelo sistema operacional."""
        try:
            if entry.is_terminal:
                terminal_cmd = get_default_terminal()
                if terminal_cmd:
                    exec_line = entry.app_info.get_commandline()
                    full_cmd = " ".join(terminal_cmd + [exec_line])
                    Gio.AppInfo.create_from_commandline(
                        full_cmd, None, Gio.AppInfoCreateFlags.NONE
                    ).launch()
                    return True

            # Disparo padrão com suporte a cgroups e Wayland
            return entry.app_info.launch()
        except Exception as e:
            print(f"[Erro ao disparar {entry.name}]: {e}")
            return False

    def _on_system_apps_changed(self, monitor):
        """Disparado automaticamente quando um Flatpak ou RPM é instalado."""
        print("[Indexer] Aplicativos do sistema alterados. Reindexando...")
        self.reload()
