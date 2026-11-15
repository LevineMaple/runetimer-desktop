"""Reading real HUD samples and following the last seconds without digits."""
import unittest
from pathlib import Path

from PIL import Image

from pc_janus_reader import JanusTracker, read_observation


FIXTURES = Path(__file__).parent / 'tests' / 'fixtures'


class JanusReaderTests(unittest.TestCase):
    def test_user_icon_with_and_without_time(self):
        for name, seconds in [('janus-3m34.png', 214), ('janus-icon.png', None)]:
            with self.subTest(name=name), Image.open(FIXTURES / name) as image:
                self.assertEqual(read_observation(image), (True, seconds))
                for scale in (1.25, 1.5, 2):
                    scaled = image.resize(tuple(round(n*scale) for n in image.size),
                                          Image.Resampling.BILINEAR)
                    self.assertEqual(read_observation(scaled), (True, seconds))

    def test_unrelated_or_covered_regions(self):
        for color in ('black', 'yellow', '#663799'):
            self.assertEqual(read_observation(Image.new('RGB', (40, 40), color)), (False, None))

    def test_blank_digits_prediction_and_late_extension(self):
        tracker = JanusTracker()
        seq = [(0,8), (1,7), (2,6), (2.8,None), (3,None), (3.5,None),
               (4,74), (5,73), (70,8), (71,7), (72,6), (73,None), (74,None)]
        self.assertEqual([now for now, secs in seq if tracker.update(secs, now)], [3,73])

    def test_stale_six_after_predicted_alert_does_not_rearm(self):
        tracker = JanusTracker()
        seq = [(0,8), (1,7), (2,6), (3,None), (3.1,6), (3.5,None),
               (4,6), (4.2,6), (5,5), (6,4), (7,None)]
        self.assertEqual([t for t,v in seq if tracker.update(v,t)], [3])

    def test_extension_cancels_old_prediction(self):
        tracker = JanusTracker()
        seq = [(0,8), (1,7), (2,6), (2.6,85), (3,None), (4,84), (5,83)]
        self.assertFalse(any([tracker.update(v,t) for t,v in seq]))

    def test_frozen_six_is_not_a_tick_or_an_infinite_prediction(self):
        tracker = JanusTracker()
        seq = [(0,8), (1,7), (2,6)] + [(x,6) for x in range(3,12)] + [(12,None)]
        self.assertFalse(any([tracker.update(v,t) for t,v in seq]))

    def test_covered_icon_blocks_forecast_and_latch_survives_occlusion(self):
        tracker = JanusTracker()
        for now,secs in [(0,8), (1,7), (2,6)]:
            self.assertFalse(tracker.update(secs,now))
        self.assertFalse(tracker.update(None,2.5,icon_present=False))
        self.assertFalse(tracker.update(None,3.0))
        self.assertFalse(tracker.update(4,4))
        self.assertTrue(tracker.update(3,5))
        self.assertFalse(tracker.update(None,5.5,icon_present=False))
        self.assertFalse(tracker.update(2,6))
        self.assertFalse(tracker.update(1,7))

    def test_threshold_skip_and_noise(self):
        tracker = JanusTracker()
        seq = [(0,9), (1,8), (2,7), (2.4,3), (3,6), (5,4), (5.3,79), (6,3)]
        self.assertEqual([t for t,v in seq if tracker.update(v,t)], [5])


if __name__ == '__main__':
    unittest.main()
