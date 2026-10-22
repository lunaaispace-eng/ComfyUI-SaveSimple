"""Luna Load Video's plan (media_io.plan_load / grid_count): how many frames, at
what rate and size, and what it costs — decided from the file's probe before any
decoding.

    E:\\ComfyUI-Easy-Install\\python_embeded\\python.exe -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from media_io import grid_count, plan_load  # noqa: E402

HD30 = {"width": 1920, "height": 1080, "fps": 30.0, "duration": 12.0, "audio": True}


class GridCountTests(unittest.TestCase):
    def test_h3_nearest(self):
        self.assertEqual(grid_count(120, "h3", 1000), 124)
        self.assertEqual(grid_count(110, "h3", 1000), 107)

    def test_h3_no_trained_cap(self):
        self.assertEqual(grid_count(500, "h3", 1000), 498)   # 17*29+5

    def test_h3_never_past_available(self):
        self.assertEqual(grid_count(124, "h3", 120), 107)
        self.assertEqual(grid_count(10, "h3", 4), 0)

    def test_ltx(self):
        self.assertEqual(grid_count(100, "ltx", 1000), 97)
        self.assertEqual(grid_count(100, "ltx", 90), 89)

    def test_free(self):
        self.assertEqual(grid_count(100, "free", 90), 90)


class PlanLoadTests(unittest.TestCase):
    def test_defaults_load_everything_as_is(self):
        p = plan_load(HD30)
        self.assertEqual((p["frames"], p["fps"], p["width"], p["height"]), (360, 30.0, 1920, 1080))
        self.assertEqual(p["size"], ("source",))
        self.assertAlmostEqual(p["seconds"], 12.0)
        self.assertEqual(p["bytes"], 360 * 1920 * 1080 * 3 * 4)

    def test_start_and_fps(self):
        p = plan_load(HD30, start_s=2.0, fps=24)
        self.assertEqual(p["frames"], 240)   # 10 s left at 24 fps

    def test_frames_capped_by_file_with_note(self):
        p = plan_load(HD30, start_s=10.0, frames=100)
        self.assertEqual(p["frames"], 60)
        self.assertTrue(any("the file has 60" in n for n in p["notes"]))

    def test_h3_grid_forces_24_and_snaps(self):
        p = plan_load(HD30, frames=120, grid="h3")
        self.assertEqual((p["frames"], p["fps"]), (124, 24.0))
        self.assertTrue(any("grid gives 124" in n for n in p["notes"]))

    def test_h3_grid_refuses_other_fps(self):
        with self.assertRaises(ValueError):
            plan_load(HD30, fps=30, grid="h3")

    def test_h3_to_end_snaps_down(self):
        p = plan_load(HD30, grid="h3")   # 12 s * 24 = 288 -> 277
        self.assertEqual(p["frames"], 277)

    def test_one_side_keeps_shape(self):
        p = plan_load(HD30, width=1280)
        self.assertEqual((p["width"], p["height"], p["fit"]), (1280, 720, "stretch"))
        p = plan_load(HD30, height=768)
        self.assertEqual((p["width"], p["height"]), (1364, 768))

    def test_both_sides_box_with_fit(self):
        p = plan_load(HD30, width=1344, height=768, fit="pad")
        self.assertEqual((p["size"], p["fit"]), (("box", 1344, 768), "pad"))

    def test_every_nth_and_fp16_cost(self):
        p = plan_load(HD30, frames=100, nth=3, precision="fp16", width=640, height=360)
        self.assertEqual(p["delivered"], 34)
        self.assertAlmostEqual(p["out_fps"], 10.0)
        self.assertEqual(p["bytes"], 34 * 640 * 360 * 3 * 2)

    def test_start_past_end_refused(self):
        with self.assertRaises(ValueError):
            plan_load(HD30, start_s=12.0)

    def test_unknown_size_refused(self):
        with self.assertRaises(ValueError):
            plan_load({"width": 0, "height": 0, "fps": 30, "duration": 3})


if __name__ == "__main__":
    unittest.main()
