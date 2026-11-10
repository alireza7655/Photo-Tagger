import os
import math
import shutil
from PIL import Image, ImageDraw, ImageFont

ICONS_DIR = os.path.join(os.path.dirname(__file__), "assets", "icons")
os.makedirs(ICONS_DIR, exist_ok=True)

# -------------------------------------------------------------------------
# Windows-style Two-Color Fluent Palette
# 1. Neutral Silver/Slate Object Outline: #cbd5e1
# 2. Vibrant Indigo/Blue Action Detail: #818cf8 / #6366f1
# -------------------------------------------------------------------------
COLOR_OUTLINE = "#cbd5e1"   # Neutral slate/silver object outline
COLOR_ACCENT  = "#818cf8"   # Vibrant indigo/blue action detail
COLOR_MUTED   = "#64748b"   # Muted boundary for tertiary details
COLOR_WHITE   = "#f8fafc"   # Crisp highlight

SW = 16  # Standard stroke width on 256 canvas

def create_hi_canvas(size=256):
    return Image.new("RGBA", (size, size), (0, 0, 0, 0))

def finalize(im, out_size=64):
    return im.resize((out_size, out_size), Image.Resampling.LANCZOS)

SILVER = "#DDE7F3"
BLUE = "#65B7FF"
GOLD = "#FFC46B"
MINT = "#56E4BD"
LILAC = "#C6A6FF"


def draw_toolbar_icon(name):
    art = Image.new("RGBA", (192, 192))
    draw = ImageDraw.Draw(art)

    def line(points, color=SILVER, width=12):
        draw.line(points, fill=color, width=width, joint="curve")

    def frame(box, radius=10):
        draw.rounded_rectangle(box, radius=radius, outline=SILVER, width=12)

    def photo(y):
        frame((28, y, 164, y + 85))
        draw.ellipse((49, y + 17, 71, y + 39), fill=GOLD)
        line([(41, y + 69), (86, y + 43), (114, y + 62), (139, y + 46), (153, y + 61)], width=10)

    if name.startswith("rotate_"):
        photo(93)
        line([(159, 76), (159, 63), (152, 49), (138, 40), (63, 40)], BLUE, 15)
        draw.polygon([(26, 40), (70, 12), (70, 68)], fill=BLUE)
        if name == "rotate_right":
            art = art.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    elif name == "open_photo":
        photo(51)
        line([(26, 30), (76, 30)], BLUE, 13)
    elif name == "open_folder":
        line([(24, 149), (24, 55), (73, 55), (89, 73), (164, 73)], BLUE)
        line([(23, 151), (46, 98), (174, 98), (153, 151), (23, 151)], SILVER)
        line([(44, 98), (82, 98)], GOLD, 12)
    elif name == "save":
        line([(30, 159), (30, 33), (138, 33), (163, 58), (163, 159), (30, 159)])
        line([(62, 34), (62, 78), (125, 78), (125, 34)], BLUE)
        line([(56, 155), (56, 110), (136, 110), (136, 155)])
        line([(79, 130), (113, 130)], MINT, 12)
    elif name == "export":
        line([(29, 99), (29, 155), (163, 155), (163, 99)])
        line([(95, 119), (95, 32)], BLUE, 15)
        draw.polygon([(95, 21), (57, 66), (133, 66)], fill=BLUE)
        line([(69, 154), (122, 154)], MINT, 12)
    elif name == "help":
        draw.ellipse((24, 24, 168, 168), outline=SILVER, width=12)
        line([(74, 71), (82, 58), (101, 55), (117, 65), (117, 82),
              (96, 100), (96, 111)], BLUE, 13)
        draw.ellipse((88, 123, 104, 139), fill=LILAC)
    else:
        raise ValueError(name)
    return art.resize((64, 64), Image.Resampling.LANCZOS)


def draw_open_photo():
    return draw_toolbar_icon("open_photo")

def draw_open_folder():
    return draw_toolbar_icon("open_folder")

def draw_save():
    return draw_toolbar_icon("save")

def draw_write_tags():
    # Silver metadata tag outline + Blue circular eyelet & thread/label
    im = create_hi_canvas(256)
    d = ImageDraw.Draw(im)
    pts = [(40, 128), (96, 52), (216, 52), (216, 204), (96, 204), (40, 128)]
    for i in range(len(pts)-1):
        d.line([pts[i], pts[i+1]], fill=COLOR_OUTLINE, width=SW)
    # Blue eyelet
    d.ellipse([(82, 112), (114, 144)], outline=COLOR_ACCENT, width=SW-2)
    # Blue label write lines
    d.line([(136, 106), (192, 106)], fill=COLOR_ACCENT, width=SW-4)
    d.line([(136, 148), (176, 148)], fill=COLOR_ACCENT, width=SW-4)
    return finalize(im)

