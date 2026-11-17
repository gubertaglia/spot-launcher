import os
from types import SimpleNamespace
import unittest

from src.scaled_layout import ScaledLayout, Gtk
from src.window import Adw, LauncherWindow


@unittest.skipUnless(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'), 'GTK display unavailable')
class ScaledLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check():
            raise unittest.SkipTest('GTK display unavailable')

    def test_app_descriptions_are_bounded_and_do_not_expose_desktop_ids(self):
        for description in ('', 'Long <description> & details ' * 12):
            app = SimpleNamespace(name='Horizon', description=description,
                                  id='org.example.Horizon.desktop', icon_name='application-x-executable')
            row = LauncherWindow._match_row(None, SimpleNamespace(entry=app))
            self.assertEqual(row.get_title_lines(), 1)
            self.assertEqual(row.get_subtitle_lines(), 1)
            self.assertNotIn(app.id, row.get_subtitle())
            self.assertEqual(row.get_tooltip_text(), app.name + ('\n' + description if description else ''))
            if not description:
                self.assertEqual(row.get_subtitle(), '')

    def test_result_viewport_reserves_full_rows_when_growing_and_shrinking(self):
        LauncherWindow._apply_css(None)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.START,
                       css_classes=['spotlight-card'])
        results = Gtk.ListBox(css_classes=['results-list'])
        scroll = Gtk.ScrolledWindow(propagate_natural_height=True, max_content_height=420,
                                   hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(results)
        card.append(scroll)
        content = Gtk.Box()
        content.append(card)
        layout = ScaledLayout()
        content.set_layout_manager(layout)
        window = SimpleNamespace(config={'max_results': 3}, list_box=results, scrolled_window=scroll)
        for scale in (.75, 1, 1.25, 2):
            layout.scale = scale
            layout.layout_changed()
            for count in (1, 3, 5, 1):
                while child := results.get_first_child():
                    results.remove(child)
                for index in range(count):
                    row = Adw.ActionRow(title=f'Result {index}', subtitle='Long description ' * 12,
                                        title_lines=1, subtitle_lines=1)
                    results.append(row)
                LauncherWindow._update_result_viewport(window)
                width = round(580 * scale)
                # GTK may allocate the minimum height to a non-resizable window.
                height = content.measure(Gtk.Orientation.VERTICAL, width).minimum
                content.allocate(width, height, -1, None)
                expected = sum(results.get_row_at_index(i).measure(Gtk.Orientation.VERTICAL, 500).natural
                               for i in range(min(count, 3)))
                self.assertGreaterEqual(scroll.get_height(), expected)
                adjustment = scroll.get_vadjustment()
                self.assertEqual(adjustment.get_upper() > adjustment.get_page_size(), count > 3)

    def test_results_grow_and_shrink_without_clipping_at_each_scale(self):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card.set_size_request(580, -1)
        card.append(Gtk.Label(label='Search'))
        results = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scroll = Gtk.ScrolledWindow(propagate_natural_height=True, max_content_height=420,
                                   hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(results)
        card.append(scroll)
        content = Gtk.Box()
        content.append(card)
        layout = ScaledLayout()
        content.set_layout_manager(layout)
        allocated = []
        layout.after_allocate = lambda: allocated.append(True)
        for scale in (.75, 1, 1.25, 2):
            layout.scale = scale
            layout.layout_changed()
            for count in (1, 4, 7, 1):
                while child := results.get_first_child():
                    results.remove(child)
                for index in range(count):
                    row = Gtk.Label(label=f'Result {index}', height_request=50)
                    results.append(row)
                width = round(580 * scale)
                height = content.measure(Gtk.Orientation.VERTICAL, width).natural
                content.allocate(width, height, -1, None)
                self.assertGreaterEqual(scroll.get_height(), min(count * 50, 420))
                self.assertEqual(card.get_width(), 580)
                self.assertEqual(allocated, [True])
                self.assertAlmostEqual(height / scale, 18 + min(count * 50, 420), delta=3)
