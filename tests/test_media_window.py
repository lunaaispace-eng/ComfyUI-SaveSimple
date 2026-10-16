"""Audio window maths for the Asset Loader's sound card (media_io.plan_window /
apply_window). Run with ComfyUI's own Python, no ComfyUI needed:

    E:\\ComfyUI-Easy-Install\\python_embeded\\python.exe -m unittest discover -s tests -v
"""

import os
import sys
import unittest

import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from media_io import apply_window, plan_window  # noqa: E402

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


if __name__ == "__main__":
    unittest.main()
