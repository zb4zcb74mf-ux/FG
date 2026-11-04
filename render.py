"""رسم بطاقات البنك بتصميم زجاجي بنفسجي (Pillow).

كل شيء يُرسم بدقة مضاعفة (SS) ثم يُصغَّر لحواف ناعمة.
"""
import functools
import io
import math
import os
import random
import re

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, features

SS = 2
W = 900

# ---------------------------------------------------------------- نصوص عربية
_RAQM = features.check("raqm")
if not _RAQM:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _reshaper = arabic_reshaper.ArabicReshaper()

_AR = re.compile(r"[\u0600-\u06FF]")
_MONEY = re.compile(r"[+\-]?\$[\d,.]+[kmbKMB]?")


def ar(s) -> str:
    s = str(s)
    if not _AR.search(s):
        return s
    # المبالغ تبقى LTR داخل النص العربي ($5k , +$1,200 ...)
    s = _MONEY.sub(lambda m: "\u2066" + m.group(0) + "\u2069", s)
    if _RAQM:
        return s
    return get_display(_reshaper.reshape(s))


_FONT_CANDIDATES = [
    "assets/fonts/Cairo-Bold.ttf", "assets/fonts/Tajawal-Bold.ttf",
    "assets/fonts/Almarai-Bold.ttf", "assets/fonts/font.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/tahomabd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]
_BASE = os.path.dirname(os.path.abspath(__file__))


@functools.lru_cache(maxsize=None)
def font(size: int):
    for p in _FONT_CANDIDATES:
        p = p if os.path.isabs(p) else os.path.join(_BASE, p)
        if os.path.exists(p):
            try:
                if _RAQM:
                    return ImageFont.truetype(p, size, layout_engine=ImageFont.Layout.RAQM)
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


# ---------------------------------------------------------------- الهوية
BRAND = {"name": "SCAR", "logo": None}


def set_brand(name: str, logo: Image.Image | None):
    BRAND["name"] = re.sub(r"(?i)\s*bank$", "", name).strip() or name
    BRAND["logo"] = logo.convert("RGBA") if logo else None


def placeholder(label="?", color=(170, 30, 48)) -> Image.Image:
    im = Image.new("RGBA", (256, 256), color + (255,))
    d = ImageDraw.Draw(im)
    d.text((128, 128), str(label)[:1].upper(), font=font(140), fill="white", anchor="mm")
    return im


# ---------------------------------------------------------------- ألوان
PURPLE_1 = (46, 11, 18)
PURPLE_2 = (9, 6, 8)
BORDER = (205, 32, 52)
LIGHT = (222, 202, 204)
GREEN = (46, 230, 120)
RED = (255, 70, 80)
ORANGE = (255, 140, 40)
WHITE = (255, 255, 255)
PANEL = (22, 9, 12, 238)


def _gradient(w, h, c1, c2):
    v = Image.linear_gradient("L").resize((w, h))
    hz = v.rotate(90, expand=True).resize((w, h))
    mask = ImageChops.add(v, hz, scale=2)
    return Image.composite(Image.new("RGB", (w, h), c2), Image.new("RGB", (w, h), c1), mask)


class Canvas:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.im = _gradient(w * SS, h * SS, PURPLE_1, PURPLE_2)
        self.d = ImageDraw.Draw(self.im, "RGBA")

    # --- أساسيات
    def _b(self, box):
        return [v * SS for v in box]

    def rrect(self, box, r, fill=None, outline=None, width=1):
        self.d.rounded_rectangle(self._b(box), r * SS, fill=fill, outline=outline,
                                 width=max(1, int(width * SS)) if outline else 0)

    def ellipse(self, box, fill=None, outline=None, width=1):
        self.d.ellipse(self._b(box), fill=fill, outline=outline,
                       width=max(1, int(width * SS)) if outline else 0)

    def line(self, pts, fill, width=2):
        self.d.line([(x * SS, y * SS) for x, y in pts], fill=fill, width=int(width * SS), joint="curve")

    def poly(self, pts, fill=None, outline=None):
        self.d.polygon([(x * SS, y * SS) for x, y in pts], fill=fill, outline=outline)

    def text(self, xy, t, size, fill=WHITE, anchor="mm"):
        self.d.text((xy[0] * SS, xy[1] * SS), ar(t), font=font(int(size * SS)), fill=fill, anchor=anchor)

    def tw(self, t, size):
        return self.d.textlength(ar(t), font=font(int(size * SS))) / SS

    def glow(self, cx, cy, r, color, blur=18, alpha=150):
        layer = Image.new("RGBA", self.im.size, (0, 0, 0, 0))
        ImageDraw.Draw(layer).ellipse(
            [(cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS], fill=color + (alpha,))
        layer = layer.filter(ImageFilter.GaussianBlur(blur * SS))
        base = self.im.convert("RGBA")
        self.im = Image.alpha_composite(base, layer).convert("RGB")
        self.d = ImageDraw.Draw(self.im, "RGBA")

    def paste_circle(self, img, cx, cy, d):
        px = int(d * SS)
        img = img.convert("RGBA").resize((px, px), Image.LANCZOS)
        mask = Image.new("L", (px, px), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, px - 1, px - 1], fill=255)
        self.im.paste(img, (int((cx - d / 2) * SS), int((cy - d / 2) * SS)), mask)

    def pill(self, cx, cy, t, size=20, fill=(28, 10, 14, 225), outline=(214, 64, 80),
             color=WHITE, pad=22, h=None, minw=0):
        w = max(self.tw(t, size) + pad * 2, minw)
        h = h or size * 1.9
        self.rrect([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], 7, fill=fill, outline=outline, width=2)
        self.text((cx, cy), t, size, color)
        return w

    # --- هيكل البطاقة
    def chrome(self, header_right="menu", timer=None, avatar=None):
        w, h = self.w, self.h
        # خدوش مائلة (scar) بدل اللمعة
        for dx, wd, al in ((.50, 16, 26), (.57, 7, 38), (.62, 3, 50)):
            x = w * dx
            self.poly([(x, 0), (x + wd, 0), (x - h * .38 + wd, h), (x - h * .38, h)], fill=(235, 40, 60, al))
        # الهيدر
        logo = BRAND["logo"] or placeholder(BRAND["name"][:1])
        self.glow(58, 52, 28, (235, 40, 60), blur=10, alpha=150)
        self.paste_circle(logo, 58, 52, 56)
        self.ellipse([29, 23, 87, 81], outline=BORDER + (255,), width=3)
        self.text((102, 52), BRAND["name"].upper(), 38, WHITE, "lm")
        tx = 102 + self.tw(BRAND["name"].upper(), 38) + 14
        self.rrect([tx, 38, tx + self.tw("BANK", 16) + 20, 66], 4, fill=BORDER + (255,))
        self.text((tx + 10, 52), "BANK", 16, WHITE, "lm")
        if header_right == "menu":
            for i in range(3):
                x = w - 96 + i * 18
                self.poly([(x + 10, 36), (x + 17, 36), (x + 7, 68), (x, 68)], fill=(240, 235, 235, 255))
        elif header_right == "avatar" and avatar is not None:
            self.paste_circle(avatar, w - 64, 52, 54)
            self.ellipse([w - 91, 25, w - 37, 79], outline=BORDER + (255,), width=3)
        if timer:
            self.pill(w / 2 + 40, 52, timer, 22, minw=100)
        self.line([(36, 100), (w - 36, 100)], (235, 40, 60, 90), 2)

    def finish(self) -> Image.Image:
        w, h = self.w * SS, self.h * SS
        c = 34 * SS
        shape = [(c, 0), (w, 0), (w, h - c), (w - c, h), (0, h), (0, c)]
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).polygon(shape, fill=255)
        out = self.im.convert("RGBA")
        d = ImageDraw.Draw(out)
        d.line(shape + [shape[0]], fill=BORDER + (255,), width=4 * SS, joint="curve")
        # شريط أحمر مميز بالزاوية المقطوعة
        d.line([(c, 3 * SS), (c * 2.4, 3 * SS)], fill=(255, 90, 100, 255), width=3 * SS)
        out.putalpha(mask)
        return out.resize((self.w, self.h), Image.LANCZOS)