def draw_export():
    return draw_toolbar_icon("export")

def draw_help():
    return draw_toolbar_icon("help")

def draw_overflow():
    # Outer silver dots + Blue center action dot
    im = create_hi_canvas(256)
    d = ImageDraw.Draw(im)
    d.ellipse([(64 - 18, 128 - 18), (64 + 18, 128 + 18)], fill=COLOR_OUTLINE)
    d.ellipse([(128 - 20, 128 - 20), (128 + 20, 128 + 20)], fill=COLOR_ACCENT)
    d.ellipse([(192 - 18, 128 - 18), (192 + 18, 128 + 18)], fill=COLOR_OUTLINE)
    return finalize(im)

def draw_undo_turn():
    # Slate curved arc + Blue arrow head
    im = create_hi_canvas(256)
    d = ImageDraw.Draw(im)
    d.arc([60, 48, 212, 200], start=210, end=40, fill=COLOR_OUTLINE, width=SW)
    d.polygon([(48, 92), (108, 64), (92, 124)], fill=COLOR_ACCENT)
    return finalize(im)

def draw_redo_turn():
    # Slate curved arc + Blue arrow head
    im = create_hi_canvas(256)
    d = ImageDraw.Draw(im)
    d.arc([44, 48, 196, 200], start=140, end=330, fill=COLOR_OUTLINE, width=SW)
    d.polygon([(208, 92), (148, 64), (164, 124)], fill=COLOR_ACCENT)
    return finalize(im)

def draw_tool_add():
    # Silver magnifying glass rim + Blue plus crosshair
    im = create_hi_canvas(256)
    d = ImageDraw.Draw(im)
    d.ellipse([(36, 36), (220, 220)], outline=COLOR_OUTLINE, width=SW)
    # Blue plus
    d.line([(128, 80), (128, 176)], fill=COLOR_ACCENT, width=SW)
    d.line([(80, 128), (176, 128)], fill=COLOR_ACCENT, width=SW)
    return finalize(im)

def draw_tool_minus():
    # Silver magnifying glass rim + Blue minus bar
    im = create_hi_canvas(256)
    d = ImageDraw.Draw(im)
    d.ellipse([(36, 36), (220, 220)], outline=COLOR_OUTLINE, width=SW)
    # Blue minus
    d.line([(80, 128), (176, 128)], fill=COLOR_ACCENT, width=SW)
    return finalize(im)

def draw_nav_prev():
    # Silver chevron stem + Blue left indicator accent
    im = create_hi_canvas(256)
    d = ImageDraw.Draw(im)
    d.line([(160, 52), (88, 128), (160, 204)], fill=COLOR_OUTLINE, width=SW+4)
    d.polygon([(80, 128), (114, 106), (114, 150)], fill=COLOR_ACCENT)
    return finalize(im)

def draw_nav_next():
    # Silver chevron stem + Blue right indicator accent
    im = create_hi_canvas(256)
    d = ImageDraw.Draw(im)
    d.line([(96, 52), (168, 128), (96, 204)], fill=COLOR_OUTLINE, width=SW+4)
    d.polygon([(176, 128), (142, 106), (142, 150)], fill=COLOR_ACCENT)
    return finalize(im)

def draw_filmstrip():
    # Silver film boundary & sprocket holes + Blue center frame
    im = create_hi_canvas(256)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([28, 52, 228, 204], radius=20, outline=COLOR_OUTLINE, width=SW)
    # Blue inner photo cell
    d.rectangle([76, 76, 180, 180], outline=COLOR_ACCENT, width=SW-4)
    for x in [48, 96, 144, 192]:
        d.rectangle([x-8, 58, x+8, 70], fill=COLOR_OUTLINE)
        d.rectangle([x-8, 186, x+8, 198], fill=COLOR_OUTLINE)
    return finalize(im)

def draw_rotate_left():
    return draw_toolbar_icon("rotate_left")

def draw_rotate_right():
    return draw_toolbar_icon("rotate_right")

def generate_all_icons():
    icons = {
        "open_photo.png": draw_open_photo(),
        "open_folder.png": draw_open_folder(),
        "save.png": draw_save(),
        "write_tags.png": draw_write_tags(),
        "export.png": draw_export(),
        "help.png": draw_help(),
        "overflow.png": draw_overflow(),
        "undo.png": draw_undo_turn(),
        "redo.png": draw_redo_turn(),
        "tool_add.png": draw_tool_add(),
        "tool_minus.png": draw_tool_minus(),
        "nav_prev.png": draw_nav_prev(),
        "nav_next.png": draw_nav_next(),
        "filmstrip.png": draw_filmstrip(),
        "rotate_left.png": draw_rotate_left(),
        "rotate_right.png": draw_rotate_right(),
    }
    for name, img in icons.items():
        p = os.path.join(ICONS_DIR, name)
        img.save(p)
    return icons

