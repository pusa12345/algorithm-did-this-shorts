"""Render a vertical Short (1080x1920) from a beat script, fully offline.
python3 render.py script.json out.mp4
script.json: {"voice": "am_michael", "beats": [{"say": "...", "big": "28×", "sub": "...", "kind": "hook|stat|text|bars|cta", "bars": [1, 28]}]}
"""
import json, math, subprocess, sys, os, re
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import scipy.io.wavfile as wavfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tts

W, H, FPS = 1080, 1920, 30
BG = (11, 11, 18)
ACC = (198, 255, 61)      # lime
ACC2 = (124, 92, 255)     # violet
WHITE = (245, 245, 250)
DIM = (150, 150, 170)
FB = "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf"
FBOLD = "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf"
FMED = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"
_fc = {}


def font(path, size):
    k = (path, size)
    if k not in _fc:
        _fc[k] = ImageFont.truetype(path, size)
    return _fc[k]


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def back(x):
    x = max(0.0, min(1.0, x)); c = 1.7
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def wrap(draw, text, f, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=f) <= maxw:
            cur = t
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines


def fit_big(draw, text, maxw, start=300, path=FB):
    s = start
    while s > 60:
        f = font(path, s)
        if all(draw.textlength(l, font=f) <= maxw for l in text.split("\n")):
            return f
        s -= 10
    return font(path, 60)


# ---------- background ----------
_glow_cache = {}


