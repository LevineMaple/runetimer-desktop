"""Real Tk disclaimer layout and acceptance regression checks.

Run separately with BOOSTER_TEST_PROFILE=high and low. The shared fixture uses
temporary settings, so these checks never change the user's acceptance state.
"""
import unittest
from unittest.mock import Mock, patch

import test_booster_ui as fixture

appmod = fixture.pc_app


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class DisclaimerUITests(unittest.TestCase):
    def setUp(self):
        with patch.object(appmod.PcTimerApp, '_show_startup_splash'), \
                patch.object(appmod.PcTimerApp, '_start_monitor_worker'), \
                patch.object(appmod.PcTimerApp, '_sound_loop'):
            self.app = appmod.PcTimerApp()
        self.callback_errors = []
        self.app.root.report_callback_exception = lambda *error: self.callback_errors.append(error)
        self.app._show_main_window(force_focus=True)
        self.app.root.update()

    def tearDown(self):
        self.app.shutting_down = True
        self.app._booster_audio.stop()
        self.app._halfhour_audio.stop()
        for after_id in self.app.root.tk.call('after', 'info'):
            self.app.root.after_cancel(after_id)
        self.app.root.destroy()

    def settle(self):
        done = appmod.tk.BooleanVar(self.app.root, False)
        self.app.root.after(1150, lambda: done.set(True))
        self.app.root.wait_variable(done)
        self.app.root.update_idletasks()
        self.assertFalse(self.callback_errors, self.callback_errors)

    def check_layout(self, dialog, button_names):
        self.assertGreater(dialog.winfo_width(), 100)
        self.assertTrue(dialog.winfo_viewable())
        self.assertEqual(str(dialog.attributes('-transparentcolor')), '')
        self.assertNotEqual(dialog.cget('bg'), appmod.base.TRANSPARENT)
        children = list(descendants(dialog))
        labels = [w for w in children if isinstance(w, appmod.tk.Label)]
        paragraphs = set(appmod.base.DISCLAIMER_TERMS_PARAGRAPHS)
        body_labels = [w for w in labels if w.cget('text') in paragraphs]
        self.assertEqual(len(body_labels), len(paragraphs))
        for label in body_labels:
            self.assertGreater(label.winfo_width(), 40)
            self.assertLessEqual(float(label.cget('wraplength')), label.winfo_width())
        buttons = {w.text: w for w in children if isinstance(w, appmod.base.RoundedButton)}
        self.assertEqual(set(buttons), set(button_names))
        dx, dy = dialog.winfo_rootx(), dialog.winfo_rooty()
        for button in buttons.values():
            self.assertTrue(button.winfo_viewable())
            self.assertGreaterEqual(button.winfo_rootx(), dx)
            self.assertGreaterEqual(button.winfo_rooty(), dy)
            self.assertLessEqual(button.winfo_rootx()+button.winfo_width(), dx+dialog.winfo_width())
            self.assertLessEqual(button.winfo_rooty()+button.winfo_height(), dy+dialog.winfo_height())
        # Locate the content canvas, excluding the shell and decorative slider.
        canvases = [w for w in children if isinstance(w, appmod.tk.Canvas)
                    and w.cget('scrollregion')]
        self.assertEqual(len(canvases), 1)
        viewport = canvases[0]
        self.assertGreater(viewport.winfo_height(), 40)
        viewport.yview_moveto(0)
        initial = viewport.yview()
        dialog.event_generate('<MouseWheel>', delta=-120)
        self.app.root.update()
        if initial[1] < 1.0:
            self.assertGreater(viewport.yview()[0], initial[0])
        viewport.yview_moveto(1)
        self.app.root.update_idletasks()
        self.assertAlmostEqual(viewport.yview()[1], 1.0)
        viewport.yview_moveto(0)
        self.app.root.update_idletasks()
        return buttons

    def test_readonly_rectangular_layout_and_close(self):
        with patch.object(self.app, '_apply_rounded_window', wraps=self.app._apply_rounded_window) as rounded:
            self.app._show_disclaimer_dialog(readonly=True)
            dialog = self.app.disclaimer_dialog
            self.settle()
            buttons = self.check_layout(dialog, ['닫기'])
            self.assertFalse(any(call.args and call.args[0] is dialog for call in rounded.call_args_list))
            fixture.BoosterUITests().snapshot(dialog, 'disclaimer-readonly')
            buttons['닫기'].command()
            self.assertIsNone(self.app.disclaimer_dialog)
            self.assertFalse(dialog.winfo_exists())

    def test_startup_accept_and_decline(self):
        self.app.root.withdraw()
        self.app.main_app_started = False
        for selected in ('동의', '동의하지 않음'):
            with self.subTest(selected=selected):
                accept, decline = Mock(), Mock()
                self.app._show_disclaimer_dialog(on_accept=accept, on_close=decline)
                dialog = self.app.disclaimer_dialog
                self.settle()
                buttons = self.check_layout(dialog, ['동의', '동의하지 않음'])
                if selected == '동의':
                    fixture.BoosterUITests().snapshot(dialog, 'disclaimer-startup')
                buttons[selected].command()
                self.assertIsNone(self.app.disclaimer_dialog)
                self.assertFalse(dialog.winfo_exists())
                (accept if selected == '동의' else decline).assert_called_once_with()
                (decline if selected == '동의' else accept).assert_not_called()


if __name__ == '__main__':
    unittest.main()