def to_bytes(img: Image.Image) -> io.BytesIO:
    b = io.BytesIO()
    img.save(b, "PNG")
    b.seek(0)
    return b


# ---------------------------------------------------------------- عناصر مشتركة
def avatar_block(c: Canvas, img, name, cx, cy, d=140, ring=WHITE, glow=(235, 40, 60)):
    c.glow(cx, cy, d / 2, glow, blur=16, alpha=170)
    c.ellipse([cx - d / 2 - 5, cy - d / 2 - 5, cx + d / 2 + 5, cy + d / 2 + 5], fill=ring + (255,))
    c.paste_circle(img, cx, cy, d)
    if name:
        c.pill(cx, cy + d / 2 + 30, name[:14], 20, minw=110)


def series(positive: bool, n=8, seed=None):
    rnd = random.Random(seed)
    v, out = rnd.uniform(.35, .65), []
    for i in range(n):
        out.append(v)
        v += rnd.uniform(-.28, .28)
        v = min(.95, max(.05, v))
    # ينتهي بالاتجاه الصحيح
    if positive and out[-1] < out[0]:
        out[-1] = min(.95, out[0] + rnd.uniform(.1, .3))
    if not positive and out[-1] > out[0]:
        out[-1] = max(.05, out[0] - rnd.uniform(.1, .3))
    return out


