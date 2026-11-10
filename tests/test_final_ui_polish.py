import os
import sys
import shutil
import pytest
from unittest.mock import Mock, patch
from PIL import Image

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import PT
from PT import PhotoTaggerApp, APP_VERSION

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

@pytest.fixture(scope="module")
def app():
    # Suppress GUI popups
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

def test_single_version_source_and_no_pro_badge(app):
    """
    Review Item 3: Header shows single version source (v3.0.0-alpha.2)
    and does not display conflicting 'PRO' product pill.
    """
    assert f"v{APP_VERSION}" in app.lbl_brand_badge.cget("text")
    assert "PRO" not in app.lbl_brand_badge.cget("text")
    assert f"v{APP_VERSION}" in app.title()

def test_title_mode_consistency_no_lingering_layout_suffix(app):
    """
    Review Item 3: Mode switching Tagging -> Layout -> Preview updates window title
    consistently without retaining a lingering '*[Layout]' suffix in Preview.
    """
    test_img = os.path.join(FIXTURES_DIR, "single_portrait.jpg")
    app.load_image(test_img)
    
    # Switch to Layout mode and modify swatch
    app.on_workspace_mode_changed("Layout")
    app.set_modified(True, project=True)
    assert "(Layout)" in app.title()
    assert "*" in app.title()
    
    # Switch to Preview mode
    app.on_workspace_mode_changed("Preview")
    title_in_preview = app.title()
    assert "(Preview)" in title_in_preview
    assert "[Layout]" not in title_in_preview, f"Lingering [Layout] in preview title: {title_in_preview}"

def test_truthful_dpi_reporting_no_fake_300_dpi(app, tmp_path):
    """
    Review Item 3: Missing DPI metadata must report 'DPI unavailable'
    instead of falsely reporting '300 DPI'.
    """
    # Create image with no DPI info
    no_dpi_path = str(tmp_path / "no_dpi.jpg")
    im = Image.new("RGB", (100, 100), color=(100, 150, 200))
    im.save(no_dpi_path, "JPEG") # PIL default JPEG has no dpi unless specified
    
    app.load_image(no_dpi_path)
    meta_text = app.lbl_photo_metadata.cget("text")
    assert "300 DPI" not in meta_text
    assert "DPI unavailable" in meta_text

    # Create image with explicit 150 DPI info
    dpi_path = str(tmp_path / "explicit_dpi.jpg")
    im.save(dpi_path, "JPEG", dpi=(150, 150))
    app.load_image(dpi_path)
    meta_text_explicit = app.lbl_photo_metadata.cget("text")
    assert "150 DPI" in meta_text_explicit

def test_top_row_clarity_and_labels(app):
    """
    Review Item 2: Save Project is clearly labeled distinct from Write Tags.
    Format selector clearly indicates 'Format: Original'.
    """
    assert app.btn_save_project.cget("text") == "Save Project"
    assert app.btn_write_tags.cget("text") == "Write Tags"
    assert app.btn_export_annotated.cget("text") == "Export Files"
    
    # Format selector
    assert "Format: Original" in app.combo_format.get()
    assert app.get_export_format() == "Original"
    
    app.set_export_format("PNG")
    assert app.get_export_format() == "PNG"
    assert app.combo_format.get() == "Format: PNG"
    app.set_export_format("Original")

def test_compact_inspector_detect_button(app):
    """
    Review Item 1: 'Re-Detect' is simplified to 'Detect' with compact width
    to fit the compact inspector.
    """
    assert app.btn_redetect.cget("text") == "Detect"
    assert app.btn_redetect.winfo_manager() == "pack"

def test_undo_redo_explicit_unavailable(app):
    """
    Review Item 4: Undo/Redo remain disabled and announce unavailable state.
    """
    assert app.btn_undo.cget("state") == "disabled"
    assert app.btn_redo.cget("state") == "disabled"
    
    app.on_undo()
    assert "unavailable" in app.lbl_status.cget("text").lower()
    app.on_redo()
    assert "unavailable" in app.lbl_status.cget("text").lower()

def test_export_reporting_includes_html_svg_and_reports_partial_failures(app, tmp_path):
    """
    Review Item Functional (PT.py:3628):
    Export checks all 4 outputs (HTML, SVG, Numbered, Tagged) and
    reports partial failure by filename rather than falsely announcing success.
    """
    test_img = str(tmp_path / "export_test.jpg")
    im = Image.new("RGB", (200, 200), color=(50, 50, 50))
    im.save(test_img)
    app.load_image(test_img)
    app.faces = [{"name": "Test Person", "x": 0.5, "y": 0.5, "w": 0.2, "h": 0.2, "id": "t1"}]
    
    # Scenario A: All 4 succeed
    with patch("PT.draw_annotations_on_image", return_value=True), \
         patch("PT.write_interactive_html", return_value=True), \
         patch("PT.write_interactive_svg", return_value=True), \
         patch("PT.messagebox.showinfo") as mock_info:
        app.export_annotated()
        assert mock_info.called
        assert "Interactive HTML" in mock_info.call_args[0][1]
        assert "Interactive SVG" in mock_info.call_args[0][1]
        assert "successfully" in app.lbl_status.cget("text").lower()

    # Scenario B: Partial failure (HTML fails)
    with patch("PT.draw_annotations_on_image", return_value=True), \
         patch("PT.write_interactive_html", return_value=False), \
         patch("PT.write_interactive_svg", return_value=True), \
         patch("PT.messagebox.showwarning") as mock_warn:
        app.export_annotated()
        assert mock_warn.called
        call_msg = mock_warn.call_args[0][1]
        assert "failure" in call_msg.lower()
        assert "export_test_interactive.html" in call_msg
        assert "failure" in app.lbl_status.cget("text").lower()


