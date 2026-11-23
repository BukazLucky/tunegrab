"""Draws assets/logo.png and assets/icon.ico (run once: python tools/make_icon.py)."""
from pathlib import Path
from PIL import Image, ImageDraw

S = 1024
out = Path(__file__).resolve().parent.parent / "assets"
out.mkdir(exist_ok=True)

# vertical gradient violet -> pink inside a rounded square
grad = Image.new("RGB", (S, S))
top, bot = (124, 108, 255), (236, 92, 178)
d = ImageDraw.Draw(grad)
for y in range(S):
    k = y / (S - 1)
    d.line([(0, y), (S, y)], fill=tuple(int(top[i] + (bot[i] - top[i]) * k) for i in range(3)))
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([40, 40, S - 40, S - 40], radius=230, fill=255)
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
img.paste(grad, (0, 0), mask)

w = ImageDraw.Draw(img)
white = (255, 255, 255, 255)
# music note: two heads + stems + beam
w.ellipse([250, 640, 430, 780], fill=white)
w.ellipse([560, 580, 740, 720], fill=white)
w.rectangle([392, 330, 430, 720], fill=white)
w.rectangle([702, 270, 740, 660], fill=white)
w.polygon([(392, 330), (740, 270), (740, 370), (392, 430)], fill=white)

img.save(out / "logo.png")
img.save(out / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("ok")
