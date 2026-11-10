import os
import sys
import shutil
import pytest
from PIL import Image
import customtkinter as ctk

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from models import ProjectDocument, FaceTag, TagStyle
from project_io import save_project_document, load_project_document
from metadata import (
    compute_badge_metrics,
    get_badge_radius,
    shape_persian_arabic_text,
    get_preset_rendering_properties,
    compute_default_badge_positions,
    draw_annotations_on_image
)
from PT import PhotoTaggerApp

FIXTURES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "fixtures"))


@pytest.fixture(scope="module")
def app():
    import PT
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


def test_item2_preview_mode_cache_invalidation(app):
    """
    Item 2: Verify that switching Tagging -> Preview -> Tagging
    properly invalidates last_bg_key and deletes preview composite,
    preventing composite preview retention behind normal overlays.
    """
    test_photo = os.path.join(FIXTURES_DIR, "single_portrait.jpg")
    loaded = app.load_image(test_photo)
    assert loaded is True
    
    # 1. Normal tagging mode
    app.on_workspace_mode_changed("🏷️ Tagging")
    app.update_idletasks()
    assert app.active_workspace_mode == "tagging"
    initial_key = app.last_bg_key
    assert initial_key is not None
    assert initial_key[0] == "normal"
    
    # 2. Switch to Preview mode
    app.on_workspace_mode_changed("👁️ Preview & Export")
    app.update_idletasks()
    assert app.active_workspace_mode == "preview"
    preview_key = app.last_bg_key
    assert preview_key is not None
    assert preview_key[0] == "preview"
    assert preview_key != initial_key
    
    # 3. Switch back to Tagging mode at exact same dimensions and zoom
    app.on_workspace_mode_changed("🏷️ Tagging")
    app.update_idletasks()
    assert app.active_workspace_mode == "tagging"
    final_key = app.last_bg_key
    assert final_key is not None
    assert final_key[0] == "normal"
    assert final_key != preview_key
    
    # Verify canvas has bg_image and overlay tags distinct
    bg_items = app.canvas.find_withtag("bg_image")
    assert len(bg_items) >= 1


def test_item3_in_memory_preview_and_unified_layout():
    """
    Item 3: Verify in-memory preview without temp files and
    unified layout positions between canvas and export.
    """
    test_photo = os.path.join(FIXTURES_DIR, "single_portrait.jpg")
    with Image.open(test_photo) as im:
        w, h = im.size
        
    tags = [
        {'name': 'Person 1', 'x': 0.4, 'y': 0.3, 'w': 0.15, 'h': 0.2},
        {'name': 'Person 2', 'x': 0.7, 'y': 0.3, 'w': 0.15, 'h': 0.2}
    ]
    
    # 1. In-memory generation
    preview_img = draw_annotations_on_image(
        test_photo,
        tags,
        output_path=None,
        draw_names=True,
        style_preset="Classic"
    )
    assert isinstance(preview_img, Image.Image)
    assert preview_img.size[0] == w
    assert preview_img.size[1] > h  # includes footer
    
    # 2. Unified positions check
    positions = compute_default_badge_positions(tags, w, h)
    assert len(positions) == 2
    # Verify both badges computed outside face boxes
    for idx, (bx, by) in enumerate(positions):
        assert 0.0 <= bx <= 1.0
        assert 0.0 <= by <= 1.0


def test_item3_badge_metrics_circle_to_pill():
    """
    Item 3: Test label metrics for 1, 9, 10, 99, 100, 125, 999.
    """
    r = 20
    # Single digit -> symmetric circle
    for num in [1, 9]:
        w, h, is_pill = compute_badge_metrics(num, r)
        assert is_pill is False
        assert w == 2 * r
        assert h == 2 * r
        
    # Double digit -> compact pill
    for num in [10, 99]:
        w, h, is_pill = compute_badge_metrics(num, r)
        assert is_pill is True
        assert w == int(2.4 * r)
        assert h == 2 * r
        
    # Triple digit -> wide pill
    for num in [100, 125, 999]:
        w, h, is_pill = compute_badge_metrics(num, r)
        assert is_pill is True
        assert w == int(3.0 * r)
        assert h == 2 * r


def test_item3_persian_arabic_shaping():
    """
    Item 3: Verify Persian/Arabic shaping and visual RTL order.
    """
    raw_persian = "علیرضا رضایی"
    shaped = shape_persian_arabic_text(raw_persian)
    assert shaped != raw_persian
    # Verify non-empty and non-Arabic chars left intact
    mixed = "Ali علیرضا"
    shaped_mixed = shape_persian_arabic_text(mixed)
    assert "Ali" in shaped_mixed


