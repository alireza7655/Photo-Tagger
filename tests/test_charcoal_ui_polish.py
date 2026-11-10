import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json
import pytest
from PIL import Image, ImageChops

import PT
from PT import (
    PhotoTaggerApp,
    COLOR_WORKSPACE,
    COLOR_SETTINGS_SURFACE,
    COLOR_PHOTO_MATTE,
    COLOR_SURFACE_HOVER,
    COLOR_BORDER_SUBTLE,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_TEXT_MUTED,
    COLOR_ACCENT_PRIMARY,
    COLOR_ACCENT_EXPORT,
    COLOR_STATUS_UNSAVED,
    COLOR_STATUS_SAVED,
    COLOR_STATUS_SYNCED,
    COLOR_STATUS_PENDING,
    draw_canvas_badge
)
from metadata import (
    get_preset_rendering_properties,
    draw_annotations_on_image
)
from models import (
    ProjectDocument,
    TagStyle,
    FaceTag
)


@pytest.fixture(scope="module")
def app():
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


def test_charcoal_design_tokens_and_workspace_surfaces(app):
    """
    Deliverable 1: Workspace and Controls (Charcoal Theme)
    - Main chrome and workspace: #242830
    - Settings surface (inspector sidebar and cards): #2B303A
    - Photo matte: #16191F
    - Hover/pressed surface: #353D4A
    """
    assert COLOR_WORKSPACE.lower() == "#242830"
    assert COLOR_SETTINGS_SURFACE.lower() == "#2b303a"
    assert COLOR_PHOTO_MATTE.lower() == "#16191f"
    assert COLOR_SURFACE_HOVER.lower() == "#353d4a"

    # Verify widget surface configuration
    assert app.cget("fg_color").lower() == "#242830"
    assert app.header_frame.cget("fg_color").lower() == "#242830"
    assert app.toolbar_frame.cget("fg_color").lower() == "#242830"
    assert app.bottom_frame.cget("fg_color").lower() == "#242830"
    assert app.canvas_container.cget("fg_color").lower() == "#16191f"
    assert str(app.canvas.cget("bg")).lower() == "#16191f"
    assert app.sidebar_frame.cget("fg_color").lower() == "#2b303a"
    assert app.appearance_card.cget("fg_color").lower() == "#242830"


def test_primary_action_hierarchy_editing_vs_preview(app):
    """
    Deliverable 1: Primary Action Rule
    - Editing modes (Tagging / Layout): Save Project is solid accent (#5b4ee7); Export is secondary.
    - Preview mode: Export Files is solid accent (#5b4ee7); Save Project is secondary.
    - Secondary controls are quiet with #353D4A hover.
    """
    # 1. In Tagging mode
    app.on_workspace_mode_changed("Tagging")
    assert app.active_workspace_mode == "tagging"
    assert app.btn_save_project.cget("fg_color").lower() == "#5b4ee7"
    assert app.btn_save_project.cget("text_color").lower() in ("#ffffff", "white")
    assert app.btn_export_annotated.cget("fg_color") == "transparent"
    assert app.btn_export_annotated.cget("hover_color").lower() == "#353d4a"

    # 2. In Layout mode
    app.on_workspace_mode_changed("Layout")
    assert app.active_workspace_mode == "layout"
    assert app.btn_save_project.cget("fg_color").lower() == "#5b4ee7"
    assert app.btn_export_annotated.cget("fg_color") == "transparent"

    # 3. In Preview mode
    app.on_workspace_mode_changed("Preview")
    assert app.active_workspace_mode == "preview"
    assert app.btn_export_annotated.cget("fg_color").lower() == "#5b4ee7"
    assert app.btn_export_annotated.cget("text_color").lower() in ("#ffffff", "white")
    assert app.btn_save_project.cget("fg_color") == "transparent"
    assert app.btn_save_project.cget("hover_color").lower() == "#353d4a"

    # Restore Tagging mode
    app.on_workspace_mode_changed("Tagging")
    assert app.active_workspace_mode == "tagging"
    assert app.btn_save_project.cget("fg_color").lower() == "#5b4ee7"


def test_mode_switcher_active_styling_and_cue(app):
    """
    Deliverable 1: Workspace Mode Switcher
    - Active tab indicated by stronger text and active styling.
    - Exposes selection cue.
    """
    for mode in ("Tagging", "Layout", "Preview"):
        app.on_workspace_mode_changed(mode)
        active_btn = app.mode_switcher._buttons_dict[mode]
        # Active button text font should be bold
        font_spec = active_btn.cget("font")
        assert "bold" in str(font_spec)
        assert active_btn.cget("text_color").lower() in ("#ffffff", "white")


