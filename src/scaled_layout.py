"""Scale a single child while preserving GTK's dynamic size negotiation."""
from math import ceil
import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gsk


class ScaledLayout(Gtk.LayoutManager):
    scale = 1.0
    after_allocate = None

    def do_get_request_mode(self, widget):
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_measure(self, widget, orientation, for_size):
        size = -1 if for_size < 0 else round(for_size / self.scale)
        minimum, natural, _, _ = widget.get_first_child().measure(orientation, size)
        return ceil(minimum * self.scale), ceil(natural * self.scale), -1, -1

    def do_allocate(self, widget, width, height, baseline):
        widget.get_first_child().allocate(round(width / self.scale), round(height / self.scale),
                                          -1, Gsk.Transform().scale(self.scale, self.scale))
        if self.after_allocate:
            callback, self.after_allocate = self.after_allocate, None
            callback()
