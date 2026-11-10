import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import io
import json
import pytest
from unittest.mock import patch, MagicMock
from PIL import Image

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
    draw_canvas_badge,
    hex_to_rgb,
    get_hex_luminance,
    get_contrasting_hex
)
from metadata import (
    get_preset_rendering_properties,
    draw_annotations_on_image,
    get_luminance,
    get_contrasting_colors,
    PRESETS
)
from models import (
    ProjectDocument,
    TagStyle,
    FaceTag
)
from project_io import get_project_sidecar_path


@pytest.fixture(scope="module")
def app_instance():
    """Create an off-screen app instance for GUI introspection tests."""
    app = PhotoTaggerApp()
    app.withdraw()
    app.update_idletasks()
    yield app
    try:
        app.destroy()
    except Exception:
        pass


@pytest.fixture
def sample_test_image(tmp_path):
    """Generates a simple 400x300 RGB test image."""
    img_path = str(tmp_path / "sample_test.jpg")
    img = Image.new("RGB", (400, 300), color=(120, 150, 180))
    img.save(img_path, quality=95)
    return img_path


# ==============================================================================
# SECTION 1: Control Groups, Surfaces, and Action Hierarchy
# ==============================================================================

def test_control_groups_surfaces_and_equal_widths(app_instance):
    """Verify all 5 control groups have matching surface backgrounds and equal button widths."""
    app = app_instance

    # Group 1: Workspace Tabs (mode_switcher)
    assert app.mode_switcher.cget("fg_color") == COLOR_WORKSPACE
    assert app.mode_switcher.cget("unselected_color") == COLOR_WORKSPACE
    assert app.mode_switcher.cget("selected_color") == COLOR_WORKSPACE
    # Verify grid uniform configure
    grid_info_0 = app.mode_switcher.grid_columnconfigure(0)
    grid_info_1 = app.mode_switcher.grid_columnconfigure(1)
    assert grid_info_0.get("uniform") == "mode_tabs"
    assert grid_info_1.get("uniform") == "mode_tabs"
    assert grid_info_0.get("weight") == 1
    assert grid_info_1.get("weight") == 1

    # Group 2: Tools (tool_switcher)
    assert app.tool_switcher.cget("fg_color") == COLOR_WORKSPACE
    assert app.tool_switcher.cget("unselected_color") == COLOR_WORKSPACE
    assert app.tool_switcher.cget("selected_color") == "#353D4A"
    for i in range(2):
        col_info = app.tool_switcher.grid_columnconfigure(i)
        assert col_info.get("uniform") == "tool_tabs"
        assert col_info.get("weight") == 1

    # Group 3: Inspector Tabs (inspector_tab_segmented)
    assert app.inspector_tab_segmented.cget("fg_color") == COLOR_SETTINGS_SURFACE
    assert app.inspector_tab_segmented.cget("unselected_color") == COLOR_SETTINGS_SURFACE
    assert app.inspector_tab_segmented.cget("selected_color") == COLOR_SETTINGS_SURFACE
    for i in range(3):
        col_info = app.inspector_tab_segmented.grid_columnconfigure(i)
        assert col_info.get("uniform") == "inspector_tabs"
        assert col_info.get("weight") == 1

    # Group 4: Badge Shapes (seg_badge_shape)
    assert app.seg_badge_shape.cget("fg_color") == COLOR_SETTINGS_SURFACE
    assert app.seg_badge_shape.cget("unselected_color") == COLOR_SETTINGS_SURFACE
    assert app.seg_badge_shape.cget("selected_color") == "#353D4A"
    for i in range(3):
        col_info = app.seg_badge_shape.grid_columnconfigure(i)
        assert col_info.get("uniform") == "shape_tabs"
        assert col_info.get("weight") == 1

    # Group 5: Tag Fonts (seg_tag_font)
    assert app.seg_tag_font.cget("fg_color") == COLOR_SETTINGS_SURFACE
    assert app.seg_tag_font.cget("unselected_color") == COLOR_SETTINGS_SURFACE
    assert app.seg_tag_font.cget("selected_color") == "#353D4A"
    for i in range(3):
        col_info = app.seg_tag_font.grid_columnconfigure(i)
        assert col_info.get("uniform") == "font_tabs"
        assert col_info.get("weight") == 1


