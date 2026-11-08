import os
import unittest

from src.scaled_layout import ScaledLayout, Gtk


@unittest.skipUnless(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'), 'GTK display unavailable')
class ScaledLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check():
            raise unittest.SkipTest('GTK display unavailable')

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