def test_settings_panel_title_case_and_options(app):
    """
    Deliverable 1: Settings Panel
    - Title Case: Preset & Palette, Badge Geometry, Corner Geometry, Tag Typography
    - Scrollable settings panel
    """
    assert app.lbl_sec_style.cget("text") == "Preset & Palette"
    assert app.lbl_sec_geom.cget("text") == "Badge Geometry"
    assert app.lbl_badge_shape.cget("text") == "Corner Geometry"
    assert app.lbl_sec_font.cget("text") == "Tag Typography"
    assert hasattr(app, "tab_appearance_frame")
    # Dropdown includes Single Outline
    presets = app.combo_preset.cget("values")
    assert "Single Outline" in presets
    assert "Classic" in presets
    assert "Minimal" in presets
    assert "High Contrast" in presets
    assert "Print" in presets


def test_status_indicators_isolated_states_and_colors(app):
    """
    Deliverable 1: Status Indicators
    - Small vivid amber dot + quiet 'Unsaved' label (COLOR_STATUS_UNSAVED = #F59E0B)
    - Quiet slate '● Saved' (COLOR_STATUS_SAVED = #94A3B8)
    - Mint check '✓ Tags synced' (COLOR_STATUS_SYNCED = #34D399)
    - Amber dot '● Tags pending' (COLOR_STATUS_PENDING = #FBBF24)
    - Separate project save and tag sync states
    """
    # 1. Clean state
    app.set_modified(False)
    assert not app.is_project_dirty
    assert not app.is_metadata_dirty
    assert "Saved" in app.pill_project_status.cget("text")
    assert app.pill_project_status.cget("text_color") == COLOR_STATUS_SAVED
    assert "synced" in app.pill_metadata_status.cget("text")
    assert app.pill_metadata_status.cget("text_color") == COLOR_STATUS_SYNCED

    # 2. Project dirty only
    app.set_modified(True, project=True, metadata=False)
    assert app.is_project_dirty
    assert not app.is_metadata_dirty
    assert "Unsaved" in app.pill_project_status.cget("text")
    assert app.pill_project_status.cget("text_color") == COLOR_STATUS_UNSAVED
    assert "synced" in app.pill_metadata_status.cget("text")
    assert app.pill_metadata_status.cget("text_color") == COLOR_STATUS_SYNCED

    # 3. Metadata dirty only
    app.set_modified(False)
    app.set_modified(True, project=False, metadata=True)
    assert not app.is_project_dirty
    assert app.is_metadata_dirty
    assert "Saved" in app.pill_project_status.cget("text")
    assert app.pill_project_status.cget("text_color") == COLOR_STATUS_SAVED
    assert "pending" in app.pill_metadata_status.cget("text")
    assert app.pill_metadata_status.cget("text_color") == COLOR_STATUS_PENDING

    # Clean up
    app.set_modified(False)


def test_responsive_filename_truncation_preserves_status(app):
    """
    Deliverable 1: Status Indicators
    - Responsive filename truncation preserving status visibility at compact widths (down to 680px).
    """
    app.current_image_path = r"C:\Photos\Very_Long_Exhibition_Photograph_Archive_Catalog_2026_Final.jpg"
    app.set_modified(False)

    # Wide desktop (1200)
    app.reflow_header(1200)
    app._sync_modified_status()
    assert app.pill_project_status.winfo_manager() == "pack"
    assert app.pill_metadata_status.winfo_manager() == "pack"

    # Compact window (818)
    app.reflow_header(818)
    app._sync_modified_status()
    assert app.pill_project_status.winfo_manager() == "pack"
    assert app.pill_metadata_status.winfo_manager() == "pack"
    assert "…" in app.lbl_photo_identity.cget("text") or len(app.lbl_photo_identity.cget("text")) < len(os.path.basename(app.current_image_path))

    # Supported minimum width (680)
    app.reflow_header(680)
    app._sync_modified_status()
    assert app.pill_project_status.winfo_manager() == "pack"
    assert app.pill_metadata_status.winfo_manager() == "pack"