def test_secondary_buttons_idle_outlines(app_instance):
    """Verify secondary toolbar buttons have no idle borders (border_width=0)."""
    app = app_instance
    secondary_buttons = [
        app.btn_open_file,
        app.btn_open_folder,
        app.btn_export_annotated,
        app.btn_write_tags,
        app.btn_overflow,
        app.btn_help,
        app.btn_undo,
        app.btn_redo,
    ]
    for btn in secondary_buttons:
        assert btn.cget("border_width") == 0, f"Button {btn} has non-zero border_width: {btn.cget('border_width')}"


def test_action_hierarchy_primary_buttons(app_instance):
    """Verify single solid primary action rule across editing and preview modes."""
    app = app_instance

    # In Tagging mode
    app.on_workspace_mode_changed("Tagging")
    app.update_idletasks()
    assert app.btn_save_project.cget("fg_color") == COLOR_ACCENT_PRIMARY  # Indigo #5b4ee7
    assert app.btn_export_annotated.cget("fg_color") == "transparent"

    # In Preview mode
    app.on_workspace_mode_changed("Preview")
    app.update_idletasks()
    assert app.btn_export_annotated.cget("fg_color") == COLOR_ACCENT_EXPORT  # Green #16a34a
    assert app.btn_save_project.cget("fg_color") == "transparent"

    # Switch back to Tagging mode for subsequent tests
    app.on_workspace_mode_changed("Tagging")
    app.update_idletasks()


# ==============================================================================
# SECTION 2: Rotate Left/Right Windows-Style Icons & Behavior
# ==============================================================================

def test_rotate_icons_exist_and_distinct(app_instance):
    """Verify rotate left and right icons exist, are 16x16, and distinct from undo/redo."""
    app = app_instance
    assert hasattr(app, "icon_rotate_left")
    assert hasattr(app, "icon_rotate_right")
    assert hasattr(app, "btn_rotate_left")
    assert hasattr(app, "btn_rotate_right")

    assert app.btn_rotate_left.cget("border_width") == 0
    assert app.btn_rotate_right.cget("border_width") == 0

    assert app.icon_rotate_left._size == (22, 22)
    assert app.icon_rotate_right._size == (22, 22)

    icons_dir = os.path.join(os.path.dirname(__file__), "..", "assets", "icons")
    rot_left_path = os.path.join(icons_dir, "rotate_left.png")
    rot_right_path = os.path.join(icons_dir, "rotate_right.png")
    undo_path = os.path.join(icons_dir, "undo.png")

    assert os.path.exists(rot_left_path)
    assert os.path.exists(rot_right_path)

    # Check distinct images
    with Image.open(rot_left_path) as l_img, Image.open(rot_right_path) as r_img, Image.open(undo_path) as u_img:
        assert l_img.size == (64, 64)
        assert r_img.size == (64, 64)
        assert l_img.tobytes() != u_img.tobytes()
        assert l_img.tobytes() != r_img.tobytes()