def draw_chart(c: Canvas, box, vals, color, avatar=None):
    x0, y0, x1, y1 = box
    n = len(vals)
    pts = [(x0 + (x1 - x0) * i / (n - 1), y1 - (y1 - y0) * v) for i, v in enumerate(vals)]
    c.poly(pts + [(x1, y1), (x0, y1)], fill=color + (55,))
    c.line(pts, color + (255,), 4)
    ex, ey = pts[-1]
    if avatar is not None:
        c.ellipse([ex - 15, ey - 15, ex + 15, ey + 15], fill=color + (255,))
        c.paste_circle(avatar, ex, ey, 24)


def die(c: Canvas, cx, cy, n, size=62):
    h = size / 2
    c.glow(cx, cy, h, (255, 255, 255), blur=8, alpha=50)
    c.rrect([cx - h, cy - h, cx + h, cy + h], 11, fill=(248, 248, 252, 255))
    o = size * .25
    pos = {1: [(0, 0)], 2: [(-o, -o), (o, o)], 3: [(-o, -o), (0, 0), (o, o)],
           4: [(-o, -o), (o, -o), (-o, o), (o, o)],
           5: [(-o, -o), (o, -o), (0, 0), (-o, o), (o, o)],
           6: [(-o, -o), (o, -o), (-o, 0), (o, 0), (-o, o), (o, o)]}[n]
    for dx, dy in pos:
        c.ellipse([cx + dx - 5.5, cy + dy - 5.5, cx + dx + 5.5, cy + dy + 5.5], fill=(25, 20, 40, 255))


# ---------------------------------------------------------------- رموز وأيقونات
def symbol(c: Canvas, kind, cx, cy, r):
    k = kind
    if k in ("cherry", "apple"):
        c.ellipse([cx - r * .7, cy - r * .55, cx + r * .7, cy + r * .85], fill=(230, 40, 55, 255))
        c.ellipse([cx - r * .45, cy - r * .35, cx - r * .1, cy - r * .05], fill=(255, 255, 255, 110))
        c.line([(cx, cy - r * .5), (cx + r * .25, cy - r * .95)], (60, 150, 60), 3)
        c.poly([(cx + r * .25, cy - r * .95), (cx + r * .7, cy - r * .85), (cx + r * .35, cy - r * .6)], fill=(70, 190, 80, 255))
    elif k == "lemon":
        c.ellipse([cx - r * .85, cy - r * .55, cx + r * .85, cy + r * .55], fill=(250, 220, 50, 255))
        c.ellipse([cx - r * .55, cy - r * .35, cx - r * .15, cy - r * .1], fill=(255, 255, 255, 120))
    elif k == "grape":
        for gx, gy in [(-.45, -.3), (.05, -.3), (.5, -.3), (-.2, .15), (.3, .15), (.05, .6)]:
            c.ellipse([cx + (gx - .27) * r, cy + (gy - .27) * r, cx + (gx + .27) * r, cy + (gy + .27) * r],
                      fill=(150, 70, 220, 255))
        c.line([(cx, cy - r * .6), (cx + r * .2, cy - r * .95)], (60, 150, 60), 3)
    elif k == "seven":
        c.text((cx, cy), "7", r * 2.0, (255, 70, 90))
    elif k == "star":
        pts = []
        for i in range(10):
            a = -math.pi / 2 + i * math.pi / 5
            rr = r * (.95 if i % 2 == 0 else .42)
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        c.poly(pts, fill=(255, 205, 40, 255))
    elif k == "gem":
        c.poly([(cx - r * .8, cy - r * .2), (cx - r * .4, cy - r * .75), (cx + r * .4, cy - r * .75),
                (cx + r * .8, cy - r * .2), (cx, cy + r * .85)], fill=(80, 190, 255, 255))
        c.line([(cx - r * .8, cy - r * .2), (cx + r * .8, cy - r * .2)], (255, 255, 255, 160), 2)
    elif k == "rotten":
        c.ellipse([cx - r * .7, cy - r * .7, cx + r * .7, cy + r * .7], fill=(90, 100, 80, 255))
        c.line([(cx - r * .35, cy - r * .35), (cx + r * .35, cy + r * .35)], (30, 30, 30), 5)
        c.line([(cx + r * .35, cy - r * .35), (cx - r * .35, cy + r * .35)], (30, 30, 30), 5)
    elif k == "orange":
        c.ellipse([cx - r * .75, cy - r * .75, cx + r * .75, cy + r * .75], fill=(255, 150, 30, 255))
        c.ellipse([cx - r * .45, cy - r * .5, cx - r * .1, cy - r * .2], fill=(255, 255, 255, 110))
    else:
        c.ellipse([cx - r * .7, cy - r * .7, cx + r * .7, cy + r * .7], fill=(150, 150, 170, 255))