def glow(r, color):
    k = (r, color)
    if k not in _glow_cache:
        im = Image.new("RGBA", (r * 2, r * 2), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.ellipse((r * 0.25, r * 0.25, r * 1.75, r * 1.75), fill=color + (90,))
        _glow_cache[k] = im.filter(ImageFilter.GaussianBlur(r * 0.35))
    return _glow_cache[k]


def background(t):
    im = Image.new("RGBA", (W, H), BG + (255,))
    g1 = glow(520, ACC2)
    g2 = glow(420, ACC)
    x1 = int(W * 0.15 + 160 * math.sin(t * 0.35)) - 520
    y1 = int(H * 0.25 + 140 * math.cos(t * 0.28)) - 520
    x2 = int(W * 0.85 + 140 * math.cos(t * 0.31)) - 420
    y2 = int(H * 0.72 + 160 * math.sin(t * 0.22)) - 420
    im.alpha_composite(g1, (x1, y1))
    im.alpha_composite(g2.copy().point(lambda v: v * 0.55) if False else g2, (x2, y2))
    # subtle grid
    d = ImageDraw.Draw(im)
    off = int((t * 20) % 90)
    for y in range(-90 + off, H, 90):
        d.line([(0, y), (W, y)], fill=(255, 255, 255, 10))
    for x in range(0, W, 90):
        d.line([(x, 0), (x, H)], fill=(255, 255, 255, 10))
    return im


# ---------- beat visuals ----------
def draw_center_text(im, text, f, color, y, alpha=1.0, scale=1.0):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    lines = text.split("\n")
    lh = int(f.size * 1.02)
    total = lh * len(lines)
    yy = y - total // 2
    for ln in lines:
        w = d.textlength(ln, font=f)
        d.text(((W - w) / 2, yy), ln, font=f, fill=color + (int(255 * alpha),))
        yy += lh
    if scale != 1.0:
        s = max(0.01, scale)
        lw, lh2 = int(W * s), int(H * s)
        layer = layer.resize((lw, lh2), Image.BICUBIC)
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        canvas.alpha_composite(layer, ((W - lw) // 2, int(y - y * s)))
        layer = canvas
    im.alpha_composite(layer)


def visual(im, beat, lt, dur):
    d = ImageDraw.Draw(im)
    kind = beat.get("kind", "text")
    big = beat.get("big", "")
    sub = beat.get("sub", "")
    p = ease(lt / 0.45)
    pop = back(lt / 0.4)
    cy = 760
    if kind in ("hook", "text", "cta"):
        f = fit_big(d, big, W - 140, 190 if kind != "hook" else 210)
        draw_center_text(im, big, f, WHITE if kind != "cta" else ACC, cy, p, 0.85 + 0.15 * pop)
    elif kind == "stat":
        m = re.match(r"([^\d]*)([\d,\.]+)(.*)", big)
        if m:
            pre, num, post = m.groups()
            target = float(num.replace(",", ""))
            cur = target * ease(lt / 1.1)
            dec = len(num.split(".")[1]) if "." in num else 0
            shown = f"{cur:,.{dec}f}" if "," in num else f"{cur:.{dec}f}"
            txt = pre + shown + post
        else:
            txt = big
        f = fit_big(d, big, W - 120, 300)
        draw_center_text(im, txt, f, ACC, cy, p, 0.9 + 0.1 * pop)
    elif kind == "bars":
        vals = beat.get("bars", [1, 28])
        labels = beat.get("labels", ["expected", "2024"])
        mx = max(vals)
        base, top = 1050, 420
        bw = 230
        xs = [W / 2 - bw - 60, W / 2 + 60]
        for i, (v, lab) in enumerate(zip(vals, labels)):
            g = ease((lt - 0.2 * i) / 1.0)
            hgt = max(8, (base - top) * v / mx * g)
            col = DIM if i == 0 else ACC
            d.rounded_rectangle((xs[i], base - hgt, xs[i] + bw, base), 18, fill=col)
            lf = font(FMED, 46)
            lw = d.textlength(lab, font=lf)
            d.text((xs[i] + (bw - lw) / 2, base + 22), lab, font=lf, fill=DIM)
            vf = font(FB, 84)
            vt = beat["values"][i] if beat.get("values") else (f"{v:g}×" if i else "1×")
            vw = d.textlength(vt, font=vf)
            d.text((xs[i] + (bw - vw) / 2, base - hgt - 100), vt, font=vf, fill=col + (int(255 * g),))
    if sub:
        sf = font(FMED, 50)
        lines = wrap(d, sub, sf, W - 200)
        y = (1180 if kind != "bars" else 1210)
        a = int(255 * ease((lt - 0.25) / 0.4))
        for ln in lines:
            w = d.textlength(ln, font=sf)
            d.text(((W - w) / 2, y), ln, font=sf, fill=DIM + (a,))
            y += 66


def captions(im, text, lt, dur):
    """Word-by-word caption, current word highlighted."""
    d = ImageDraw.Draw(im)
    words = text.split()
    weights = [max(2, len(w)) for w in words]
    tot = sum(weights)
    talk = dur * 0.95
    acc, idx = 0, len(words) - 1
    for i, wgt in enumerate(weights):
        acc += wgt
        if lt < talk * acc / tot:
            idx = i
            break
    f = font(FB, 66)
    lines = wrap(d, text, f, W - 160)
    # pad box
    y = 1460
    widx = 0
    for ln in lines:
        lw = sum(d.textlength(w, font=f) for w in ln.split()) + 22 * (len(ln.split()) - 1)
        x = (W - lw) / 2
        for w in ln.split():
            ww = d.textlength(w, font=f) + 22
            col = ACC if widx == idx else (WHITE if widx < idx else (210, 210, 220))
            if widx == idx:
                pad = 8
                d.rounded_rectangle((x - pad, y - 4, x + d.textlength(w, font=f) + pad, y + 82), 14, fill=(255, 255, 255, 28))
            # stroke for readability
            d.text((x, y), w, font=f, fill=col, stroke_width=4, stroke_fill=(0, 0, 0))
            x += ww
            widx += 1
        y += 92


def chrome(im, t, total):
    d = ImageDraw.Draw(im)
    tf = font(FBOLD, 34)
    tag = "THE ALGORITHM DID THIS"
    tw = d.textlength(tag, font=tf)
    d.rounded_rectangle(((W - tw) / 2 - 26, 150, (W + tw) / 2 + 26, 212), 31, outline=ACC + (200,), width=3)
    d.text(((W - tw) / 2, 160), tag, font=tf, fill=ACC)
    # progress bar
    d.rectangle((0, H - 10, W * min(1, t / total), H), fill=ACC)


# ---------- music ----------
def music(seconds, sr=24000):
    t = np.arange(int(seconds * sr)) / sr
    chords = [[220.0, 261.63, 329.63], [174.61, 220.0, 261.63], [196.0, 246.94, 293.66], [164.81, 207.65, 246.94]]
    out = np.zeros_like(t)
    seg = 2.0
    for i in range(int(seconds / seg) + 1):
        s, e = int(i * seg * sr), int(min(seconds, (i + 1) * seg) * sr)
        if s >= len(t): break
        tt = t[s:e] - i * seg
        env = np.minimum(1, tt / 0.3) * np.exp(-tt * 0.6)
        for fq in chords[i % 4]:
            out[s:e] += np.sin(2 * np.pi * fq * tt) * env * 0.05 + np.sin(2 * np.pi * fq * 2 * tt) * env * 0.012
    # soft pulse
    beat = (np.sin(2 * np.pi * 2.0 * t) > 0.97).astype(float)
    kick = np.convolve(beat, np.exp(-np.arange(1200) / 200) * np.sin(2 * np.pi * 55 * np.arange(1200) / sr), "same")
    out += kick * 0.05
    fade = np.minimum(1, np.minimum(t / 1.0, (seconds - t) / 1.5))
    return (out * fade).astype(np.float32)


def render(script, out):
    beats = script["beats"]
    voice, spans = tts.synth([b["say"] for b in beats], script.get("voice", "am_michael"),
                             gap=0.22, speed=script.get("speed", 1.05))
    lead = 0.25
    voice = np.concatenate([np.zeros(int(lead * tts.SR), np.float32), voice, np.zeros(int(0.8 * tts.SR), np.float32)])
    total = len(voice) / tts.SR
    m = music(total)[:len(voice)]
    if len(m) < len(voice):
        m = np.pad(m, (0, len(voice) - len(m)))
    mix = voice * 0.95 + m
    mix = mix / max(1.0, np.abs(mix).max() / 0.95)
    wav = out + ".wav"
    wavfile.write(wav, tts.SR, (mix * 32767).astype(np.int16))
    spans = [(a + lead, b + lead) for a, b in spans]
    # beat windows: each beat visible from its start until next start
    starts = [s[0] for s in spans] + [total]
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", wav,
                             "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                             "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", out],
                            stdin=subprocess.PIPE)
    n = int(total * FPS)
    for fi in range(n):
        t = fi / FPS
        bi = 0
        for i in range(len(beats)):
            if t >= starts[i] - 0.05:
                bi = i
        b = beats[bi]
        lt = t - starts[bi]
        im = background(t)
        visual(im, b, lt, starts[bi + 1] - starts[bi])
        sa, sb = spans[bi]
        captions(im, b["say"], max(0, t - sa), sb - sa)
        chrome(im, t, total)
        proc.stdin.write(im.convert("RGB").tobytes())
    proc.stdin.close(); proc.wait()
    os.remove(wav)
    return total


if __name__ == "__main__":
    s = json.load(open(sys.argv[1]))
    print("duration", render(s, sys.argv[2]))
