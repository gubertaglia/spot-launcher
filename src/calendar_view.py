"""Calendário mensal integrado ao launcher."""
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk
from src import _, regional_date_format


class CalendarView(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8, visible=False)
        self.calendar = Gtk.Calendar(hexpand=True, show_week_numbers=True)
        self.calendar.connect("day-selected", self._update_date)
        self.append(self.calendar)

        actions = Gtk.Box(spacing=8)
        today = Gtk.Button(label=_("Hoje"))
        today.connect("clicked", lambda button: self.select_today())
        actions.append(today)
        self.date_label = Gtk.Label(hexpand=True)
        actions.append(self.date_label)
        self.copy_button = Gtk.Button(label=_("Copiar data"))
        self.copy_button.connect("clicked", lambda button: self.copy_date())
        actions.append(self.copy_button)
        self.append(actions)
        self._update_date()

    def select_today(self):
        self.calendar.select_day(GLib.DateTime.new_now_local())
        self._update_date()

    def _update_date(self, *args):
        # O sinal também pode ocorrer durante a criação do widget.
        if hasattr(self, "date_label"):
            self.date_label.set_label(self.calendar.get_date().format(regional_date_format()))
            self.copy_button.set_label(_("Copiar data"))

    def copy_date(self):
        text = self.calendar.get_date().format(regional_date_format())
        Gdk.Display.get_default().get_clipboard().set(text)
        self.copy_button.set_label(_("Data copiada"))