def metal_icon(c: Canvas, kind, cx, cy, r, ring):
    c.glow(cx, cy, r, ring, blur=8, alpha=90)
    c.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(18, 12, 42, 255), outline=ring + (255,), width=3)
    q = r * .62
    if kind == "diamond":
        c.poly([(cx - q, cy - q * .35), (cx - q * .5, cy - q), (cx + q * .5, cy - q), (cx + q, cy - q * .35), (cx, cy + q)],
               fill=(70, 170, 255, 255))
        c.poly([(cx - q * .5, cy - q), (cx, cy - q * .35), (cx + q * .5, cy - q)], fill=(180, 230, 255, 255))
        c.line([(cx - q, cy - q * .35), (cx + q, cy - q * .35)], (255, 255, 255, 170), 2)
    elif kind in ("gold", "platinum"):
        top, side = ((255, 225, 90), (225, 150, 20)) if kind == "gold" else ((235, 238, 250), (150, 158, 180))
        c.poly([(cx - q, cy + q * .5), (cx - q * .6, cy - q * .2), (cx + q, cy - q * .2), (cx + q * .6, cy + q * .5)],
               fill=side + (255,))
        c.poly([(cx - q * .6, cy - q * .2), (cx - q * .3, cy - q * .65), (cx + q * 1.0, cy - q * .65), (cx + q, cy - q * .2)],
               fill=top + (255,))
    elif kind in ("silver", "copper"):
        a, b = ((225, 228, 238), (150, 155, 170)) if kind == "silver" else ((255, 160, 80), (190, 85, 30))
        c.ellipse([cx - q, cy - q, cx + q, cy + q], fill=b + (255,))
        c.ellipse([cx - q * .72, cy - q * .72, cx + q * .72, cy + q * .72], fill=a + (255,))
    elif kind == "ruby":
        pts = [(cx + q * math.cos(math.radians(60 * i + 30)), cy + q * math.sin(math.radians(60 * i + 30))) for i in range(6)]
        c.poly(pts, fill=(225, 35, 55, 255))
        c.poly([pts[0], pts[1], (cx, cy)], fill=(255, 120, 130, 255))
    elif kind == "emerald":
        pts = [(cx + q * math.cos(math.radians(45 * i + 22.5)), cy + q * math.sin(math.radians(45 * i + 22.5))) for i in range(8)]
        c.poly(pts, fill=(30, 190, 85, 255))
        c.poly([(cx - q * .45, cy - q * .45), (cx + q * .45, cy - q * .45), (cx + q * .45, cy + q * .45), (cx - q * .45, cy + q * .45)],
               fill=(110, 240, 150, 255))
    elif kind == "oil":
        c.ellipse([cx - q * .75, cy - q * .35, cx + q * .75, cy + q * 1.0], fill=(20, 20, 25, 255), outline=(190, 190, 205, 255), width=2)
        c.poly([(cx, cy - q * 1.0), (cx - q * .7, cy + q * .1), (cx + q * .7, cy + q * .1)], fill=(20, 20, 25, 255))
        c.line([(cx - q * .7, cy + q * .1), (cx, cy - q * 1.0), (cx + q * .7, cy + q * .1)], (190, 190, 205, 255), 2)
    elif kind == "pearl":
        c.ellipse([cx - q, cy - q, cx + q, cy + q], fill=(250, 238, 240, 255))
        c.ellipse([cx - q * .6, cy - q * .65, cx - q * .1, cy - q * .2], fill=(255, 255, 255, 230))
    else:  # عناصر المتجر
        c.ellipse([cx - q * .8, cy - q * .8, cx + q * .8, cy + q * .8], fill=(150, 100, 255, 255))