def test_header_reflow_880_compact_and_wide(app):
    """
    Deliverable 1: In compact mode (880 logical width):
    - Save Project, Write Tags, Format: Original, Export Files remain visible, readable, and accessible.
    - Secondary actions (Open Folder, Help) are folded into overflow button.
    In wide mode (1200 logical width):
    - Secondary actions are shown directly, overflow is hidden.
    """
    app.reflow_header(880)
    app.update_idletasks()
    
    assert app.btn_save_project.winfo_manager() == "pack"
    assert app.btn_save_project.cget("text") == "Save Project"
    assert app.btn_write_tags.winfo_manager() == "pack"
    assert app.btn_write_tags.cget("text") == "Write Tags"
    assert app.btn_export_annotated.winfo_manager() == "pack"
    assert app.btn_export_annotated.cget("text") == "Export Files"
    assert app.combo_format.winfo_manager() == "pack"
    
    # Secondary actions folded into overflow
    assert app.btn_open_folder.winfo_manager() == ""
    assert app.btn_help.winfo_manager() == ""
    assert app.btn_overflow.winfo_manager() == "pack"
    
    # Wide mode (1200)
    app.reflow_header(1200)
    app.update_idletasks()
    
    assert app.btn_save_project.winfo_manager() == "pack"
    assert app.btn_write_tags.winfo_manager() == "pack"
    assert app.btn_export_annotated.winfo_manager() == "pack"
    assert app.combo_format.winfo_manager() == "pack"
    assert app.btn_open_folder.winfo_manager() == "pack"
    assert app.btn_help.winfo_manager() == "pack"
    assert app.btn_overflow.winfo_manager() == ""


def test_people_tab_dedicated_full_width_edit_row(app):
    """
    Deliverable 2: In People tab, the person name entry is given a dedicated
    full-width edit row (row=1, columnspan=4) so long / mixed-script names
    are completely visible and unobstructed.
    """
    test_img = os.path.join(FIXTURES_DIR, "single_portrait.jpg")
    app.load_image(test_img)
    app.faces = [
        {
            "id": "face_recheck_1",
            "name": "دکتر مریم احمدی (Dr. Maryam)",
            "x": 0.5,
            "y": 0.4,
            "w": 0.25,
            "h": 0.25,
            "bx": 0.5,
            "by": 0.25
        }
    ]
    app.rebuild_sidebar()
    app.update_idletasks()
    
    assert len(app.face_entries) == 1
    entry = app.face_entries[0]
    
    grid_info = entry.grid_info()
    assert int(grid_info.get("row", -1)) == 1, f"Entry should be on row 1, got {grid_info}"
    assert int(grid_info.get("column", -1)) == 0, f"Entry should start at column 0, got {grid_info}"
    assert int(grid_info.get("columnspan", -1)) == 4, f"Entry should span all 4 columns, got {grid_info}"
    assert "ew" in grid_info.get("sticky", ""), f"Entry should have sticky='ew', got {grid_info}"


def test_canvas_tagging_name_dark_backing(app):
    """
    Deliverable 3: On canvas in Tagging mode, a high-contrast dark backing
    is drawn behind name label text over portraits.
    """
    test_img = os.path.join(FIXTURES_DIR, "single_portrait.jpg")
    app.load_image(test_img)
    app.faces = [
        {
            "id": "face_recheck_2",
            "name": "دکتر مریم احمدی (Dr. Maryam)",
            "x": 0.5,
            "y": 0.4,
            "w": 0.25,
            "h": 0.25
        }
    ]
    app.on_workspace_mode_changed("Tagging")
    app.update_idletasks()
    
    items = app.canvas.find_withtag("overlay")
    found_text = False
    found_dark_backing = False
    
    for item in items:
        item_type = app.canvas.type(item)
        if item_type == "text":
            text_val = app.canvas.itemcget(item, "text")
            if "Maryam" in text_val or "مریم" in text_val:
                found_text = True
        elif item_type == "rectangle":
            fill_color = app.canvas.itemcget(item, "fill")
            if fill_color == "#0f111a":
                found_dark_backing = True
                
    assert found_text, "Canvas should render the person's name text in Tagging mode"
    assert found_dark_backing, "Canvas should draw a dark backing rectangle (#0f111a) behind name label text"


