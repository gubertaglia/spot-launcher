"""Read and restore launcher positions on X11 and XWayland."""
from ctypes import CDLL, POINTER, byref, c_char_p, c_int, c_uint, c_ulong, c_void_p
from functools import lru_cache


@lru_cache(maxsize=1)
def _x11():
    lib = CDLL("libX11.so.6")
    lib.XOpenDisplay.argtypes = [c_char_p]
    lib.XOpenDisplay.restype = c_void_p
    lib.XDefaultRootWindow.argtypes = [c_void_p]
    lib.XDefaultRootWindow.restype = c_ulong
    lib.XTranslateCoordinates.argtypes = [
        c_void_p, c_ulong, c_ulong, c_int, c_int, POINTER(c_int), POINTER(c_int), POINTER(c_ulong),
    ]
    lib.XQueryPointer.argtypes = [
        c_void_p, c_ulong, POINTER(c_ulong), POINTER(c_ulong),
        POINTER(c_int), POINTER(c_int), POINTER(c_int), POINTER(c_int), POINTER(c_uint),
    ]
    lib.XMoveWindow.argtypes = [c_void_p, c_ulong, c_int, c_int]
    lib.XCloseDisplay.argtypes = [c_void_p]
    return lib


def position(window, target=None):
    surface = window.get_surface()
    if not surface or not hasattr(surface, "get_xid"):
        return None
    lib = _x11()
    display = lib.XOpenDisplay(surface.get_display().get_name().encode())
    if not display:
        return None
    try:
        xid = surface.get_xid()
        if target is None:
            x, y, child = c_int(), c_int(), c_ulong()
            if lib.XTranslateCoordinates(display, xid, lib.XDefaultRootWindow(display),
                                         0, 0, byref(x), byref(y), byref(child)):
                return [x.value, y.value]
        elif (isinstance(target, list) and len(target) == 2
              and all(type(n) is int and -32768 <= n <= 32767 for n in target)):
            # Discard a saved location if its monitor was disconnected.
            monitors = surface.get_display().get_monitors()
            for monitor in monitors:
                rect = monitor.get_geometry()
                scale = monitor.get_scale_factor()
                if (rect.x * scale <= target[0] + 24 < (rect.x + rect.width) * scale
                        and rect.y * scale <= target[1] + 24 < (rect.y + rect.height) * scale):
                    lib.XMoveWindow(display, xid, *target)
                    break
    finally:
        lib.XCloseDisplay(display)
    return None



def hide_from_dock(window):
    """Set taskbar hints when the native X11 surface becomes available."""
    surface = window.get_surface()
    if surface and hasattr(surface, "set_skip_taskbar_hint"):
        surface.set_skip_taskbar_hint(True)
        surface.set_skip_pager_hint(True)


def default_position(window, saved=None):
    surface = window.get_surface()
    if not surface or not hasattr(surface, "get_xid"):
        return None
    display = surface.get_display()
    monitor = display.get_monitor_at_surface(surface)
    lib = _x11()
    connection = lib.XOpenDisplay(display.get_name().encode())
    if connection:
        try:
            root, child = c_ulong(), c_ulong()
            x, y, local_x, local_y, mask = c_int(), c_int(), c_int(), c_int(), c_uint()
            if lib.XQueryPointer(connection, lib.XDefaultRootWindow(connection),
                                 byref(root), byref(child), byref(x), byref(y),
                                 byref(local_x), byref(local_y), byref(mask)):
                for candidate in display.get_monitors():
                    rect = candidate.get_geometry()
                    scale = candidate.get_scale_factor()
                    if (rect.x * scale <= x.value < (rect.x + rect.width) * scale
                            and rect.y * scale <= y.value < (rect.y + rect.height) * scale):
                        monitor = candidate
                        break
        finally:
            lib.XCloseDisplay(connection)
    if not monitor:
        return None
    rect = monitor.get_geometry()
    scale = monitor.get_scale_factor()
    if (isinstance(saved, list) and len(saved) == 2 and all(type(n) is int for n in saved)
            and rect.x * scale <= saved[0] < (rect.x + rect.width) * scale
            and rect.y * scale <= saved[1] < (rect.y + rect.height) * scale):
        return saved
    return [int((rect.x + max(0, (rect.width - window.get_width()) / 2)) * scale),
            int((rect.y + max(0, rect.height * 0.35 - window.get_height() / 2)) * scale)]


def gnome_placement(old_size=(0, 0)):
    """Ask the Shell extension to place native Wayland windows without blocking GTK."""
    from gi.repository import Gio, GLib
    def complete(connection, result):
        try:
            connection.call_finish(result)
        except GLib.Error:
            pass  # The compositor owns placement when the optional extension is unavailable.
    try:
        connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except GLib.Error:
        return
    connection.call(
        'org.gnome.Shell', '/org/spot/Launcher/Integration', 'org.spot.Launcher.Integration',
        'Place', GLib.Variant('(ii)', old_size), None, Gio.DBusCallFlags.NONE, 1000, None, complete)