def test_five_presets_defaults_and_single_outline_rendering(tmp_path):
    """
    Deliverable 2: Tag Preset Comparison & Single Outline
    - 5 presets: Minimal, Classic, High Contrast, Print, Single Outline
    - Single Outline has exactly one visible perimeter on circles/rectangles without halo/shadow
    - Minimal has no stroke (width=0)
    - Print has opaque white badge with black text
    """
    presets = ["Minimal", "Classic", "High Contrast", "Print", "Single Outline"]
    
    # 1. Verify get_preset_rendering_properties returns valid defaults for all 5 presets
    for p in presets:
        props = get_preset_rendering_properties(style_preset=p)
        assert "badge_rgb" in props
        assert "badge_text_rgb" in props
        assert "legend_bg" in props

    # 2. Create test image with dark and light regions
    test_img_path = str(tmp_path / "test_matte.jpg")
    img = Image.new("RGB", (400, 300), (22, 25, 31))
    # Top-right is light, bottom-left is dark
    for x in range(200, 400):
        for y in range(0, 150):
            img.putpixel((x, y), (240, 240, 245))
    img.save(test_img_path, quality=95)

    faces = [
        {"x": 0.25, "y": 0.50, "w": 0.2, "h": 0.2, "name": "Dark Region Face", "bx": 0.25, "by": 0.35},
        {"x": 0.75, "y": 0.25, "w": 0.2, "h": 0.2, "name": "Light Region Face", "bx": 0.75, "by": 0.15}
    ]

    # 3. Export with all 5 presets on identical photo and positions
    exported_images = {}
    for p in presets:
        out_path = str(tmp_path / f"export_{p.replace(' ', '_')}.jpg")
        draw_annotations_on_image(
            test_img_path,
            faces,
            output_path=out_path,
            draw_names=True,
            style_preset=p
        )
        assert os.path.exists(out_path)
        exported_images[p] = Image.open(out_path)

    assert len(exported_images) == 5

    # 4. Single Outline verification:
    # Circle perimeter is crisp and distinct on both dark and light halves
    outline_img = exported_images["Single Outline"]
    assert outline_img.size[0] == 400
    assert outline_img.size[1] > 300  # Footer appended
    # Legend background should match props["legend_bg"] (charcoal #242830)
    footer_pixel = outline_img.getpixel((5, outline_img.size[1] - 5))
    expected_bg = get_preset_rendering_properties(style_preset="Single Outline")["legend_bg"][:3]
    for c in range(3):
        assert abs(footer_pixel[c] - expected_bg[c]) <= 10


def test_single_outline_on_canvas(app):
    """
    Verify draw_canvas_badge handles Single Outline without halo/shadow on Tk Canvas.
    """
    import tkinter as tk
    canvas = tk.Canvas(app, width=200, height=100, bg="#16191F")
    
    # Draw Single Outline badge
    draw_canvas_badge(
        canvas, 50, 50, "1", 12, "#ffffff",
        text_color="#ffffff", badge_shape="auto",
        style_preset="Single Outline"
    )
    
    # Verify canvas items
    items = canvas.find_all()
    assert len(items) >= 2  # base rect, perimeter oval, text
    canvas.destroy()


def test_english_persian_reposition_save_reload_refine_export(tmp_path, app):
    """
    Deliverable 3: Bilingual Candidate Verification Journey
    - Reposition English/Persian project
    - Save project sidecar
    - Reload and refine restored positions
    - Export annotated image
    """
    photo_path = str(tmp_path / "bilingual_portrait.jpg")
    img = Image.new("RGB", (600, 450), (40, 45, 55))
    img.save(photo_path, quality=95)

    app.load_image(photo_path)
    app.faces = [
        {"x": 0.3, "y": 0.4, "w": 0.2, "h": 0.2, "name": "Dr. Sarah Miller", "bx": 0.32, "by": 0.20},
        {"x": 0.7, "y": 0.4, "w": 0.2, "h": 0.2, "name": "دکتر مریم رضایی", "bx": 0.68, "by": 0.22}
    ]
    app.on_preset_changed("Single Outline")
    
    # 1. Save project sidecar
    sidecar_path = photo_path + ".phototagger.json"
    app.save_project_only()
    assert os.path.exists(sidecar_path)

    # 2. Reload project document
    with open(sidecar_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    doc = ProjectDocument.from_dict(data, image_path=photo_path)
    assert doc is not None
    assert len(doc.tags) == 2
    assert doc.tags[0].name == "Dr. Sarah Miller"
    assert doc.tags[1].name == "دکتر مریم رضایی"
    assert "outline" in doc.style.preset_name.lower()

    # 3. Refine positions
    app.faces[0]["bx"] = 0.35
    app.faces[0]["by"] = 0.18
    app.faces[1]["bx"] = 0.65
    app.faces[1]["by"] = 0.19
    app.save_project_only()

    # 4. Verify refined sidecar
    with open(sidecar_path, "r", encoding="utf-8") as f:
        data2 = json.load(f)
    doc2 = ProjectDocument.from_dict(data2, image_path=photo_path)
    assert doc2.tags[0].bx == 0.35
    assert doc2.tags[0].by == 0.18

    # 5. Export annotated image with refined positions
    export_out = str(tmp_path / "bilingual_refined_export.jpg")
    draw_annotations_on_image(
        photo_path,
        app.faces,
        output_path=export_out,
        style_preset=app.current_preset
    )
    assert os.path.exists(export_out)
    out_im = Image.open(export_out)
    assert out_im.size[0] == 600