def test_rotation_transformations_and_persistence(app_instance, sample_test_image, tmp_path):
    """Verify 90° CW and CCW rotation transforms image, tags, persists to sidecar, and reloads."""
    app = app_instance
    app.set_modified(False)

    # Open image
    app.load_image(sample_test_image)
    orig_w, orig_h = app.original_pil_image.size
    assert (orig_w, orig_h) == (400, 300)

    # Add a face tag with known normalized coordinates
    test_tag = {
        "id": "test_tag_1",
        "name": "Alice",
        "x": 0.2,
        "y": 0.3,
        "w": 0.1,
        "h": 0.1,
        "bx": 0.2,
        "by": 0.35
    }
    app.faces = [test_tag]

    # Rotate 90° Clockwise (Right)
    app.rotate_photo("right")
    assert app.original_pil_image.size == (300, 400)
    assert getattr(app, '_image_rotated', False) is True
    assert getattr(app, '_image_rotation_angle', 0) == 90

    # Test coordinate transformation for 90° CW:
    # new_x = 1.0 - y = 1.0 - 0.3 = 0.7
    # new_y = x = 0.2
    # new_w = h = 0.1, new_h = w = 0.1
    rotated_tag = app.faces[0]
    assert pytest.approx(rotated_tag["x"], abs=1e-4) == 0.7
    assert pytest.approx(rotated_tag["y"], abs=1e-4) == 0.2
    assert pytest.approx(rotated_tag["w"], abs=1e-4) == 0.1
    assert pytest.approx(rotated_tag["h"], abs=1e-4) == 0.1

    # Save project to sidecar
    app.save_project_only()
    sidecar_path = get_project_sidecar_path(sample_test_image)
    assert os.path.exists(sidecar_path)

    with open(sidecar_path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    assert doc.get("extra", {}).get("rotation") == 90

    # Clear app and reload image: should restore rotation and transformed tags
    app.original_pil_image = None
    app.faces = []
    app.set_modified(False)
    app.load_image(sample_test_image)

    assert app.original_pil_image.size == (300, 400)
    assert getattr(app, '_image_rotated', False) is True
    assert getattr(app, '_image_rotation_angle', 0) == 90
    assert len(app.faces) == 1
    reloaded_tag = app.faces[0]
    assert pytest.approx(reloaded_tag["x"], abs=1e-4) == 0.7
    assert pytest.approx(reloaded_tag["y"], abs=1e-4) == 0.2

    # Rotate 90° Counter-Clockwise (Left) -> back to 0°
    app.rotate_photo("left")
    assert app.original_pil_image.size == (400, 300)
    assert getattr(app, '_image_rotation_angle', 0) == 0
    back_tag = app.faces[0]
    assert pytest.approx(back_tag["x"], abs=1e-4) == 0.2
    assert pytest.approx(back_tag["y"], abs=1e-4) == 0.3
    app.set_modified(False)


def test_export_with_rotation(app_instance, sample_test_image, tmp_path):
    """Verify annotated exports honour rotated image orientation."""
    app = app_instance
    app.set_modified(False)
    app.load_image(sample_test_image)
    app.faces = [{"id": "t1", "name": "Persian Test فرهاد", "x": 0.5, "y": 0.5, "w": 0.1, "h": 0.1}]
    app.rotate_photo("right")

    out_numbered = str(tmp_path / "rot_numbered.jpg")
    out_tagged = str(tmp_path / "rot_tagged.jpg")

    export_source = app.original_pil_image
    success_num = draw_annotations_on_image(export_source, app.faces, out_numbered, draw_names=False)
    success_tag = draw_annotations_on_image(export_source, app.faces, out_tagged, draw_names=True)

    assert success_num is True
    assert success_tag is True

    with Image.open(out_numbered) as img_num:
        assert img_num.size == (300, 400)
    with Image.open(out_tagged) as img_tag:
        assert img_tag.size[0] == 300
        assert img_tag.size[1] >= 400  # Includes rendered footer legend
    app.set_modified(False)


# ==============================================================================
# SECTION 3: Tag Color Accent Across EVERY Preset & Mathematical Contrast
# ==============================================================================

def test_tag_color_accent_across_every_preset():
    """Verify that every preset changes its badge fill when a Tag Color Accent is selected."""
    swatches = [
        {"name": "Sky Blue", "hex": "#0ea5e9", "rgb": (14, 165, 233)},
        {"name": "Emerald", "hex": "#10b981", "rgb": (16, 185, 129)},
        {"name": "Amber", "hex": "#f59e0b", "rgb": (245, 158, 11)},
        {"name": "Violet", "hex": "#8b5cf6", "rgb": (139, 92, 246)},
        {"name": "White", "hex": "#ffffff", "rgb": (255, 255, 255)},
        {"name": "Dark Charcoal", "hex": "#1e293b", "rgb": (30, 41, 59)},
    ]

    for preset_name in ["Single Outline", "Borderless", "Classic", "Minimal", "High Contrast", "Print"]:
        for swatch in swatches:
            props = get_preset_rendering_properties(style_preset=preset_name, color_style=swatch)
            assert props["badge_rgb"] == swatch["rgb"], (
                f"Preset '{preset_name}' with swatch '{swatch['name']}' did not reflect badge fill! "
                f"Got {props['badge_rgb']}, expected {swatch['rgb']}"
            )


def test_mathematical_contrast_calculation():
    """Verify luminance and contrasting text / keyline calculation."""
    # Pure white background -> luminance > 0.5 -> dark text and keyline
    white_lum = get_luminance((255, 255, 255))
    assert white_lum > 0.9
    white_text, white_keyline = get_contrasting_colors((255, 255, 255))
    assert white_text == (15, 23, 42, 255)
    assert white_keyline == (0, 0, 0, 255)

    # Pure black background -> luminance < 0.5 -> white text and keyline
    black_lum = get_luminance((0, 0, 0))
    assert black_lum < 0.1
    black_text, black_keyline = get_contrasting_colors((0, 0, 0))
    assert black_text == (255, 255, 255, 255)
    assert black_keyline == (255, 255, 255, 255)

    # Yellow background (245, 158, 11) -> high luminance -> dark text
    yellow_text, _ = get_contrasting_colors((245, 158, 11))
    assert yellow_text == (15, 23, 42, 255)

    # Dark blue background (37, 99, 235) -> low luminance -> white text
    blue_text, _ = get_contrasting_colors((37, 99, 235))
    assert blue_text == (255, 255, 255, 255)


def test_single_outline_exactly_one_perimeter_no_halo():
    """Verify Single Outline preset produces exactly 1 contrasting perimeter without halo or shadow."""
    for fill_rgb in [(14, 165, 233), (255, 255, 255), (30, 41, 59)]:
        props = get_preset_rendering_properties(style_preset="Single Outline", color_style={"rgb": fill_rgb, "hex": "#test"})
        assert props["stroke_width"] == 1
        assert props["shadow_width"] == 0
        assert props["shadow_rgb"] is None
        assert props["halo_rgb"] is None

        # Keyline must mathematically contrast with fill
        lum = get_luminance(fill_rgb)
        if lum > 0.5:
            assert props["keyline_rgb"] == (0, 0, 0)
        else:
            assert props["keyline_rgb"] == (255, 255, 255)


def test_minimal_and_borderless_stroke_widths():
    """Verify Minimal and Borderless have zero stroke width (no perimeter outline)."""
    min_props = get_preset_rendering_properties(style_preset="Minimal")
    assert min_props["stroke_width"] == 0
    assert min_props["shadow_width"] == 0

    borderless_props = get_preset_rendering_properties(style_preset="Borderless")
    assert borderless_props["stroke_width"] == 0
    assert borderless_props["shadow_width"] == 0


def test_print_preset_characteristics():
    """Verify Print preset renders square shape and responds to accent color."""
    default_props = get_preset_rendering_properties(style_preset="Print", color_style=None)
    assert default_props["badge_rgb"] == (255, 255, 255)
    assert default_props["badge_text_rgb"] == (0, 0, 0, 255)
    assert default_props["shape"] == "square"

    accent_props = get_preset_rendering_properties(style_preset="Print", color_style={"rgb": (16, 185, 129), "hex": "#10b981"})
    assert accent_props["badge_rgb"] == (16, 185, 129)
    assert accent_props["shape"] == "square"


# ==============================================================================
# SECTION 4: Minimal vs. Borderless Presets
# ==============================================================================

def test_preset_definitions_and_backward_compatibility():
    """Verify both Minimal and Borderless exist in PRESETS and preset dropdown."""
    assert "Minimal" in PRESETS
    assert "Borderless" in PRESETS
    assert "Single Outline" in PRESETS
    assert "Classic" in PRESETS
    assert "High Contrast" in PRESETS
    assert "Print" in PRESETS

    # Backward compatibility: arbitrary legacy string falls back cleanly to Classic
    fallback_props = get_preset_rendering_properties(style_preset="LegacyNonExistentPreset")
    assert fallback_props["name"] == "Classic"


# ==============================================================================
# SECTION 5: Google Drive & Open Photo Robustness
# ==============================================================================

def test_open_photo_local_success(app_instance, sample_test_image):
    """Verify opening a standard local photo loads cleanly."""
    app = app_instance
    app.set_modified(False)
    app.load_image(sample_test_image)
    assert app.current_image_path == sample_test_image
    assert app.original_pil_image is not None
    app.set_modified(False)


def test_open_photo_google_drive_path(app_instance, tmp_path):
    """Verify opening a path structured like Google Drive (G:\\My Drive\\...) is supported."""
    app = app_instance
    app.set_modified(False)
    fake_drive_path = "G:\\My Drive\\Photos\\test_drive.jpg"

    buf = io.BytesIO()
    test_img = Image.new("RGB", (200, 200), color=(100, 100, 100))
    test_img.save(buf, format="JPEG")
    img_bytes = buf.getvalue()

    def fake_exists(p):
        return p == fake_drive_path

    from unittest.mock import mock_open
    m = mock_open(read_data=img_bytes)
    with patch("builtins.open", m):
        with patch("os.path.exists", side_effect=fake_exists):
            with patch("os.path.getsize", return_value=len(img_bytes)):
                with patch("metadata.read_photo_metadata", return_value=([], None, "Teal", "Auto (1.0x)")):
                    app.load_image(fake_drive_path)
                    assert app.current_image_path == fake_drive_path
                    assert app.original_pil_image is not None
    app.set_modified(False)


def test_open_photo_cloud_hydration_error_resilience(app_instance, sample_test_image):
    """Verify handling of Windows error 1920 / ERROR_CANT_ACCESS_FILE keeps open image intact."""
    app = app_instance
    app.set_modified(False)
    # First load a valid image
    app.load_image(sample_test_image)
    app.faces = [{"id": "preserve_1", "name": "Preserved Person", "x": 0.5, "y": 0.5, "w": 0.2, "h": 0.2}]
    original_faces = list(app.faces)
    original_path = app.current_image_path

    # Simulate opening a cloud-only file that throws WinError 1920
    failing_path = "G:\\My Drive\\Photos\\offline_stub.jpg"
    win_error = OSError(1920, "The file cannot be accessed by the system (ERROR_CANT_ACCESS_FILE)", failing_path, 1920)

    with patch("PIL.Image.open", side_effect=win_error):
        with patch("tkinter.messagebox.showerror") as mock_err:
            app.load_image(failing_path)
            # Verify error dialog was shown with actionable cloud guidance
            assert mock_err.called
            err_title, err_msg = mock_err.call_args[0]
            assert "Cloud" in err_title or "Error" in err_title
            assert "Make available offline" in err_msg or "offline" in err_msg

    # Verify existing loaded photo and edits were preserved
    assert app.current_image_path == original_path
    assert app.original_pil_image is not None
    assert app.faces == original_faces
    app.set_modified(False)


def test_open_photo_cancellation_preserves_state(app_instance, sample_test_image):
    """Verify user cancelling file dialog (empty string) preserves existing photo and edits."""
    app = app_instance
    app.set_modified(False)
    app.load_image(sample_test_image)
    app.faces = [{"id": "edit_1", "name": "Work In Progress", "x": 0.4, "y": 0.4, "w": 0.1, "h": 0.1}]
    orig_faces = list(app.faces)
    orig_path = app.current_image_path

    with patch("tkinter.filedialog.askopenfilename", return_value=""):
        app.open_file()

    assert app.current_image_path == orig_path
    assert app.faces == orig_faces
    app.set_modified(False)