# ================================================================ البطاقات
def amount_card(avatar, name, title, big, big_color=GREEN, badge=None, badge_color=GREEN, badge_icon="check"):
    c = Canvas(W, 320)
    c.chrome()
    avatar_block(c, avatar, name, 170, 186)
    c.text((W - 40, 128), title, 22, LIGHT, "rm")
    c.text((W - 40, 190), big, 64, big_color, "rm")
    if badge:
        bw = c.tw(badge, 20) + 110
        x1, x0 = W - 40, W - 40 - bw
        c.rrect([x0, 232, x1, 292], 10, fill=badge_color + (25,), outline=badge_color + (255,), width=2)
        cx = x1 - 32
        if badge_icon == "check":
            c.ellipse([cx - 22, 247, cx + 22, 277], outline=badge_color + (255,), width=3) if False else None
            c.ellipse([cx - 22, 240, cx + 22, 284], outline=badge_color + (255,), width=3)
            c.line([(cx - 10, 262), (cx - 2, 271), (cx + 11, 253)], badge_color + (255,), 4)
        else:
            c.ellipse([cx - 22, 240, cx + 22, 284], fill=(200, 60, 50, 255), outline=(255, 110, 90, 255), width=2)
            for dy in (-7, 0, 7):
                c.rrect([cx - 11, 262 + dy - 3, cx + 11, 262 + dy + 3], 3, fill=(255, 200, 190, 255))
        c.text((cx - 36, 262), badge, 20, WHITE, "rm")
    return c.finish()


def balance_card(avatar, name, balance_text, debt_text=None):
    c = Canvas(W, 320)
    c.chrome()
    avatar_block(c, avatar, name, 170, 186)
    c.text((W - 40, 128), "كشف الحساب", 26, WHITE, "rm")
    c.rrect([300, 160, W - 40, 240], 16, fill=(10, 40, 40, 200), outline=GREEN + (255,), width=3)
    c.glow((300 + W - 40) / 2, 200, 40, GREEN, blur=26, alpha=40)
    c.ellipse([330, 182, 366, 218], fill=(250, 200, 40, 255), outline=(255, 235, 120, 255), width=3)
    c.text(((300 + W - 40) / 2 + 20, 200), balance_text, 52, GREEN)
    if debt_text:
        c.text((W - 40, 276), debt_text, 22, RED, "rm")
    else:
        for i, col in enumerate(((235, 235, 245, 255), (150, 130, 220, 255))):
            c.ellipse([600 + i * 24 - 14, 268 - 14, 600 + i * 24 + 14, 268 + 14], fill=col)
    return c.finish()


def chart_card(avatar, name, title, pct, delta_text, total_text, positive=True, seed=None):
    col = GREEN if positive else RED
    c = Canvas(W, 340)
    c.chrome()
    avatar_block(c, avatar, name, 170, 196)
    c.text((W - 40, 128), title, 22, LIGHT, "rm")
    c.text((W - 40, 176), f"{'+' if positive else '-'}{abs(pct)}%", 56, col, "rm")
    draw_chart(c, (340, 215, 650, 275), series(positive, seed=seed), col, avatar)
    c.text((W - 40, 258), delta_text, 28, col, "rm")
    lab = "الرصيد الكلي"
    c.text((W - 40, 302), lab, 18, LIGHT, "rm")
    c.text((W - 40 - c.tw(lab, 18) - 10, 302), total_text, 18, WHITE, "rm")
    return c.finish()


