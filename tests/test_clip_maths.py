"""Video clip maths for the Asset Loader's video card (media_io): which source
frames make up the clip at a new frame rate, how a frame is fitted to a size,
which frame counts a model accepts, and what a clip costs in memory.

    E:\\ComfyUI-Easy-Install\\python_embeded\\python.exe -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from media_io import clip_bytes, fit_box, grid_frames, pick_frames  # noqa: E402


def times(fps: float, seconds: float):
    return [i / fps for i in range(int(round(fps * seconds)))]


class PickFramesTests(unittest.TestCase):
    def test_same_rate_takes_every_frame(self):
        self.assertEqual(pick_frames(times(24, 2), 24, 0.0, 24), list(range(24)))

    def test_30_to_24_drops_one_frame_in_five(self):
        idx = pick_frames(times(30, 2), 24, 0.0, 24)
        self.assertEqual(len(idx), 24)
        self.assertEqual(idx[:6], [0, 1, 2, 3, 5, 6])   # source 4 (0.133 s) skipped
        self.assertEqual(idx, sorted(idx))

    def test_12_to_24_holds_each_frame_twice(self):
        self.assertEqual(pick_frames(times(12, 1), 24, 0.0, 6), [0, 0, 1, 1, 2, 2])

    def test_start_skips_earlier_frames(self):
        self.assertEqual(pick_frames(times(24, 4), 24, 1.0, 3), [24, 25, 26])

    def test_runs_out_rather_than_inventing_frames(self):
        self.assertEqual(len(pick_frames(times(24, 1), 24, 0.5, 50)), 12)


class FitBoxTests(unittest.TestCase):
    def test_crop_fills_and_centres(self):
        # 1920x1080 -> 1344x768: scale to cover (1365x768), cut 10 px each side
        self.assertEqual(fit_box(1920, 1080, 1344, 768, "crop"), (1365, 768, 10, 0))

    def test_pad_fits_inside_and_centres(self):
        self.assertEqual(fit_box(1920, 1080, 1344, 768, "pad"), (1344, 756, 0, 6))

    def test_stretch_ignores_aspect(self):
        self.assertEqual(fit_box(1920, 1080, 1344, 768, "stretch"), (1344, 768, 0, 0))


class GridTests(unittest.TestCase):
    def test_free_keeps_the_count(self):
        self.assertEqual(grid_frames(120, "free"), 120)

    def test_h3_snaps_to_nearest_17k_plus_5(self):
        self.assertEqual(grid_frames(120, "h3"), 124)
        self.assertEqual(grid_frames(40, "h3"), 39)

    def test_ltx_snaps_to_nearest_8k_plus_1(self):
        self.assertEqual(grid_frames(120, "ltx"), 121)
        self.assertEqual(grid_frames(1, "ltx"), 1)


class MemoryTests(unittest.TestCase):
    def test_fp16_clip_of_39_frames_at_1344x768(self):
        self.assertEqual(clip_bytes(39, 1344, 768, "fp16"), 39 * 1344 * 768 * 3 * 2)

    def test_fp32_is_twice_fp16(self):
        self.assertEqual(clip_bytes(10, 100, 100, "fp32"), 2 * clip_bytes(10, 100, 100, "fp16"))


if __name__ == "__main__":
    unittest.main()
