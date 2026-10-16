"""Shot timeline rules for the Asset Loader (asset_timeline.py): which H3 tag each
reference really gets, and whether every placement fits inside the shot.

    E:\\ComfyUI-Easy-Install\\python_embeded\\python.exe -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from asset_timeline import (check_placements, h3_tags, newest_video, shot_frames, tail_start,  # noqa: E402
                            target_fps, target_grid)


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


class TargetTests(unittest.TestCase):
    def test_frame_rate_per_target(self):
        self.assertEqual(target_fps("h3", 30.0), 24.0)
        self.assertEqual(target_fps("ltx", 30.0), 25.0)
        self.assertEqual(target_fps("general", 29.97), 29.97)

    def test_grid_per_target(self):
        self.assertEqual(target_grid("h3"), "h3")
        self.assertEqual(target_grid("ltx"), "ltx")
        self.assertEqual(target_grid("general"), "free")

    def test_ltx_clip_guides_start_at_0_or_8k_plus_1(self):
        self.assertEqual(check_placements(121, [("V1", 0, 17), ("V2", 33, 17)], "ltx"), [])
        errs = check_placements(121, [("V1", 30, 17)], "ltx")
        self.assertEqual(len(errs), 1)
        self.assertIn("25 or 33", errs[0])

    def test_ltx_single_frames_go_anywhere(self):
        self.assertEqual(check_placements(121, [("P1", 30, 1)], "ltx"), [])


class ShotLengthTests(unittest.TestCase):
    def test_wired_seconds_win(self):
        self.assertEqual(shot_frames(124 / 24, 200), 124)

    def test_unwired_uses_the_stored_length(self):
        self.assertEqual(shot_frames(None, 192), 192)
        self.assertEqual(shot_frames(0, 192), 192)


class ContinuationTests(unittest.TestCase):
    def test_newest_video_wins_and_other_files_are_ignored(self):
        files = [("shot_001.mp4", 100.0), ("shot_002.mp4", 300.0), ("shot_002.txt", 900.0), ("still.png", 800.0)]
        self.assertEqual(newest_video(files), "shot_002.mp4")

    def test_no_video_gives_none(self):
        self.assertIsNone(newest_video([("notes.txt", 1.0)]))

    def test_tail_starts_n_frames_before_the_end(self):
        # 124 frames at 24 fps = 5.1667 s; the last 22 start at frame 102 = 4.25 s
        self.assertAlmostEqual(tail_start(124 / 24, 24, 22), 102 / 24)

    def test_tail_ends_on_the_last_source_frame(self):
        # 12.4 s at 30 fps: the last frame is at 12.3667 s; 22 frames at 24 fps must
        # put their last sample exactly there, so the cut joins the very last image.
        start = tail_start(12.4, 24, 22, 30)
        self.assertAlmostEqual(start + 21 / 24, 12.4 - 1 / 30)

    def test_tail_of_a_short_clip_starts_at_zero(self):
        self.assertEqual(tail_start(0.5, 24, 22), 0.0)


if __name__ == "__main__":
    unittest.main()