def vs_card(avatar_a, name_a, avatar_b, name_b, dice_a, dice_b, result_text, result_color):
    c = Canvas(W, 320)
    c.chrome()
    avatar_block(c, avatar_a, name_a, 140, 184, d=130)
    avatar_block(c, avatar_b, name_b, W - 140, 184, d=130)
    c.pill(W / 2, 140, "VS", 20, minw=54, h=34)
    die(c, W / 2 - 45, 192, dice_a)
    die(c, W / 2 + 45, 192, dice_b)
    c.text((W / 2, 258), result_text, 26, result_color)
    return c.finish()


def duel_card(avatar_a, name_a, avatar_b, name_b, text, color=GREEN, mode="steal"):
    c = Canvas(W, 320)
    c.chrome()
    avatar_block(c, avatar_a, name_a, 170, 186)
    avatar_block(c, avatar_b, name_b, W - 170, 186)
    mx = W / 2
    if mode == "steal":
        pts = [(mx - 90, 170), (mx - 30, 150), (mx + 25, 188), (mx + 90, 165)]
        for i, off in enumerate((30, 20)):
            c.line([(mx - 130 - off, 168 + i * 8), (mx - 100 - off + 25, 168 + i * 8)], ORANGE + (200,), 3)
        c.line(pts, ORANGE + (255,), 5)
        symbol(c, "star", mx + 100, 163, 15)
    elif mode == "heart":
        c.poly([(mx, 195), (mx - 48, 145), (mx - 30, 118), (mx, 138), (mx + 30, 118), (mx + 48, 145)],
               fill=(255, 70, 120, 255))
        c.ellipse([mx - 50, 112, mx - 4, 158], fill=(255, 70, 120, 255))
        c.ellipse([mx + 4, 112, mx + 50, 158], fill=(255, 70, 120, 255))
    else:  # تحويل: سهم
        c.line([(mx - 90, 160), (mx + 80, 160)], color + (255,), 6)
        c.poly([(mx + 60, 135), (mx + 100, 160), (mx + 60, 185)], fill=color + (255,))
    c.pill(mx, 238, text, 26, outline=color, color=color, minw=170, h=46)
    return c.finish()


def shield_card(avatar, name, title, remain_text):
    c = Canvas(W, 320)
    c.chrome()
    avatar_block(c, avatar, name, 170, 186)
    mx = 580
    c.text((mx, 135), title, 28, WHITE)
    c.glow(mx, 200, 40, GREEN, blur=20, alpha=110)
    pts = [(mx, 165), (mx + 42, 178), (mx + 40, 215), (mx, 245), (mx - 40, 215), (mx - 42, 178)]
    c.poly(pts, fill=(60, 170, 110, 255), outline=(120, 255, 180, 255))
    c.line([(mx - 15, 207), (mx - 3, 220), (mx + 20, 192)], WHITE, 6)
    c.text((mx, 276), remain_text, 22, LIGHT)
    return c.finish()


def wheel_card(avatar, name, prizes, idx, result_text):
    c = Canvas(W, 340)
    c.chrome()
    avatar_block(c, avatar, name, 170, 196)
    cx, cy, r = 600, 200, 80
    cols = [(225, 50, 50), (110, 120, 135), (235, 150, 20), (210, 80, 130), (80, 170, 60), (235, 160, 20)]
    n = len(prizes)
    sweep = 360 / n
    off = 270 - (idx * sweep + sweep / 2)
    c.glow(cx, cy, r, (255, 140, 40), blur=18, alpha=110)
    for i, p in enumerate(prizes):
        a0 = off + i * sweep
        c.d.pieslice([(cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS], a0, a0 + sweep,
                     fill=cols[i % len(cols)] + (255,), outline=(255, 255, 255, 60), width=SS)
        am = math.radians(a0 + sweep / 2)
        c.text((cx + r * .62 * math.cos(am), cy + r * .62 * math.sin(am)), _short_prize(p), 13, WHITE)
    c.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], fill=(25, 15, 40, 255))
    c.poly([(cx - 12, cy - r - 12), (cx + 12, cy - r - 12), (cx, cy - r + 8)], fill=(240, 240, 250, 255))
    c.text((cx, 314), result_text, 26, (255, 200, 60))
    return c.finish()


