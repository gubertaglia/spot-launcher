from dataclasses import dataclass, field
import time
from typing import List, Optional

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib
from src import _
from src.search import search_text, intent_metadata
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
    is_setting: bool = False
    search_name: str = field(init=False, repr=False)
    search_metadata: str = field(init=False, repr=False)
    search_description: str = field(init=False, repr=False)
    search_aliases: str = field(init=False, repr=False)

    def __post_init__(self):
        self.search_name = search_text(self.name)
        self.search_metadata = search_text(" ".join((self.id, *self.keywords)))
        self.search_description = search_text(self.description)
        self.search_aliases = intent_metadata(self.name + " " + " ".join(self.keywords))


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
            is_setting = (isinstance(app, Gio.DesktopAppInfo)
                          and "X-GNOME-Settings-Panel" in (app.get_categories() or "").split(";")
                          and app.get_show_in() and not app.get_is_hidden())
            if not app.should_show() and not is_setting:
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
                keywords.extend((app.get_string("Keywords") or "").split(";"))
                generic_name = app.get_generic_name()
                if generic_name:
                    keywords.append(generic_name)
                try:
                    desktop = GLib.KeyFile()
                    desktop.load_from_file(app.get_filename(), GLib.KeyFileFlags.KEEP_TRANSLATIONS)
                    for key in desktop.get_keys("Desktop Entry")[0]:
                        base, _, language = key.partition("[")
                        if base not in ("Name", "GenericName", "Keywords"):
                            continue
                        if language and language.rstrip("]").split("_")[0].split("-")[0] not in ("pt", "en", "es", "fr"):
                            continue
                        keywords.extend(desktop.get_string("Desktop Entry", key).split(";"))
                except (GLib.Error, TypeError):
                    pass  # AppInfo metadata remains usable if its file disappeared.

            keywords = list(dict.fromkeys(keyword for keyword in keywords if keyword))
            loaded.append(
                AppEntry(
                    id=app_id,
                    name=name,
                    description=description,
                    icon_name=icon_name,
                    is_terminal=is_terminal,
                    app_info=app,
                    keywords=keywords,
                    is_setting=is_setting,
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
