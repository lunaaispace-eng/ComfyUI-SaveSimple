"""Shot timeline rules for the Asset Loader (asset_timeline.py): which H3 tag each
reference really gets, and whether every placement fits inside the shot.

    E:\\ComfyUI-Easy-Install\\python_embeded\\python.exe -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from asset_timeline import check_placements, h3_tags, shot_frames  # noqa: E402


class TagTests(unittest.TestCase):
    def test_only_references_are_numbered_and_in_card_order(self):
        # cards 1 and 3 sit on the shot; 2 and 4 are references -> <Picture 1>, <Picture 2>
        t = h3_tags(["key", "ref", "key", "ref"], [], [])
        self.assertEqual(t["pictures"], {1: "<Picture 1>", 3: "<Picture 2>"})

    def test_soundtracks_come_before_standalone_sounds(self):
        clips = [{"role": "ref", "sound": True}, {"role": "ref", "sound": False}, {"role": "guide", "sound": True}]
        t = h3_tags([], clips, ["lock", "ref", "ref"])
        self.assertEqual(t["videos"], {0: "<Video 1>", 1: "<Video 2>"})
        self.assertEqual(t["video_audio"], {0: "<Audio 1>"})          # clip 2 has none; clip 3 is on the shot
        self.assertEqual(t["sounds"], {1: "<Audio 2>", 2: "<Audio 3>"})  # the locked song is no reference

    def test_nothing_referenced_gives_empty_maps(self):
        t = h3_tags(["key"], [{"role": "guide", "sound": True}], ["lock"])
        self.assertEqual(t, {"pictures": {}, "videos": {}, "video_audio": {}, "sounds": {}})


class PlacementTests(unittest.TestCase):
    def test_everything_inside_the_shot_passes(self):
        self.assertEqual(check_placements(124, [("<P1>", 0, 1), ("V1", 34, 39), ("P3", 123, 1)]), [])

    def test_a_clip_that_runs_past_the_end_is_named(self):
        errs = check_placements(124, [("V1", 100, 39)])
        self.assertEqual(len(errs), 1)
        self.assertIn("V1", errs[0])
        self.assertIn("100", errs[0])

    def test_a_frame_past_the_last_is_refused(self):
        self.assertEqual(len(check_placements(124, [("P1", 124, 1)])), 1)


class ShotLengthTests(unittest.TestCase):
    def test_wired_seconds_win(self):
        self.assertEqual(shot_frames(124 / 24, 200), 124)

    def test_unwired_uses_the_stored_length(self):
        self.assertEqual(shot_frames(None, 192), 192)
        self.assertEqual(shot_frames(0, 192), 192)


if __name__ == "__main__":
    unittest.main()
