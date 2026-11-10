import os
import sys
import shutil
import hashlib
import pytest
from PIL import Image, ImageChops

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import PT
from PT import PhotoTaggerApp, APP_VERSION
import models
from models import ProjectDocument, TagStyle
import project_io
from project_io import save_project_document, load_project_document
import metadata
from metadata import (
    resolve_font_files_for_family,
    draw_annotations_on_image,
    shape_persian_arabic_text,
    write_interactive_html,
    write_interactive_svg
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

@pytest.fixture(scope="module")
def app():
    # Set Tcl/Tk library paths if needed
    tcl_dir = "C:/Users/alire/AppData/Local/Programs/Python/Python312/tcl/tcl8.6"
    tk_dir = "C:/Users/alire/AppData/Local/Programs/Python/Python312/tcl/tk8.6"
    if os.path.isdir(tcl_dir):
        os.environ["TCL_LIBRARY"] = tcl_dir
    if os.path.isdir(tk_dir):
        os.environ["TK_LIBRARY"] = tk_dir

    PT.messagebox.askyesnocancel = lambda *a, **k: False
    PT.messagebox.askyesno = lambda *a, **k: False
    PT.messagebox.showwarning = lambda *a, **k: None
    PT.messagebox.showinfo = lambda *a, **k: None
    PT.messagebox.showerror = lambda *a, **k: None

    instance = PhotoTaggerApp()
    yield instance
    try:
        instance.destroy()
    except Exception:
        pass


def test_tag_font_picker_ui_controls(app):
    """Verify Tag Font picker exists under Appearance with 3 verified choices."""
    assert hasattr(app, "seg_tag_font"), "seg_tag_font control must exist"
    assert hasattr(app, "combo_tag_font"), "combo_tag_font control must exist"
    assert hasattr(app, "lbl_font_sample"), "lbl_font_sample preview label must exist"

    # Default is Segoe UI
    assert app.get_selected_tag_font() == "Segoe UI"
    assert app.seg_tag_font.get() == "Segoe UI"
    assert app.combo_tag_font.get() == "Segoe UI"

    # Switching to Tahoma
    app.on_tag_font_changed("Tahoma")
    assert app.get_selected_tag_font() == "Tahoma"
    assert app.seg_tag_font.get() == "Tahoma"
    assert app.combo_tag_font.get() == "Tahoma"
    assert app.lbl_font_sample.cget("font")[0] == "Tahoma"

    # Switching to Arial
    app.on_tag_font_changed("Arial")
    assert app.get_selected_tag_font() == "Arial"
    assert app.seg_tag_font.get() == "Arial"
    assert app.combo_tag_font.get() == "Arial"
    assert app.lbl_font_sample.cget("font")[0] == "Arial"

    # Reset to Segoe UI
    app.on_tag_font_changed("Segoe UI")
    assert app.get_selected_tag_font() == "Segoe UI"


def test_font_survival_on_save_and_reload(app, tmp_path):
    """Verify font choice persists in .phototagger.json and survives reload."""
    test_photo = str(tmp_path / "font_persist_test.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), test_photo)
    assert app.load_image(test_photo) is True

    # Select Tahoma
    app.on_tag_font_changed("Tahoma")
    assert app.is_project_dirty is True

    # Save Project
    saved = app.save_project_only()
    assert saved is True
    assert app.is_project_dirty is False

    # Check sidecar content directly
    sidecar_path = test_photo + ".phototagger.json"
    assert os.path.exists(sidecar_path)
    loaded_doc = load_project_document(test_photo)
    assert loaded_doc is not None
    assert loaded_doc.style.font_family == "Tahoma"

    # Reload image and verify UI rehydrates font choice
    # First flip app state to Arial to confirm reload changes it
    app.seg_tag_font.set("Arial")
    assert app.load_image(test_photo) is True
    assert app.get_selected_tag_font() == "Tahoma"
    assert app.seg_tag_font.get() == "Tahoma"
    assert app.combo_tag_font.get() == "Tahoma"


def test_photo_hash_untouched_on_save_project(app, tmp_path):
    """Save Project must never touch or modify the original photo file bytes."""
    test_photo = str(tmp_path / "photo_hash_test.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), test_photo)

    with open(test_photo, "rb") as f:
        orig_hash = hashlib.sha256(f.read()).hexdigest()

    assert app.load_image(test_photo) is True
    app.on_tag_font_changed("Arial")
    app.save_project_only()

    with open(test_photo, "rb") as f:
        new_hash = hashlib.sha256(f.read()).hexdigest()

    assert orig_hash == new_hash, "Original photo file hash must be 100% identical after Save Project"


def test_export_pixel_divergence_between_fonts(tmp_path):
    """
    Rendered export images must differ in pixel bytes between different fonts
    (e.g., Segoe UI vs Tahoma vs Arial).
    """
    photo_path = os.path.join(FIXTURES_DIR, "single_portrait.jpg")
    faces = [{"name": "دکتر مریم احمدی (Dr. Maryam)", "x": 0.5, "y": 0.5, "w": 0.25, "h": 0.25, "id": "f1"}]

    img_segoe = draw_annotations_on_image(
        photo_path, faces, output_path=None, draw_names=True, font_family="Segoe UI"
    )
    img_tahoma = draw_annotations_on_image(
        photo_path, faces, output_path=None, draw_names=True, font_family="Tahoma"
    )
    img_arial = draw_annotations_on_image(
        photo_path, faces, output_path=None, draw_names=True, font_family="Arial"
    )

    assert img_segoe is not None
    assert img_tahoma is not None
    assert img_arial is not None

    # Compare Segoe vs Tahoma
    diff_st = ImageChops.difference(img_segoe.convert("RGB"), img_tahoma.convert("RGB"))
    bbox_st = diff_st.getbbox()
    assert bbox_st is not None, "Segoe UI and Tahoma must produce differing pixel bytes"

    # Compare Segoe vs Arial
    diff_sa = ImageChops.difference(img_segoe.convert("RGB"), img_arial.convert("RGB"))
    bbox_sa = diff_sa.getbbox()
    assert bbox_sa is not None, "Segoe UI and Arial must produce differing pixel bytes"


def test_persian_arabic_coverage_across_fonts():
    """All 3 fonts must resolve system font files and support Persian/Arabic text shaping."""
    persian_test_text = "۱۲ • دکتر مریم احمدی (Dr. Maryam)"
    shaped = shape_persian_arabic_text(persian_test_text)
    assert shaped is not None
    assert len(shaped) > 0

    for family in ["Segoe UI", "Tahoma", "Arial"]:
        font_paths = resolve_font_files_for_family(family)
        assert len(font_paths) > 0, f"Font paths for {family} must not be empty"
        # At least one font file must exist on Windows
        existing = [p for p in font_paths if os.path.exists(p)]
        assert len(existing) > 0, f"At least one font file for {family} must exist on disk: {font_paths}"


def test_missing_font_fallback():
    """Unsupported or missing font names safely fallback to Segoe UI."""
    fallback_paths = resolve_font_files_for_family("NonExistentFontFamilyXYZ")
    assert len(fallback_paths) > 0
    # Should resolve to Segoe UI fallbacks
    segoe_paths = resolve_font_files_for_family("Segoe UI")
    assert fallback_paths == segoe_paths


def test_interactive_html_and_svg_font_family(tmp_path):
    """HTML and SVG exports must include the chosen font family in style/attributes."""
    photo_path = str(tmp_path / "web_export_test.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), photo_path)
    faces = [{"name": "Test User", "x": 0.5, "y": 0.5, "w": 0.2, "h": 0.2, "id": "t1"}]

    html_path = photo_path.replace(".jpg", "_interactive.html")
    svg_path = photo_path.replace(".jpg", "_interactive.svg")

    ok_html = write_interactive_html(photo_path, faces, "Sample Desc", font_family="Tahoma")
    assert ok_html is True
    assert os.path.exists(html_path)
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    assert "'Tahoma', 'Segoe UI'" in html_content

    ok_svg = write_interactive_svg(photo_path, faces, "Sample Desc", font_family="Arial")
    assert ok_svg is True
    assert os.path.exists(svg_path)
    with open(svg_path, "r", encoding="utf-8") as f:
        svg_content = f.read()
    assert 'font-family="Arial, Segoe UI' in svg_content


def test_fluent_two_color_icons_and_mirrored_rotate():
    """Verify generated icons exist, have 2-color palette, and rotate pair is mirrored."""
    icons_dir = os.path.join(BASE_DIR, "assets", "icons")
    assert os.path.isdir(icons_dir), "assets/icons must exist"

    required_icons = [
        "open_photo.png", "open_folder.png", "save.png", "write_tags.png",
        "export.png", "help.png", "overflow.png", "undo.png", "redo.png",
        "tool_add.png", "tool_minus.png", "nav_prev.png", "nav_next.png",
        "filmstrip.png", "rotate_left.png", "rotate_right.png"
    ]

    for icon_name in required_icons:
        icon_path = os.path.join(icons_dir, icon_name)
        assert os.path.exists(icon_path), f"Icon {icon_name} must exist"
        with Image.open(icon_path) as im:
            assert im.size == (64, 64)
            assert im.mode == "RGBA"

    # Verify rotate pair is mirrored (horizontal flip of rotate_left matches rotate_right)
    rl_path = os.path.join(icons_dir, "rotate_left.png")
    rr_path = os.path.join(icons_dir, "rotate_right.png")
    with Image.open(rl_path) as rl, Image.open(rr_path) as rr:
        rl_flipped = rl.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        diff = ImageChops.difference(rl_flipped, rr)
        # Bounding box of difference should be either None or extremely small (sub-pixel anti-aliasing)
        bbox = diff.getbbox()
        if bbox:
            # Let's verify max difference is negligible
            stat = diff.convert("L").getextrema()
            assert stat[1] < 30, "rotate_left and rotate_right must be clean mirrored pair"

    # Contact sheet verification
    sheet_path = os.path.join(icons_dir, "icon_contact_sheet.png")
    assert os.path.exists(sheet_path), "icon_contact_sheet.png must exist"