def _short_prize(p):
    return f"${p // 1000}k" if p >= 1000 else f"${p}"


def slots_card(avatar, name, kinds, labels, result_text, color, title=None):
    c = Canvas(W, 340)
    c.chrome()
    avatar_block(c, avatar, name, 170, 196)
    if title:
        c.text((W - 40, 128), title, 22, LIGHT, "rm")
    for i, k in enumerate(kinds):
        cx = 440 + i * 130
        c.rrect([cx - 52, 150, cx + 52, 250], 18, fill=(245, 244, 252, 255))
        symbol(c, k, cx, 200, 34)
        if labels:
            c.text((cx, 268), labels[i], 18, LIGHT)
    c.text((W - 40, 312), result_text, 28, color, "rm")
    return c.finish()


def trade_card(avatar, name, title, lines, big, big_color):
    """بيع/شراء: سطور صغيرة + مبلغ كبير."""
    c = Canvas(W, 340)
    c.chrome()
    avatar_block(c, avatar, name, 170, 196)
    c.text((W - 40, 128), title, 22, LIGHT, "rm")
    for i, ln in enumerate(lines[:3]):
        c.pill(W - 40 - c.tw(ln, 20) / 2 - 22, 170 + i * 42, ln, 20, minw=150, h=34)
    c.text((300 + 90, 296), big, 46, big_color, "mm")
    return c.finish()


def info_card(avatar, name, title, rows, footer=None):
    n = len(rows)
    h = max(330, 150 + n * 54 + (40 if footer else 20))
    c = Canvas(W, h)
    c.chrome()
    avatar_block(c, avatar, name, 170, min(210, h / 2 + 20))
    c.text((W - 40, 126), title, 26, WHITE, "rm")
    for i, row in enumerate(rows):
        label, value = row[0], row[1]
        col = row[2] if len(row) > 2 else WHITE
        y = 172 + i * 54
        c.rrect([320, y - 22, W - 40, y + 22], 14, fill=PANEL, outline=(150, 38, 52, 220), width=2)
        c.text((W - 60, y), label, 21, LIGHT, "rm")
        c.text((345, y), value, 21, col, "lm")
    if footer:
        c.text((W - 40, h - 26), footer, 18, LIGHT, "rm")
    return c.finish()


def market_card(avatar, rows, timer_text):
    tw_, th = 270, 140
    c = Canvas(W, 620)
    c.chrome(header_right="avatar", timer=timer_text, avatar=avatar)
    c.text((W / 2, 126), "أسعار المعادن", 26, WHITE)
    for i, m in enumerate(rows):
        col, row = i % 3, i // 3
        # الترتيب من اليمين لليسار مثل القوائم العربية
        x = W - 33 - tw_ - col * (tw_ + 12)
        y = 150 + row * (th + 12)
        ring = m["color"]
        c.rrect([x, y, x + tw_, y + th], 16, fill=PANEL, outline=ring + (255,), width=3)
        metal_icon(c, m["kind"], x + 50, y + 46, 34, ring)
        c.text((x + tw_ - 14, y + 22), m["name"], 20, WHITE, "rm")
        c.text((x + tw_ - 14, y + 50), f"${int(m['price']):,}", 24, WHITE, "rm")
        up = m["pct"] >= 0
        c.text((x + tw_ - 14, y + 76), f"{'▲' if up else '▼'} {abs(m['pct']):.1f}%", 16, GREEN if up else RED, "rm")
        bw = (tw_ - 24) / 3
        stats = [("أعلى", m["high"], GREEN), ("متوسط", m["avg"], WHITE), ("أدنى", m["low"], RED)]
        for j, (lab, val, vc) in enumerate(stats):
            bx = x + 12 + (2 - j) * bw
            c.rrect([bx + 2, y + 94, bx + bw - 2, y + th - 8], 8, fill=(255, 255, 255, 18))
            c.text((bx + bw / 2, y + 103), lab, 11, LIGHT)
            c.text((bx + bw / 2, y + 122), _k(val), 14, vc)
    return c.finish()