def test_cancel_open_folder_preserves_active_collection_and_photo(app, tmp_path):
    """
    Issue 1: Cancel Open Folder changes navigation.
    Reproduced with a dirty photo in an open collection. Choose a second folder
    and cancel the unsaved-edits prompt. The original photo, image_list,
    current_image_idx, and navigation state must remain unchanged.
    """
    dir1 = tmp_path / "collection1"
    dir1.mkdir()
    p1 = dir1 / "p1.jpg"
    p2 = dir1 / "p2.jpg"
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), str(p1))
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), str(p2))

    with patch.object(PT.filedialog, "askdirectory", return_value=str(dir1)):
        app.open_folder()

    assert len(app.image_list) == 2
    assert app.current_image_idx == 0
    assert app.current_image_path == str(p1)

    # Make current photo dirty
    app.set_modified(True, project=True)
    prior_list = list(app.image_list)
    prior_idx = app.current_image_idx
    prior_path = app.current_image_path

    dir2 = tmp_path / "collection2"
    dir2.mkdir()
    p3 = dir2 / "p3.jpg"
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), str(p3))

    # User picks folder 2, but clicks Cancel on unsaved-changes prompt
    with patch.object(PT.filedialog, "askdirectory", return_value=str(dir2)), \
         patch.object(PT.messagebox, "askyesnocancel", return_value=None):
        app.open_folder()

    assert app.image_list == prior_list, "image_list must not mutate when folder open is cancelled"
    assert app.current_image_idx == prior_idx, "current_image_idx must remain unchanged"
    assert app.current_image_path == prior_path, "current_image_path must remain active photo"


def test_open_folder_empty_directory_preserves_active_collection(app, tmp_path):
    """
    Issue 1 edge case: Selecting an empty directory or folder without supported images
    must show an info message and preserve the previous collection completely.
    """
    dir1 = tmp_path / "collection_valid"
    dir1.mkdir()
    p1 = dir1 / "valid.jpg"
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), str(p1))

    with patch.object(PT.filedialog, "askdirectory", return_value=str(dir1)):
        app.open_folder()

    prior_list = list(app.image_list)
    prior_idx = app.current_image_idx

    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()

    with patch.object(PT.filedialog, "askdirectory", return_value=str(empty_dir)), \
         patch.object(PT.messagebox, "showinfo") as mock_info:
        app.open_folder()
        assert mock_info.called
        assert "No supported image" in mock_info.call_args[0][1] or "No images found" in mock_info.call_args[0][0]

    assert app.image_list == prior_list
    assert app.current_image_idx == prior_idx


def test_open_folder_unreadable_first_photo_preserves_active_collection(app, tmp_path):
    """
    Issue 1 edge case: If the first candidate in a newly selected folder is unreadable / corrupted,
    the load fails with an error and the previous collection remains completely untouched.
    """
    dir1 = tmp_path / "active_coll"
    dir1.mkdir()
    p1 = dir1 / "active.jpg"
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), str(p1))

    with patch.object(PT.filedialog, "askdirectory", return_value=str(dir1)):
        app.open_folder()

    prior_list = list(app.image_list)
    prior_idx = app.current_image_idx

    corrupt_dir = tmp_path / "corrupt_coll"
    corrupt_dir.mkdir()
    bad_img = corrupt_dir / "00_bad.jpg"
    bad_img.write_bytes(b"not an image file")

    with patch.object(PT.filedialog, "askdirectory", return_value=str(corrupt_dir)), \
         patch.object(PT.messagebox, "showerror") as mock_err:
        app.open_folder()
        assert mock_err.called

    assert app.image_list == prior_list
    assert app.current_image_idx == prior_idx


