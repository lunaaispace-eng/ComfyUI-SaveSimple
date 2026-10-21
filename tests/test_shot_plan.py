"""Luna Shot List's script rules (shot_plan): parsing, chaining starts with an overlap,
grid snapping, JSON, and the errors that name the wrong line.

    E:\\ComfyUI-Easy-Install\\python_embeded\\python.exe -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shot_plan import parse_time, plan_scenes, scene_line, snap  # noqa: E402

SCRIPT = """# a test song
overlap: 22
0:12.00 | 5.17 | the singer walks into the light
        | 124f | close-up on the guitar  # the red one
0:30.5  | 3s   | wide shot, the crowd
"""


class SnapTests(unittest.TestCase):
    def test_h3(self):
        self.assertEqual(snap(120, "h3"), 124)
        self.assertEqual(snap(110, "h3"), 107)
        self.assertEqual(snap(1, "h3"), 5)

    def test_ltx_and_free(self):
        self.assertEqual(snap(100, "ltx"), 97)
        self.assertEqual(snap(77, "free"), 77)


class ParseTests(unittest.TestCase):
    def test_times(self):
        self.assertEqual(parse_time("1:02.5"), 62.5)
        self.assertEqual(parse_time("0:01:02"), 62.0)
        self.assertEqual(parse_time("12s"), 12.0)
        with self.assertRaises(ValueError):
            parse_time("1::2")

    def test_script(self):
        p = plan_scenes(SCRIPT)
        s1, s2, s3 = p["scenes"]
        self.assertEqual((s1["start"], s1["frames"]), (12.0, 124))
        # scene 2 starts 22 frames before scene 1 ends: 12 + 124/24 - 22/24 = 16.25
        self.assertAlmostEqual(s2["start"], 16.25)
        self.assertTrue(s2["auto_start"])
        self.assertEqual(s2["overlap"], 22)
        self.assertEqual(s2["prompt"], "close-up on the guitar  # the red one")
        self.assertEqual((s3["start"], s3["frames"], s3["overlap"]), (30.5, 73, 0))   # 3 s = 72 -> 73
        self.assertEqual(s1["line"], 2)

    def test_overlap_argument_and_first_start(self):
        p = plan_scenes("start: 1:00\n| 5 | a\n| 5 | b", overlap_frames=0)
        self.assertEqual(p["scenes"][0]["start"], 60.0)
        self.assertAlmostEqual(p["scenes"][1]["start"], 60 + 124 / 24)

    def test_json(self):
        p = plan_scenes('{"overlap": 5, "scenes": [{"start": 2, "frames": 39, "prompt": "x"}, {"seconds": 1}]}')
        self.assertEqual(p["scenes"][0]["frames"], 39)
        self.assertAlmostEqual(p["scenes"][1]["start"], 2 + 39 / 24 - 5 / 24)
        self.assertIsNone(p["scenes"][0]["line"])

    def test_ltx_runs_at_25(self):
        p = plan_scenes("0 | 4 | a", grid="ltx")
        self.assertEqual((p["fps"], p["scenes"][0]["frames"]), (25, 97))

    def test_errors_name_the_line(self):
        with self.assertRaisesRegex(ValueError, "line 2"):
            plan_scenes("0 | 5 | a\nnonsense")
        with self.assertRaisesRegex(ValueError, "line 1: length"):
            plan_scenes("0 | five | a")
        with self.assertRaisesRegex(ValueError, "empty"):
            plan_scenes("  ")
        with self.assertRaisesRegex(ValueError, "would not move on"):
            plan_scenes("0 | 5f | a\n | 5f | b", overlap_frames=22)

    def test_line_writer(self):
        self.assertEqual(scene_line("0:12.00", "124f", "a"), "0:12.00  | 124f   | a")


if __name__ == "__main__":
    unittest.main()