def create_icon_contact_sheet(out_path):
    """
    Renders an icon contact sheet displaying every icon at:
    - Native 100% size (20x20 and 24x24)
    - 150% High-DPI scale (30x30 and 36x36)
    - Full-resolution preview (48x48)
    With metadata labels, roles, and color breakdown.
    """
    icons = generate_all_icons()
    
    font_path = "C:\\Windows\\Fonts\\segoeui.ttf"
    font = ImageFont.truetype(font_path, 13) if os.path.exists(font_path) else ImageFont.load_default()
    font_bold = ImageFont.truetype("C:\\Windows\\Fonts\\segoeuib.ttf", 14) if os.path.exists("C:\\Windows\\Fonts\\segoeuib.ttf") else font
    font_header = ImageFont.truetype("C:\\Windows\\Fonts\\segoeuib.ttf", 18) if os.path.exists("C:\\Windows\\Fonts\\segoeuib.ttf") else font

    rows = len(icons)
    sheet_w = 900
    row_h = 44
    header_h = 90
    sheet_h = header_h + rows * row_h + 30

    sheet = Image.new("RGBA", (sheet_w, sheet_h), "#0f111a")
    d = ImageDraw.Draw(sheet)

    # Title Banner
    d.rectangle([0, 0, sheet_w, header_h - 10], fill="#141724")
    d.text((24, 16), "Photo Tagger v3.0 — Fluent Two-Color Icon Family Contact Sheet", font=font_header, fill="#f8fafc")
    d.text((24, 46), "Default: Silver Outline (#cbd5e1) + Vibrant Indigo Action Accent (#818cf8) • Tested at 100% and 150% Scale", font=font, fill="#94a3b8")

    # Column headers
    cols = [(24, "ICON NAME & ROLE"), (320, "20px (100%)"), (420, "24px (100%)"), (530, "30px (150%)"), (650, "36px (150%)"), (770, "48px PREVIEW")]
    for cx, ch in cols:
        d.text((cx, header_h - 6), ch, font=font_bold, fill="#64748b")
    d.line([(20, header_h + 16), (sheet_w - 20, header_h + 16)], fill="#232738", width=1)

    y = header_h + 24
    for idx, (name, img) in enumerate(icons.items()):
        # Alternating subtle row background
        if idx % 2 == 1:
            d.rectangle([16, y - 6, sheet_w - 16, y + row_h - 8], fill="#13151f")

        role = name.replace(".png", "").replace("_", " ").title()
        d.text((24, y + 4), f"{name} ({role})", font=font, fill="#e2e8f0")

        # 20px
        im20 = img.resize((20, 20), Image.Resampling.LANCZOS)
        sheet.paste(im20, (330, y + 4), im20)

        # 24px
        im24 = img.resize((24, 24), Image.Resampling.LANCZOS)
        sheet.paste(im24, (430, y + 2), im24)

        # 30px
        im30 = img.resize((30, 30), Image.Resampling.LANCZOS)
        sheet.paste(im30, (540, y - 1), im30)

        # 36px
        im36 = img.resize((36, 36), Image.Resampling.LANCZOS)
        sheet.paste(im36, (660, y - 4), im36)

        # 48px
        im48 = img.resize((48, 48), Image.Resampling.LANCZOS)
        sheet.paste(im48, (780, y - 10), im48)

        y += row_h

    sheet.save(out_path)
    print(f"Saved icon contact sheet: {out_path} ({sheet_w}x{sheet_h})")

def main():
    icons = generate_all_icons()
    print(f"Generated {len(icons)} two-color icons in {ICONS_DIR}")
    contact_path = os.path.join(os.path.dirname(__file__), "Plans-Reports", "20261109", "run", "icon_contact_sheet.png")
    os.makedirs(os.path.dirname(contact_path), exist_ok=True)
    create_icon_contact_sheet(contact_path)
    shutil.copy2(contact_path, os.path.join(ICONS_DIR, "icon_contact_sheet.png"))
    
    # Mirror contact sheet to baseline
    baseline_run = os.path.join("C:/Coding_Projects/Photo Tagger", "Plans-Reports", "20261109", "run")
    os.makedirs(baseline_run, exist_ok=True)
    shutil.copy2(contact_path, os.path.join(baseline_run, "icon_contact_sheet.png"))

if __name__ == "__main__":
    main()
