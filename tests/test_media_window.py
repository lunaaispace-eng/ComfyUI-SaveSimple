"""Audio window maths for the Asset Loader's sound card (media_io.plan_window /
apply_window). Run with ComfyUI's own Python, no ComfyUI needed:

    E:\\ComfyUI-Easy-Install\\python_embeded\\python.exe -m unittest discover -s tests -v
"""

import os
import sys
import unittest

import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from media_io import apply_window, plan_window, song_shot_count, song_shot_start  # noqa: E402

SR44, SR48 = 44100, 48000


def ramp(channels: int, length: int) -> torch.Tensor:
    """[C, L] with every sample distinct, so a wrong slice cannot pass by accident."""
    base = torch.arange(length, dtype=torch.float32) + 1.0
    return torch.stack([base * (c + 1) for c in range(channels)])


class PlanWindowTests(unittest.TestCase):
    def test_window_inside_the_file(self):
        p = plan_window(10 * SR44, SR44, 2.0, 3.0)
        self.assertEqual(p, {"start": 2 * SR44, "want": 3 * SR44, "take": 3 * SR44, "fill": 0})

    def test_zero_length_means_to_the_end(self):
        p = plan_window(10 * SR44, SR44, 1.5, 0.0)
        self.assertEqual(p["start"], int(1.5 * SR44))
        self.assertEqual(p["want"], 10 * SR44 - int(1.5 * SR44))
        self.assertEqual(p["fill"], 0)

    def test_window_past_the_end_is_filled(self):
        p = plan_window(10 * SR44, SR44, 8.0, 5.0)
        self.assertEqual(p["take"], 2 * SR44)
        self.assertEqual(p["fill"], 3 * SR44)

    def test_negative_start_is_clamped(self):
        self.assertEqual(plan_window(SR44, SR44, -3.0, 0.5)["start"], 0)

    def test_h3_shot_lengths_are_sample_exact(self):
        # 124 frames at 24 fps = 5.1666… s; both rates divide it exactly.
        self.assertEqual(plan_window(60 * SR48, SR48, 0.0, 124 / 24)["want"], 248000)
        self.assertEqual(plan_window(60 * SR44, SR44, 0.0, 124 / 24)["want"], 227850)


class ApplyWindowTests(unittest.TestCase):
    def test_inside_returns_the_exact_slice(self):
        wav = ramp(2, 1000)
        out = apply_window(wav, {"start": 100, "want": 300, "take": 300, "fill": 0}, "silence")
        self.assertTrue(torch.equal(out, wav[:, 100:400]))

    def test_silence_fills_the_tail_with_zeros(self):
        wav = ramp(2, 1000)
        out = apply_window(wav, {"start": 900, "want": 300, "take": 100, "fill": 200}, "silence")
        self.assertEqual(tuple(out.shape), (2, 300))
        self.assertTrue(torch.equal(out[:, :100], wav[:, 900:]))
        self.assertTrue(torch.equal(out[:, 100:], torch.zeros(2, 200)))

    def test_loop_continues_from_the_start_of_the_file(self):
        wav = ramp(1, 1000)
        out = apply_window(wav, {"start": 900, "want": 300, "take": 100, "fill": 200}, "loop")
        self.assertTrue(torch.equal(out[:, 100:], wav[:, :200]))

    def test_loop_repeats_a_file_shorter_than_the_gap(self):
        wav = ramp(1, 50)
        out = apply_window(wav, {"start": 0, "want": 170, "take": 50, "fill": 120}, "loop")
        self.assertEqual(out.shape[-1], 170)
        self.assertTrue(torch.equal(out[:, 50:100], wav))
        self.assertTrue(torch.equal(out[:, 150:170], wav[:, :20]))


class SongByShotTests(unittest.TestCase):
    """Shot n of a song starts where shot n-1 started plus (shot length - overlap)."""

    SHOT = 124 / 24          # 5.1666… s, H3's default 124-frame shot

    def test_shot_one_starts_at_the_song_start(self):
        self.assertAlmostEqual(song_shot_start(12.0, 1, self.SHOT, 22), 12.0)

    def test_each_shot_advances_by_length_minus_overlap(self):
        # (124 - 22) / 24 = 4.25 s per shot — the mockup's 0:20.50 for shot 3.
        self.assertAlmostEqual(song_shot_start(12.0, 3, self.SHOT, 22), 20.5)
        self.assertAlmostEqual(song_shot_start(12.0, 4, self.SHOT, 22), 24.75)

    def test_no_overlap_means_back_to_back_shots(self):
        self.assertAlmostEqual(song_shot_start(0.0, 2, self.SHOT, 0), self.SHOT)

    def test_count_is_every_shot_that_starts_inside_the_song(self):
        # starts 12.0, 16.25, … ; the last one starting before 178.4 is shot 40
        self.assertEqual(song_shot_count(178.4, 12.0, self.SHOT, 22), 40)
        self.assertLess(song_shot_start(12.0, 40, self.SHOT, 22), 178.4)
        self.assertGreaterEqual(song_shot_start(12.0, 41, self.SHOT, 22), 178.4)

    def test_count_is_zero_when_the_song_starts_past_its_end(self):
        self.assertEqual(song_shot_count(30.0, 31.0, self.SHOT, 22), 0)

    def test_overlap_as_long_as_the_shot_is_refused(self):
        with self.assertRaises(ValueError):
            song_shot_start(0.0, 2, 22 / 24, 22)


if __name__ == "__main__":
    unittest.main()