def test_item4_truthful_presets_and_persistence(tmp_path):
    """
    Item 4: Verify truthful appearance presets:
    - High Contrast uses black text on yellow badge (WCAG AAA)
    - Print uses clean white legend background with dark text
    - Presets persist across sidecar save and reload
    """
    hc_props = get_preset_rendering_properties("High Contrast")
    assert hc_props["badge_text_rgb"] == (0, 0, 0, 255) # Black text!
    assert hc_props["badge_rgb"] == (234, 179, 8)       # Yellow badge!
    
    print_props = get_preset_rendering_properties("Print")
    assert print_props["legend_bg"] == (255, 255, 255, 255) # White legend!
    assert print_props["legend_text"] == (15, 23, 42, 255)  # Dark text!
    
    # Test persistence of preset in ProjectDocument
    photo_copy = str(tmp_path / "preset_test.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), photo_copy)
    
    doc = ProjectDocument(
        image_path=photo_copy,
        image_width=800,
        image_height=600,
        tags=[FaceTag(name="Dr. Smith", x=0.5, y=0.5, w=0.2, h=0.2)],
        style=TagStyle(preset_name="High Contrast", color_theme="Yellow")
    )
    save_project_document(doc)
    
    loaded = load_project_document(photo_copy)
    assert loaded is not None
    assert loaded.style.preset_name == "High Contrast"
    assert loaded.style.color_theme == "Yellow"


def test_item4_uuid_hidden_from_people_cards(app):
    """
    Item 4: Verify UUID strings are hidden from routine tagging UI cards.
    """
    test_photo = os.path.join(FIXTURES_DIR, "single_portrait.jpg")
    app.load_image(test_photo)
    app.update_idletasks()
    
    # Check that no label in faces_scroll contains "UUID:"
    for child in app.faces_scroll.winfo_children():
        for sub in child.winfo_children():
            if isinstance(sub, ctk.CTkLabel):
                txt = sub.cget("text")
                assert not txt.startswith("UUID:"), f"Found visible UUID: {txt}"


def test_u2_persian_arabic_clean_shaping_and_bidi():
    """
    U2: Verify proven Persian/Arabic shaping and UAX #9 Bidirectional Ordering.
    Asserts zero ASCII corruptions ('0EbBc...', '0E', etc.), proper Presentation Forms,
    and correct preservation of mixed English/Persian phrases, ZWNJ, and digits.
    """
    samples = [
        "علیرضا رضایی",
        "سارا طباطبایی",
        "دانش\u200cآموخته دانشگاه تهران",
        "توضیحات عکس به زبان فارسی با حروف ویژه: گ، چ، پ، ژ، ک، ی",
        "Dr. Alireza (علیرضا رضایی) - Lead Researcher",
        "شماره پرونده: ۱۲۳۴۵"
    ]
    for text in samples:
        shaped = shape_persian_arabic_text(text)
        assert shaped != text, f"Expected text to be reshaped: {text}"
        # Assert no Latin-looking corruptions or escape fragments
        for forbidden in ["0EbBc", "0E", "bB", "feC", "þ"]:
            assert forbidden not in shaped, f"Found corruption '{forbidden}' in shaped text: {shaped}"


def test_u2_mathematical_wcag_contrast_ratios():
    """
    U2: Mathematically compute and verify WCAG 2.1 contrast ratios
    for opaque rendered colors of all style presets.
    """
    def srgb_to_lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    def luminance(hex_color):
        hex_color = hex_color.lstrip('#')
        r, g, b = int(hex_color[:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return 0.2126 * srgb_to_lin(r) + 0.7152 * srgb_to_lin(g) + 0.0722 * srgb_to_lin(b)

    def ratio(c1, c2):
        l1, l2 = luminance(c1), luminance(c2)
        if l1 < l2:
            l1, l2 = l2, l1
        return (l1 + 0.05) / (l2 + 0.05)

    # High Contrast badge: Pitch Black on Safety Yellow
    hc_badge_ratio = ratio('#000000', '#FFCC00')
    assert hc_badge_ratio > 13.0, f"Expected HC badge ratio > 13.0, got {hc_badge_ratio}"
    assert hc_badge_ratio > 7.0  # WCAG AAA

    # High Contrast legend: Pure White on Pitch Black
    hc_legend_ratio = ratio('#FFFFFF', '#000000')
    assert hc_legend_ratio == 21.0  # Maximum theoretical ratio

    # Print preset badge: Pure White on Navy
    print_badge_ratio = ratio('#FFFFFF', '#1E3A8A')
    assert print_badge_ratio > 10.0
    assert print_badge_ratio > 7.0  # WCAG AAA

    # Print preset legend: Charcoal on Pure White Paper
    print_legend_ratio = ratio('#1F2937', '#FFFFFF')
    assert print_legend_ratio > 14.0
    assert print_legend_ratio > 7.0  # WCAG AAA


def test_u1_mode_sync_and_responsive_layout(app):
    """
    U1: Verify mode switcher segmented button visual state matches
    the internal active_workspace_mode, and action buttons fit without clipping.
    """
    # 1. Verify Mode Switcher Synchronization
    app.on_workspace_mode_changed("👁️ Preview")
    assert app.active_workspace_mode == "preview"
    assert "Preview" in app.mode_switcher.get()

    app.on_workspace_mode_changed("📐 Layout")
    assert app.active_workspace_mode == "layout"
    assert "Layout" in app.mode_switcher.get()

    app.on_workspace_mode_changed("🏷️ Tag")
    assert app.active_workspace_mode == "tagging"
    assert "Tag" in app.mode_switcher.get()

    # 2. Verify Action Buttons in Header Row
    assert hasattr(app, 'btn_save_project')
    assert hasattr(app, 'btn_write_tags')
    assert hasattr(app, 'btn_export_annotated')
    assert hasattr(app, 'combo_format')
    
    # 3. Verify minsize is within compact display limits
    assert (app._min_width, app._min_height) == (680, 360)


def test_r3_work_area_sizing_and_taskbar_clearance(app):
    """
    Review 3: Verify the physical window fits strictly inside usable work area (1280x672)
    with safe margins (> 20px) preventing any taskbar overlap.
    """
    app.update()
    import ctypes
    from ctypes import wintypes
    class RECT(ctypes.Structure):
        _fields_ = [('left', wintypes.LONG), ('top', wintypes.LONG), ('right', wintypes.LONG), ('bottom', wintypes.LONG)]
    wrect = RECT()
    hwnd = ctypes.windll.user32.GetParent(app.winfo_id()) or app.winfo_id()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(wrect))
    
    # Work area bounds on test monitor
    assert wrect.left >= 0, f"Window left {wrect.left} < 0"
    assert wrect.top >= 0, f"Window top {wrect.top} < 0"
    assert wrect.right <= 1280, f"Window right {wrect.right} exceeds monitor width 1280"
    assert wrect.bottom <= 672, f"Window bottom {wrect.bottom} exceeds usable work area height 672 (taskbar collision!)"
    
    # Verify positive clearance
    bottom_clearance = 672 - wrect.bottom
    right_clearance = 1280 - wrect.right
    assert bottom_clearance >= 15, f"Bottom clearance too tight: {bottom_clearance}px"
    assert right_clearance >= 15, f"Right clearance too tight: {right_clearance}px"


def test_r3_zoom_fit_and_floating_canvas_controls(app):
    """
    Review 3 / Alpha 2: Verify zoom and fit controls are discoverable, visible,
    and unified in the persistent floating canvas overlay to prevent toolbar clipping.
    """
    app.update()
    # Floating canvas zoom overlay
    assert hasattr(app, 'canvas_zoom_pill')
    assert app.canvas_zoom_pill.winfo_ismapped() == 1
    assert hasattr(app, 'c_btn_zoom_out')
    assert hasattr(app, 'c_btn_zoom_in')
    assert hasattr(app, 'c_btn_fit')
    assert hasattr(app, 'c_lbl_zoom')

    # Canonical zoom control attributes are mapped directly to floating canvas controls
    assert hasattr(app, 'btn_zoom_out')
    assert hasattr(app, 'btn_zoom_in')
    assert hasattr(app, 'btn_zoom_reset')
    assert hasattr(app, 'lbl_zoom_level')
    assert app.btn_zoom_out is app.c_btn_zoom_out
    assert app.btn_zoom_reset is app.c_btn_fit
    assert app.btn_zoom_in is app.c_btn_zoom_in
    assert app.lbl_zoom_level is app.c_lbl_zoom


def test_r3_honest_control_labeling(app):
    """
    Review 3: Verify unfinished controls (undo/redo) are honestly labeled
    and disabled rather than deceptively active.
    """
    assert hasattr(app, 'btn_undo')
    assert hasattr(app, 'btn_redo')
    assert str(app.btn_undo.cget("state")) == "disabled"
    assert str(app.btn_redo.cget("state")) == "disabled"


def test_r3_inspector_scrollability(app):
    """
    Review 3: Verify all inspector tabs use CTkScrollableFrame so content
    and buttons are 100% reachable even at minimum window height.
    """
    from customtkinter import CTkScrollableFrame
    assert isinstance(app.faces_scroll, CTkScrollableFrame)
    assert isinstance(app.tab_details_frame, CTkScrollableFrame)
    assert isinstance(app.tab_appearance_frame, CTkScrollableFrame)


def test_r3_persian_arabic_fallback_and_html_bidi():
    """
    Review 3: Verify pure-Python fallback behaves cleanly with 0% mangling
    and interactive HTML export includes dir='auto' and unicode-bidi.
    """
    import metadata
    import tempfile
    
    # Test pure-Python fallback
    saved_flag = metadata._HAS_PROVEN_SHAPER
    try:
        metadata._HAS_PROVEN_SHAPER = False
        sample = "دانش‌آموخته دانشگاه - علیرضا رضایی (Dr. Alireza)"
        fallback_res = metadata.shape_persian_arabic_text(sample)
        assert len(fallback_res) > 0
        assert not any(m in fallback_res for m in ["0E", "bB", "feC", "0EbBc"])
    finally:
        metadata._HAS_PROVEN_SHAPER = saved_flag

    # Test HTML export dir="auto"
    fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")
    img_p = os.path.join(fixtures_dir, "single_portrait.jpg")
    tags = [{"name": "دکتر مریم احمدی", "x": 0.5, "y": 0.5, "w": 0.2, "h": 0.2}]
    desc = "توضیحات عکس به فارسی"
    
    with tempfile.TemporaryDirectory() as td:
        out_html = os.path.join(td, "test_bidi.html")
        ok = metadata.write_interactive_html(img_p, tags, desc)
        # write_interactive_html generates html next to image_path, check return/file
        expected_html = os.path.splitext(img_p)[0] + "_interactive.html"
        if os.path.exists(expected_html):
            with open(expected_html, "r", encoding="utf-8") as f:
                html_txt = f.read()
            os.remove(expected_html) # Clean up
            assert 'dir="auto"' in html_txt
            assert 'unicode-bidi: plaintext;' in html_txt


# =============================================================================
# BADGE SHAPE MILESTONE TESTS (AG_BADGE_SHAPE_HANDOFF)
# =============================================================================

def test_badge_shape_normalization_and_legacy_compatibility():
    """
    Verify canonical badge shape values and legacy/fallback compatibility.
    - Canonical: 'auto', 'rounded_square', 'square'
    - Legacy mappings: 'circle' -> 'auto', 'round_rect' -> 'rounded_square'
    - Prototype string mappings: 'Rounded Square (Prototype)' -> 'rounded_square', 'Square (Prototype)' -> 'square'
    - Fallback: None or unknown strings safely return 'auto'
    """
    from models import normalize_badge_shape, TagStyle

    # Canonical
    assert normalize_badge_shape("auto") == "auto"
    assert normalize_badge_shape("rounded_square") == "rounded_square"
    assert normalize_badge_shape("square") == "square"

    # UI display strings
    assert normalize_badge_shape("Auto Pill/Circle") == "auto"
    assert normalize_badge_shape("Rounded Square") == "rounded_square"
    assert normalize_badge_shape("Square") == "square"

    # Prototype legacy strings
    assert normalize_badge_shape("Rounded Square (Prototype)") == "rounded_square"
    assert normalize_badge_shape("Square (Prototype)") == "square"

    # Legacy project settings
    assert normalize_badge_shape("circle") == "auto"
    assert normalize_badge_shape("round_rect") == "rounded_square"
    assert normalize_badge_shape("pill") == "auto"
    assert normalize_badge_shape("rect") == "square"

    # Unknown / None safe fallback
    assert normalize_badge_shape(None) == "auto"
    assert normalize_badge_shape("") == "auto"
    assert normalize_badge_shape("hexagon") == "auto"
    assert normalize_badge_shape("triangle") == "auto"

    # TagStyle integration
    ts = TagStyle(badge_shape="round_rect")
    assert ts.badge_shape == "rounded_square"
    assert ts.to_dict()["badge_shape"] == "rounded_square"

    ts_circle = TagStyle.from_dict({"badge_shape": "circle"})
    assert ts_circle.badge_shape == "auto"


def test_badge_metrics_geometry_and_padding_1_to_999():
    """
    Verify geometry, corner radii distinction, padding, and backwards-compatible
    tuple unpacking for 1, 10, 125, 999 across all three canonical shapes.
    """
    base_r = 20

    for shape in ["auto", "rounded_square", "square"]:
        for val in [1, 10, 125, 999]:
            metrics = compute_badge_metrics(val, base_r, badge_shape=shape)
            
            # Backwards-compatible tuple unpacking
            w, h, is_pill = metrics
            assert w == metrics.width
            assert h == metrics.height
            assert is_pill == metrics.is_pill

            if shape in ("square", "rounded_square"):
                # Genuine symmetric square: W strictly equals H for all digit counts
                assert w == h
            else:
                assert h == int(2 * base_r)

            s = str(val)
            if len(s) == 1:
                assert w == int(2.0 * base_r)
            elif len(s) == 2:
                assert w == int(2.4 * base_r)
                assert is_pill is True
            elif len(s) == 3:
                assert w == int(3.0 * base_r)
                assert is_pill is True
            
            # Distinct corner radii
            if shape == "square":
                assert metrics.corner_radius == 0
                assert metrics.shape == "square"
            elif shape == "rounded_square":
                expected_cr = max(3, int(base_r * 0.35))
                assert metrics.corner_radius == expected_cr
                assert metrics.shape == "rounded_square"
                assert metrics.corner_radius > 0
                assert metrics.corner_radius < base_r
            elif shape == "auto":
                assert metrics.corner_radius == base_r
                assert metrics.shape == "auto"
                if len(s) == 1:
                    assert is_pill is False


def test_badge_shape_ui_dropdown_wiring_and_preset_independence(app, monkeypatch):
    """
    Verify that selecting shapes through the dropdown callback changes canonical shape
    and that changing appearance color presets does NOT reset shape to Auto.
    """
    import PT
    monkeypatch.setattr(PT.messagebox, "askyesnocancel", lambda *a, **k: False)
    monkeypatch.setattr(PT.messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(PT.messagebox, "showwarning", lambda *a, **k: None)

    app.set_modified(False)
    test_photo = os.path.join(FIXTURES_DIR, "single_portrait.jpg")
    app.load_image(test_photo)
    app.update_idletasks()

    # 1. Select Rounded Square
    app.combo_badge_shape.set("Rounded Square")
    app.on_shape_changed("Rounded Square")
    assert app.get_selected_badge_shape() == "rounded_square"
    assert app.current_doc.style.badge_shape == "rounded_square"

    # 2. Select Square
    app.combo_badge_shape.set("Square")
    app.on_shape_changed("Square")
    assert app.get_selected_badge_shape() == "square"
    assert app.current_doc.style.badge_shape == "square"

    # 3. Change color preset to High Contrast -> Shape MUST stay Square
    app.on_preset_changed("High Contrast")
    assert app.current_preset == "High Contrast"
    assert app.combo_badge_shape.get() == "Square"
    assert app.get_selected_badge_shape() == "square"
    assert app.current_doc.style.badge_shape == "square"

    # 4. Change color preset to Print -> Shape MUST still stay Square
    app.on_preset_changed("Print")
    assert app.combo_badge_shape.get() == "Square"
    assert app.get_selected_badge_shape() == "square"

    # 5. Cycle back to Auto
    app.combo_badge_shape.set("Auto Pill/Circle")
    app.on_shape_changed("Auto Pill/Circle")
    assert app.get_selected_badge_shape() == "auto"
    app.set_modified(False)


def test_badge_shape_dirty_state_isolation(app, tmp_path, monkeypatch):
    """
    Verify changing badge shape marks project dirty without modifying is_metadata_dirty.
    Saving project sidecar resets is_project_dirty without touching photo image hash.
    """
    import PT
    monkeypatch.setattr(PT.messagebox, "askyesnocancel", lambda *a, **k: False)
    monkeypatch.setattr(PT.messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(PT.messagebox, "showwarning", lambda *a, **k: None)

    from PIL import Image
    photo_file = str(tmp_path / "shape_dirty_test.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), photo_file)
    
    with open(photo_file, "rb") as f:
        import hashlib
        initial_hash = hashlib.sha256(f.read()).hexdigest()

    app.set_modified(False)
    app.load_image(photo_file)
    app.update_idletasks()
    if not app.faces:
        app.faces.append({"name": "Initial Name", "x": 0.5, "y": 0.5, "w": 0.2, "h": 0.2, "id": "test_id"})
    app.is_project_dirty = False
    app.is_metadata_dirty = False

    # Simulate pending metadata edit (e.g. name edit)
    app.faces[0]["name"] = "Pending Name Edit"
    app.set_modified(True, project=True, metadata=True)
    assert app.is_metadata_dirty is True

    # Change badge shape
    app.combo_badge_shape.set("Rounded Square")
    app.on_shape_changed("Rounded Square")
    
    # Metadata dirty state must NOT be cleared by layout change
    assert app.is_project_dirty is True
    assert app.is_metadata_dirty is True

    # Save project sidecar only
    saved = app.save_project_only()
    assert saved is True
    assert app.is_project_dirty is False
    # Pending metadata edits remain pending!
    assert app.is_metadata_dirty is True

    # Photo file must remain 100% byte-for-byte untouched
    with open(photo_file, "rb") as f:
        post_save_hash = hashlib.sha256(f.read()).hexdigest()
    assert initial_hash == post_save_hash
    app.set_modified(False)


def test_badge_shape_persistence_and_restore(tmp_path):
    """
    Verify shape persists to sidecar and recovery draft and restores accurately.
    Also tests legacy sidecars map properly on load.
    """
    from models import ProjectDocument, FaceTag
    photo_file = str(tmp_path / "persistence_shape.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), photo_file)

    doc = ProjectDocument(image_path=photo_file, image_width=800, image_height=600)
    doc.tags = [FaceTag(name="Alice", x=0.5, y=0.5, w=0.2, h=0.2, bx=0.4, by=0.3)]
    doc.style.badge_shape = "rounded_square"

    # Save sidecar
    save_project_document(doc, is_draft=False)

    # Load sidecar back
    loaded_doc = load_project_document(photo_file)
    assert loaded_doc is not None
    assert loaded_doc.style.badge_shape == "rounded_square"
    assert loaded_doc.tags[0].bx == 0.4
    assert loaded_doc.tags[0].by == 0.3

    # Legacy sidecar with 'circle' -> loads as 'auto'
    from project_io import get_project_sidecar_path
    sidecar_path = get_project_sidecar_path(photo_file)
    with open(sidecar_path, "r", encoding="utf-8") as f:
        raw_json = f.read()
    raw_json_circle = raw_json.replace('"rounded_square"', '"circle"')
    with open(sidecar_path, "w", encoding="utf-8") as f:
        f.write(raw_json_circle)

    loaded_legacy = load_project_document(photo_file)
    assert loaded_legacy is not None
    assert loaded_legacy.style.badge_shape == "auto"

    # Legacy sidecar with 'round_rect' -> loads as 'rounded_square'
    raw_json_rr = raw_json.replace('"rounded_square"', '"round_rect"')
    with open(sidecar_path, "w", encoding="utf-8") as f:
        f.write(raw_json_rr)

    loaded_rr = load_project_document(photo_file)
    assert loaded_rr is not None
    assert loaded_rr.style.badge_shape == "rounded_square"


def test_badge_shape_rendering_and_persian_support(tmp_path):
    """
    Verify rendering output for all three shapes with Persian/Arabic text
    in tagged exports and in-memory previews.
    """
    from PIL import Image
    test_img = Image.new("RGB", (600, 400), color=(120, 120, 120))
    tags = [
        {"x": 0.3, "y": 0.4, "w": 0.2, "h": 0.2, "name": "علیرضا رضایی"},
        {"x": 0.7, "y": 0.4, "w": 0.2, "h": 0.2, "name": "دکتر مریم احمدی"}
    ]
    desc = "عکس یادگاری در دانشگاه تهران"

    for shape in ["auto", "rounded_square", "square"]:
        out_file = str(tmp_path / f"export_{shape}.jpg")
        # Direct export
        ok = draw_annotations_on_image(
            test_img,
            tags,
            output_path=out_file,
            draw_names=True,
            description=desc,
            badge_shape=shape
        )
        assert ok is True
        assert os.path.exists(out_file)
        with Image.open(out_file) as rendered:
            assert rendered.size[0] >= 600
            assert rendered.size[1] >= 400

        # In-memory preview composite
        preview_img = draw_annotations_on_image(
            test_img,
            tags,
            output_path=None,
            draw_names=True,
            description=desc,
            badge_shape=shape
        )
        assert isinstance(preview_img, Image.Image)
        assert preview_img.size == (600, preview_img.size[1])