def _k(v):
    if v >= 1000:
        s = f"{v / 1000:.2f}".rstrip("0").rstrip(".") if v < 10000 else f"{v / 1000:.1f}".rstrip("0").rstrip(".")
        return f"${s}K"
    return f"${int(v)}"


def leaderboard_card(entries, title="الاغنياء"):
    """entries: [(img, name, value_text)]"""
    n = len(entries)
    h = 150 + n * 98 + 20
    c = Canvas(W, h)
    c.chrome()
    c.text((W - 40, 126), title, 26, WHITE, "rm")
    medal = [(255, 200, 40), (205, 205, 215), (230, 140, 60), (110, 110, 125), (110, 110, 125)]
    for i, (img, name, val) in enumerate(entries):
        y = 150 + i * 98
        c.rrect([36, y, W - 36, y + 82], 16, fill=PANEL, outline=(170, 40, 58, 255), width=2)
        ax = W - 90
        mc = medal[min(i, 4)]
        c.ellipse([ax - 34, y + 7, ax + 34, y + 75], fill=mc + (255,))
        c.paste_circle(img, ax, y + 41, 58)
        c.ellipse([ax + 12, y + 46, ax + 38, y + 72], fill=(235, 125, 40, 255) if i < 3 else (70, 70, 85, 255),
                  outline=(20, 15, 35, 255), width=2)
        c.text((ax + 25, y + 59), str(i + 1), 15, WHITE)
        if i == 0:
            symbol(c, "star", ax, y - 4, 13)
        c.text((ax - 52, y + 41), name[:16], 24, WHITE, "rm")
        c.text((64, y + 41), val, 24, GREEN, "lm")
    return c.finish()


MENU = [
    ((190, 36, 54), "عام", ["راتب", "فلوسي", "بخشيش", "تحويل", "نهب", "توب", "وقت", "بروفايل", "اعدادات"]),
    ((226, 168, 48), "المميزون", ["منح"]),
    ((214, 78, 40), "العاب", ["استثمار", "تداول", "رهان", "نرد", "قمار", "حجر", "تحدي", "فواكه", "لون", "حظ", "برج"]),
    ((150, 150, 165), "البنك", ["قرض", "سداد", "حماية"]),
    ((220, 90, 130), "الزواج", ["زواج", "زواجي", "طلاق"]),
    ((200, 150, 60), "المتجر", ["متجر", "ممتلكات", "شراء", "بيع", "سوق"]),
    ((120, 40, 60), "البيركات", ["صندوق", "بيركات"]),
]


def menu_card():
    mw = 1000
    size, ph, gap, pad = 20, 42, 10, 18
    probe = Canvas(10, 10)
    layouts, total = [], 150
    for color, title, cmds in MENU:
        rows, cur, x = [], [], 0
        maxw = mw - 2 * 50 - 2 * 18
        for cmd in cmds:
            w = probe.tw(cmd, size) + pad * 2
            if x + w > maxw and cur:
                rows.append(cur)
                cur, x = [], 0
            cur.append((cmd, w))
            x += w + gap
        rows.append(cur)
        body = 20 + len(rows) * (ph + gap) + 6
        layouts.append((color, title, rows, body))
        total += 52 + body + 22
    c = Canvas(mw, total + 10)
    c.chrome()
    c.text((mw / 2, 128), "قائمة اوامر البوت", 28, WHITE)
    y = 160
    for color, title, rows, body in layouts:
        c.rrect([40, y, mw - 40, y + 52 + body], 18, fill=(22, 9, 12, 238), outline=color + (255,), width=2)
        c.d.rounded_rectangle([40 * SS, y * SS, (mw - 40) * SS, (y + 52) * SS], 18 * SS, fill=color + (255,))
        c.d.rectangle([40 * SS, (y + 30) * SS, (mw - 40) * SS, (y + 52) * SS], fill=color + (255,))
        c.text((mw - 64, y + 26), title, 24, WHITE, "rm")
        py = y + 52 + 20 + ph / 2
        for row in rows:
            x = mw - 58
            for cmd, w in row:
                c.rrect([x - w, py - ph / 2, x, py + ph / 2], ph / 2, fill=color + (60,), outline=color + (255,), width=2)
                c.text((x - w / 2, py), cmd, size, WHITE)
                x -= w + gap
            py += ph + gap
        y += 52 + body + 22
    return c.finish()
