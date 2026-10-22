"""Write a test clip for the video nodes: each frame shows its own number (big digits
on a colour that changes per frame) and the sound is a 440 Hz tone, so a loaded
batch can be checked frame by frame and the sound length to the sample.

    E:\\ComfyUI-Easy-Install\\python_embeded\\python.exe tests\\make_test_clip.py OUT.mp4 [w h fps seconds]

Default: 1920x1080, 30 fps, 6 s, stereo 48 kHz AAC.
"""

import sys

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def main(out, w=1920, h=1080, fps=30, seconds=6.0):
    w, h, fps, seconds = int(w), int(h), int(fps), float(seconds)
    n = int(round(fps * seconds))
    sr = 48000
    try:
        font = ImageFont.truetype("arial.ttf", h // 3)
    except OSError:
        font = ImageFont.load_default()
    with av.open(out, "w") as c:
        vs = c.add_stream("libx264", rate=fps)
        vs.width, vs.height, vs.pix_fmt = w, h, "yuv420p"
        aus = c.add_stream("aac", rate=sr)
        aus.layout = "stereo"
        for i in range(n):
            img = Image.new("RGB", (w, h), ((i * 37) % 256, (i * 91) % 256, (i * 53) % 256))
            ImageDraw.Draw(img).text((w // 10, h // 3), str(i), fill=(255, 255, 255), font=font)
            for p in vs.encode(av.VideoFrame.from_image(img)):
                c.mux(p)
        for p in vs.encode():
            c.mux(p)
        t = np.arange(int(sr * seconds)) / sr
        tone = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        step = 1024
        for k in range(0, len(tone), step):
            chunk = np.stack([tone[k:k + step]] * 2)
            frame = av.AudioFrame.from_ndarray(chunk, format="fltp", layout="stereo")
            frame.sample_rate = sr
            frame.pts = k
            for p in aus.encode(frame):
                c.mux(p)
        for p in aus.encode():
            c.mux(p)
    print(f"{out}: {n} frames {w}x{h} @ {fps} fps, {seconds} s, tone 440 Hz")


if __name__ == "__main__":
    main(*sys.argv[1:])