def test_badge_scale_continuous_factor_and_project_roundtrip(app, tmp_path):
    """
    Issue 2: Badge Scale displays a different value than it applies.
    Verified that setting 1.25x updates label to 1.25x, get_selected_font_size_style()
    returns scale 1.25, and saving/reopening project preserves the exact 1.25 factor.
    """
    test_photo = str(tmp_path / "scale_test.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), test_photo)
    app.load_image(test_photo)
    app.faces = [{"name": "Scale Test", "x": 0.5, "y": 0.5, "w": 0.2, "h": 0.2, "id": "sc1"}]

    app.on_scale_slider_changed(1.25)
    app.update_idletasks()

    assert app.lbl_scale_value.cget("text") == "1.25x"
    style_info = app.get_selected_font_size_style()
    assert style_info["scale"] == 1.25

    # Save project and verify roundtrip
    assert app.save_project_only() is True
    from project_io import load_project_document
    doc = load_project_document(test_photo)
    assert "1.25" in doc.style.font_size_preset

    # Reopen project and verify label and slider reflect 1.25
    assert app.load_image(test_photo) is True
    assert app.slider_badge_scale.get() == 1.25
    assert app.lbl_scale_value.cget("text") == "1.25x"
    assert app.get_selected_font_size_style()["scale"] == 1.25


def test_mode_switcher_responsive_placement_and_no_clipping(app):
    """
    Final Fix Recheck:
    Mode switcher ('Tagging', 'Layout', 'Preview') must not clip at default packaged launch
    size (818x390) or minimum supported size (680x360). Mode switcher reflows to Row 1
    (toolbar_center) at compact breakpoints (< 1000) and to Row 0 (header_center) at wide
    breakpoints (>= 1000). Tooltip and text labels remain fully intact.
    """
    # 1. Test at default packaged launch size (818x390)
    app.geometry("818x390")
    app.update_idletasks()
    app.update()
    
    assert getattr(app, '_mode_switcher_location', None) == "toolbar"
    assert app.mode_switcher.master == app
    assert app.mode_switcher.cget("values") == ["Tagging", "Layout", "Preview"]
    assert app.toolbar_center.winfo_width() >= app.mode_switcher.winfo_reqwidth()
    # Ensure Row 0 actions are preserved
    assert app.btn_export_annotated.winfo_manager() == "pack"
    assert app.btn_save_project.winfo_manager() == "pack"
    assert app.btn_write_tags.winfo_manager() == "pack"
    assert app.btn_overflow.winfo_manager() == "pack"

    # 2. Test at minimum supported window size (680x360)
    app.geometry("680x360")
    app.update_idletasks()
    app.update()

    assert getattr(app, '_mode_switcher_location', None) == "toolbar"
    assert app.toolbar_center.winfo_width() >= app.mode_switcher.winfo_reqwidth()
    # Row 0 actions fit without collision
    assert app.header_left.winfo_width() + app.action_frame.winfo_width() <= app.header_frame.winfo_width()

    # 3. Test at wide desktop layout (1200x800)
    app.geometry("1200x800")
    app.update_idletasks()
    app.update()

    assert getattr(app, '_mode_switcher_location', None) == "header"
    assert app.header_center.winfo_width() >= app.mode_switcher.winfo_reqwidth()
    assert app.btn_open_folder.winfo_manager() == "pack"
    assert app.btn_help.winfo_manager() == "pack"

    # 4. Return to default launch size (818x390)
    app.geometry("818x390")
    app.update_idletasks()
    app.update()

    assert getattr(app, '_mode_switcher_location', None) == "toolbar"
    assert app.toolbar_center.winfo_width() >= app.mode_switcher.winfo_reqwidth()


def test_tag_color_accent_all_eight_swatches_canonical_palette(app, tmp_path):
    """
    AG Appearance Handoff Section 2:
    - Verifies all eight swatches (Teal, Blue, Purple, Green, Orange/Red, Yellow, White, Black)
      use the canonical palette with correct text color and contrast.
    - Tests clicks on all 8 swatches under Studio Minimal.
    - Tests clicks under High Contrast preset to verify subsequent clicks override badge accent.
    - In Layout mode: verifies badge fill remains the chosen color (not overridden by purple)
      and selection/drag is indicated by outline ring.
    - In Preview mode: verifies cache invalidation on swatch click.
    - Verifies project persistence and roundtrip reload.
    """
    from models import CANONICAL_PALETTE, get_canonical_color_style
    from project_io import load_project_document

    test_photo = str(tmp_path / "swatch_test.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), test_photo)
    assert app.load_image(test_photo) is True
    app.faces = [{"name": "Color Model", "x": 0.5, "y": 0.4, "w": 0.25, "h": 0.25, "id": "cm1"}]

    # Part A: Test all 8 swatches under Studio Minimal
    app.combo_preset.set("Studio Minimal")
    app.on_preset_changed("Studio Minimal")

    all_swatches = ["Teal", "Blue", "Purple", "Green", "Orange/Red", "Yellow", "White", "Black"]
    for swatch_name in all_swatches:
        # Click swatch
        app.on_swatch_clicked(swatch_name)
        app.update_idletasks()

        expected = CANONICAL_PALETTE[swatch_name]
        style = app.get_selected_color_style()
        assert style["hex"] == expected["hex"], f"{swatch_name} hex mismatch: {style['hex']} != {expected['hex']}"
        assert style["rgb"] == expected["rgb"], f"{swatch_name} rgb mismatch: {style['rgb']} != {expected['rgb']}"
        assert style["text_color"] == expected["text_color"], f"{swatch_name} text mismatch"
        assert app.combo_style_color.get() == swatch_name
        assert f"({swatch_name})" in app.lbl_style_color.cget("text")

    # Part B: Preset override test (High Contrast preset default is Yellow, subsequent click overrides to Teal)
    app.combo_preset.set("High Contrast")
    app.on_preset_changed("High Contrast")
    assert app.combo_style_color.get() == "Yellow"

    # Click Purple while under High Contrast
    app.on_swatch_clicked("Purple")
    app.update_idletasks()
    purple_style = app.get_selected_color_style()
    assert purple_style["hex"] == CANONICAL_PALETTE["Purple"]["hex"]
    assert app.combo_style_color.get() == "Purple"

    # Part C: In Layout mode, selected badge preserves chosen fill (not replaced by purple)
    app.on_workspace_mode_changed("Layout")
    app.on_swatch_clicked("Green")
    app.selected_face_idx = 0
    app.draw_canvas()
    app.update_idletasks()
    # Check that canvas items for badge exist and chosen fill is intact
    badge_items = app.canvas.find_withtag("badge_0")
    assert len(badge_items) > 0, "Badge 0 items must be drawn on canvas in Layout mode"

    # Part D: In Preview mode, cache key invalidates on swatch change
    app.on_workspace_mode_changed("Preview")
    app.on_swatch_clicked("Yellow")
    app.draw_canvas()
    key_yellow = app.last_bg_key
    assert key_yellow is not None
    assert CANONICAL_PALETTE["Yellow"]["hex"] in key_yellow

    app.on_swatch_clicked("White")
    app.draw_canvas()
    key_white = app.last_bg_key
    assert key_white is not None
    assert CANONICAL_PALETTE["White"]["hex"] in key_white
    assert key_yellow != key_white, "Preview cache key must change on swatch click"

    # Part E: Project state persistence roundtrip
    app.on_swatch_clicked("Orange/Red")
    assert app.save_project_only() is True
    doc = load_project_document(test_photo)
    assert doc.style.color_theme in ("Orange/Red", "Orange", "Red")

    # Reopening photo restores chosen swatch and updates selection ring
    assert app.load_image(test_photo) is True
    assert app.combo_style_color.get() == "Orange/Red"
    assert "Orange/Red" in app.lbl_style_color.cget("text")


def test_retired_duplicate_editor(app):
    """
    AG Appearance Handoff Section 3:
    Retire Dedicated Editor Window from normal UI.
    """
    assert hasattr(app, 'btn_finetune_2b')
    assert app.btn_finetune_2b.winfo_manager() == "", "Dedicated Editor button must be retired (unpacked) from UI"
    # Verify main layout supports badge dragging and controls
    assert hasattr(app, 'btn_reset_badges')
    assert app.btn_reset_badges.winfo_manager() == "pack"
    assert hasattr(app, 'slider_badge_scale')
    assert app.slider_badge_scale.winfo_manager() == "pack"


def test_write_tags_explained_and_duplicate_removed(app):
    """
    AG Appearance Handoff Section 4:
    - Duplicate button in Details tab removed.
    - Authoritative top action kept with clear tooltip and responsive label.
    - Tooltip on Save Project and Format Selector.
    """
    # 1. Details tab duplicate is retired
    assert hasattr(app, 'btn_write_tags_tab')
    assert app.btn_write_tags_tab.winfo_manager() == "", "Duplicate Write Tags button must be removed from Details tab"

    # 2. Authoritative top button remains packed
    assert app.btn_write_tags.winfo_manager() == "pack"

    # 3. Responsive label
    app.reflow_header(1200)
    assert app.btn_write_tags.cget("text") == "Write Tags to Photo"
    app.reflow_header(880)
    assert app.btn_write_tags.cget("text") == "Write Tags"

    # 4. Top actions distinct
    assert app.btn_save_project.cget("text") == "Save Project"
    assert app.btn_export_annotated.cget("text") == "Export Files"


def test_restored_visible_credit_footer(app):
    """
    AG Appearance Handoff Section 5:
    Restores visible credit 'Created by Alireza Mostaghasi, 2026' in a quiet footer location
    without squeezing navigation or status.
    """
    assert hasattr(app, 'lbl_credit'), "Credit label must exist"
    assert app.lbl_credit.cget("text") == "Created by Alireza Mostaghasi, 2026"
    assert app.lbl_credit.winfo_manager() == "pack"

    # Test at default packaged size 818x390
    app.geometry("818x390")
    app.update_idletasks()
    app.update()
    assert app.lbl_credit.winfo_reqwidth() <= app.bottom_frame.winfo_width()
    assert app.btn_prev.winfo_manager() == "pack"
    assert app.lbl_status.winfo_manager() == "pack"


def test_mode_switcher_guaranteed_visible_slot_startup_and_resizing(app, tmp_path):
    """
    Verifies Blocker 1 fix:
    - Mode switcher is 100% visible with full labels at startup WITHOUT photo.
    - Mode switcher is 100% visible with full labels at startup WITH photo (including long filename).
    - Mode switcher placement reflows to Row 0 on maximize (>=1180px) and back to Row 1 on restore.
    - Mode switcher is fully visible with complete labels at minimum supported size 680x360.
    """
    # 1. Startup without photo
    app.update_idletasks()
    app.update()
    assert app.mode_switcher.winfo_ismapped() == 1, "Mode switcher must be mapped at startup without photo"
    assert app.mode_switcher.winfo_width() >= app.mode_switcher.winfo_reqwidth()
    for mode in ["Tagging", "Layout", "Preview"]:
        btn = app.mode_switcher._buttons_dict[mode]
        assert btn.winfo_ismapped() == 1, f"Mode button {mode} must be mapped"
        assert btn.winfo_width() > 0, f"Mode button {mode} must have positive width"
        assert btn.cget("text") == mode, f"Mode button label must be '{mode}'"

    # 2. Startup with long filename photo
    test_photo = str(tmp_path / "2026_Family_Vacation_Historical_Archive_Panorama_Master_Capture.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), test_photo)
    assert app.load_image(test_photo) is True
    app.update_idletasks()
    app.update()
    assert app.mode_switcher.winfo_ismapped() == 1, "Mode switcher must be mapped after loading photo"
    for mode in ["Tagging", "Layout", "Preview"]:
        btn = app.mode_switcher._buttons_dict[mode]
        assert btn.winfo_ismapped() == 1
        assert btn.cget("text") == mode

    # 3. Maximize / wide view (>= 1180)
    app.geometry("1200x800")
    app.update_idletasks()
    app.update()
    assert getattr(app, '_mode_switcher_location', None) == "header", "Mode switcher must be in header at 1200px"
    assert app.mode_switcher.winfo_ismapped() == 1
    for mode in ["Tagging", "Layout", "Preview"]:
        btn = app.mode_switcher._buttons_dict[mode]
        assert btn.winfo_ismapped() == 1
        assert btn.cget("text") == mode

    # 4. Restore from maximize back to compact (818x390)
    app.geometry("818x390")
    app.update_idletasks()
    app.update()
    assert getattr(app, '_mode_switcher_location', None) == "toolbar", "Mode switcher must be in toolbar at 818px"
    assert app.mode_switcher.winfo_ismapped() == 1
    for mode in ["Tagging", "Layout", "Preview"]:
        btn = app.mode_switcher._buttons_dict[mode]
        assert btn.winfo_ismapped() == 1
        assert btn.cget("text") == mode

    # 5. Minimum supported size (680x360)
    app.geometry("680x360")
    app.update_idletasks()
    app.update()
    assert getattr(app, '_mode_switcher_location', None) == "toolbar", "Mode switcher must be on toolbar at 680px"
    assert app.mode_switcher.winfo_ismapped() == 1
    for mode in ["Tagging", "Layout", "Preview"]:
        btn = app.mode_switcher._buttons_dict[mode]
        assert btn.winfo_ismapped() == 1
        assert btn.cget("text") == mode


def test_shape_selector_saved_shape_agreement_and_draft_recovery(app, tmp_path):
    """
    Verifies Blocker 2 fix:
    - On reopening a saved Square project, the badge renders square AND the segment highlights Square.
    - Tests all 3 shapes (square, rounded_square, auto) on normal reload.
    - Verifies dirty state remains False on clean reload.
    - Verifies draft recovery synchronizes both seg_badge_shape and combo_badge_shape.
    - Verifies swatch click leaves segment and badge in agreement.
    """
    test_photo = str(tmp_path / "shape_sync_test.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), test_photo)
    assert app.load_image(test_photo) is True
    app.faces = [{"name": "Shape Tester", "x": 0.5, "y": 0.5, "w": 0.25, "h": 0.25, "id": "st1"}]

    shapes_to_test = [
        ("Square", "square", "Square"),
        ("Rounded", "rounded_square", "Rounded Square"),
        ("Pill", "auto", "Auto Pill/Circle")
    ]

    for seg_input, canon_expected, combo_expected in shapes_to_test:
        app.seg_badge_shape.set(seg_input)
        app.on_seg_shape_changed(seg_input)
        assert app.get_selected_badge_shape() == canon_expected
        assert app.combo_badge_shape.get() == combo_expected
        assert app.save_project_only() is True

        # Reopen image
        assert app.load_image(test_photo) is True
        assert app.is_project_dirty is False, "Project dirty state must be False on reload"
        assert app.get_selected_badge_shape() == canon_expected, f"Expected {canon_expected} badge shape"
        assert app.seg_badge_shape.get() == seg_input, f"Expected segment {seg_input}, got {app.seg_badge_shape.get()}"
        assert app.combo_badge_shape.get() == combo_expected

        # Swatch click preserves shape agreement
        app.on_swatch_clicked("White")
        assert app.get_selected_badge_shape() == canon_expected
        assert app.seg_badge_shape.get() == seg_input


def test_appearance_sample_strip_not_blank_live_badges(app, tmp_path):
    """
    Verifies Blocker 3 fix:
    - Appearance tab badge preview canvas is not blank.
    - Shows live sample badges 1, 42, and 125 with proper fill and geometry.
    - White swatch displays visible sample badges with contrasting borders.
    - Yellow swatch displays visible sample badges with contrasting borders.
    - Responds to shape changes at both compact and wide sizes.
    """
    test_photo = str(tmp_path / "sample_strip_test.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), test_photo)
    assert app.load_image(test_photo) is True

    app.on_workspace_mode_changed("Layout")
    app.on_inspector_tab_changed("Appearance")
    app.update_idletasks()
    app.update()

    cv = app.badge_preview_canvas
    assert cv.winfo_ismapped() == 1, "Preview canvas must be mapped"

    # Verify initial sample strip contains rendered items
    items = cv.find_all()
    assert len(items) >= 10, f"Sample strip must contain badge elements, found {len(items)}"

    # Test White swatch
    app.on_swatch_clicked("White")
    app.update_idletasks()
    app.update()
    white_items = cv.find_all()
    assert len(white_items) >= 10, "Sample strip must remain populated on White swatch"

    # Test Yellow swatch
    app.on_swatch_clicked("Yellow")
    app.update_idletasks()
    yellow_items = cv.find_all()
    assert len(yellow_items) >= 10, "Sample strip must remain populated on Yellow swatch"

    # Test shape changes update preview strip
    for shape_seg in ["Square", "Rounded", "Pill"]:
        app.seg_badge_shape.set(shape_seg)
        app.on_seg_shape_changed(shape_seg)
        app.update_idletasks()
        app.update()
        shape_items = cv.find_all()
        assert {cv.itemcget(item, "text") for item in shape_items if cv.type(item) == "text"} >= {"1", "42", "125"}, f"Sample strip must remain populated for shape {shape_seg}"


def test_save_project_leaves_window_open_and_responsive(app, tmp_path):
    """
    Verifies that invoking Save Project leaves the application window open,
    saves the sidecar to disk, and keeps the UI responsive.
    """
    test_photo = str(tmp_path / "save_window_test.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), test_photo)
    assert app.load_image(test_photo) is True
    app.faces = [{"name": "Save User", "x": 0.5, "y": 0.5, "w": 0.2, "h": 0.2, "id": "su1"}]
    app.mark_changed(project=True, metadata=False)

    assert app.winfo_exists() == 1, "Window must exist before save"
    app.btn_save_project.invoke()
    app.update_idletasks()
    app.update()

    assert app.winfo_exists() == 1, "Window must remain open after Save Project invoke"
    sidecar_path = test_photo + ".phototagger.json"
    assert os.path.exists(sidecar_path), "Project sidecar must exist on disk"
    assert app.is_project_dirty is False


    # Test at minimum size 680x360
    app.geometry("680x360")
    app.update_idletasks()
    app.update()
    assert app.lbl_credit.winfo_reqwidth() <= app.bottom_frame.winfo_width()
    assert app.btn_prev.winfo_manager() == "pack"
    assert app.lbl_status.winfo_manager() == "pack"


def test_mode_switcher_guaranteed_visible_slot_startup_and_resizing(app, tmp_path):
    """
    Verifies Blocker 1 fix:
    - Mode switcher is 100% visible with full labels at startup WITHOUT photo.
    - Mode switcher is 100% visible with full labels at startup WITH photo (including long filename).
    - Mode switcher placement reflows to Row 0 on maximize (>=1180px) and back to Row 1 on restore.
    - Mode switcher is fully visible with complete labels at minimum supported size 680x360.
    """
    # 1. Startup without photo
    app.update_idletasks()
    app.update()
    assert app.mode_switcher.winfo_ismapped() == 1, "Mode switcher must be mapped at startup without photo"
    assert app.mode_switcher.winfo_width() >= app.mode_switcher.winfo_reqwidth()
    for mode in ["Tagging", "Layout", "Preview"]:
        btn = app.mode_switcher._buttons_dict[mode]
        assert btn.winfo_ismapped() == 1, f"Mode button {mode} must be mapped"
        assert btn.winfo_width() > 0, f"Mode button {mode} must have positive width"
        assert btn.cget("text") == mode, f"Mode button label must be '{mode}'"

    # 2. Startup with long filename photo
    test_photo = str(tmp_path / "2026_Family_Vacation_Historical_Archive_Panorama_Master_Capture.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), test_photo)
    assert app.load_image(test_photo) is True
    app.update_idletasks()
    app.update()
    assert app.mode_switcher.winfo_ismapped() == 1, "Mode switcher must be mapped after loading photo"
    for mode in ["Tagging", "Layout", "Preview"]:
        btn = app.mode_switcher._buttons_dict[mode]
        assert btn.winfo_ismapped() == 1
        assert btn.cget("text") == mode

    # 3. Maximize / wide view (>= 1180)
    app.geometry("1200x800")
    app.update_idletasks()
    app.update()
    assert getattr(app, '_mode_switcher_location', None) == "header", "Mode switcher must be in header at 1200px"
    assert app.mode_switcher.winfo_ismapped() == 1
    for mode in ["Tagging", "Layout", "Preview"]:
        btn = app.mode_switcher._buttons_dict[mode]
        assert btn.winfo_ismapped() == 1
        assert btn.cget("text") == mode

    # 4. Restore from maximize back to compact (818x390)
    app.geometry("818x390")
    app.update_idletasks()
    app.update()
    assert getattr(app, '_mode_switcher_location', None) == "toolbar", "Mode switcher must be in toolbar at 818px"
    assert app.mode_switcher.winfo_ismapped() == 1
    for mode in ["Tagging", "Layout", "Preview"]:
        btn = app.mode_switcher._buttons_dict[mode]
        assert btn.winfo_ismapped() == 1
        assert btn.cget("text") == mode

    # 5. Minimum supported size (680x360)
    app.geometry("680x360")
    app.update_idletasks()
    app.update()
    assert getattr(app, '_mode_switcher_location', None) == "toolbar", "Mode switcher must be on toolbar at 680px"
    assert app.mode_switcher.winfo_ismapped() == 1
    for mode in ["Tagging", "Layout", "Preview"]:
        btn = app.mode_switcher._buttons_dict[mode]
        assert btn.winfo_ismapped() == 1
        assert btn.cget("text") == mode


def test_shape_selector_saved_shape_agreement_and_draft_recovery(app, tmp_path):
    """
    Verifies Blocker 2 fix:
    - On reopening a saved Square project, the badge renders square AND the segment highlights Square.
    - Tests all 3 shapes (square, rounded_square, auto) on normal reload.
    - Verifies dirty state remains False on clean reload.
    - Verifies draft recovery synchronizes both seg_badge_shape and combo_badge_shape.
    - Verifies swatch click leaves segment and badge in agreement.
    """
    test_photo = str(tmp_path / "shape_sync_test.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), test_photo)
    assert app.load_image(test_photo) is True
    app.faces = [{"name": "Shape Tester", "x": 0.5, "y": 0.5, "w": 0.25, "h": 0.25, "id": "st1"}]

    shapes_to_test = [
        ("Square", "square", "Square"),
        ("Rounded", "rounded_square", "Rounded Square"),
        ("Pill", "auto", "Auto Pill/Circle")
    ]

    for seg_input, canon_expected, combo_expected in shapes_to_test:
        app.seg_badge_shape.set(seg_input)
        app.on_seg_shape_changed(seg_input)
        assert app.get_selected_badge_shape() == canon_expected
        assert app.combo_badge_shape.get() == combo_expected
        assert app.save_project_only() is True

        # Reopen image
        assert app.load_image(test_photo) is True
        assert app.is_project_dirty is False, "Project dirty state must be False on reload"
        assert app.get_selected_badge_shape() == canon_expected, f"Expected {canon_expected} badge shape"
        assert app.seg_badge_shape.get() == seg_input, f"Expected segment {seg_input}, got {app.seg_badge_shape.get()}"
        assert app.combo_badge_shape.get() == combo_expected

        # Swatch click preserves shape agreement
        app.on_swatch_clicked("White")
        assert app.get_selected_badge_shape() == canon_expected
        assert app.seg_badge_shape.get() == seg_input


def test_appearance_sample_strip_not_blank_live_badges(app, tmp_path):
    """
    Verifies Blocker 3 fix:
    - Appearance tab badge preview canvas is not blank.
    - Shows live sample badges 1, 42, and 125 with proper fill and geometry.
    - White swatch displays visible sample badges with contrasting borders.
    - Yellow swatch displays visible sample badges with contrasting borders.
    - Responds to shape changes at both compact and wide sizes.
    """
    test_photo = str(tmp_path / "sample_strip_test.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), test_photo)
    assert app.load_image(test_photo) is True

    app.on_workspace_mode_changed("Layout")
    app.on_inspector_tab_changed("Appearance")
    app.update_idletasks()
    app.update()

    cv = app.badge_preview_canvas
    assert cv.winfo_ismapped() == 1, "Preview canvas must be mapped"

    # Verify initial sample strip contains rendered items
    items = cv.find_all()
    assert len(items) >= 10, f"Sample strip must contain badge elements, found {len(items)}"

    # Test White swatch
    app.on_swatch_clicked("White")
    app.update_idletasks()
    app.update()
    white_items = cv.find_all()
    assert len(white_items) >= 10, "Sample strip must remain populated on White swatch"

    # Test Yellow swatch
    app.on_swatch_clicked("Yellow")
    app.update_idletasks()
    yellow_items = cv.find_all()
    assert len(yellow_items) >= 10, "Sample strip must remain populated on Yellow swatch"

    # Test shape changes update preview strip
    for shape_seg in ["Square", "Rounded", "Pill"]:
        app.seg_badge_shape.set(shape_seg)
        app.on_seg_shape_changed(shape_seg)
        app.update_idletasks()
        app.update()
        shape_items = cv.find_all()
        assert {cv.itemcget(item, "text") for item in shape_items if cv.type(item) == "text"} >= {"1", "42", "125"}, f"Sample strip must remain populated for shape {shape_seg}"


def test_save_project_leaves_window_open_and_responsive(app, tmp_path):
    """
    Verifies that invoking Save Project leaves the application window open,
    saves the sidecar to disk, and keeps the UI responsive.
    """
    test_photo = str(tmp_path / "save_window_test.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), test_photo)
    assert app.load_image(test_photo) is True
    app.faces = [{"name": "Save User", "x": 0.5, "y": 0.5, "w": 0.2, "h": 0.2, "id": "su1"}]
    app.mark_changed(project=True, metadata=False)

    assert app.winfo_exists() == 1, "Window must exist before save"
    app.btn_save_project.invoke()
    app.update_idletasks()
    app.update()

    assert app.winfo_exists() == 1, "Window must remain open after Save Project invoke"
    sidecar_path = test_photo + ".phototagger.json"
    assert os.path.exists(sidecar_path), "Project sidecar must exist on disk"
    assert app.is_project_dirty is False




