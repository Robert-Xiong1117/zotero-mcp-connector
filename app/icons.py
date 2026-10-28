"""App/tray icon: Zotero-red rounded square, white Z, status dot."""
from PIL import Image, ImageDraw, ImageFont

BRAND = (204, 41, 54, 255)
STATUS = {
    "ok": (46, 160, 67, 255),
    "warn": (230, 162, 30, 255),
    "bad": (218, 54, 51, 255),
    "idle": (140, 140, 140, 255),
}


def _font(size):
    for name in ("segoeuib.ttf", "arialbd.ttf", "Arial Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                 "/System/Library/Fonts/Helvetica.ttc", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def make_icon(level=None, size=256) -> Image.Image:
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = s * 0.03
    d.rounded_rectangle([pad, pad, s - pad, s - pad], radius=s * 0.22, fill=BRAND)
    f = _font(int(s * 0.66))
    box = d.textbbox((0, 0), "Z", font=f)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((s - w) / 2 - box[0], (s - h) / 2 - box[1]), "Z", font=f, fill=(255, 255, 255, 255))
    if level in STATUS:
        r_out, r_in = s * 0.22, s * 0.16
        cx = cy = s - r_out - pad * 0.5
        d.ellipse([cx - r_out, cy - r_out, cx + r_out, cy + r_out], fill=(255, 255, 255, 255))
        d.ellipse([cx - r_in, cy - r_in, cx + r_in, cy + r_in], fill=STATUS[level])
    return img


if __name__ == "__main__":  # used by the build to produce .ico / .png
    import sys
    out = sys.argv[1]
    base = make_icon(None, 1024)
    if out.endswith(".ico"):
        base.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    else:
        base.save(out)
