from pathlib import Path
import sys
import os
import shutil
import hashlib
from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import PT
from models import (
    ProjectDocument,
    FaceTag,
    TagStyle,
    SchemaError,
    CorruptProjectError,
    ProjectIdentityMismatchError,
    compute_content_fingerprint
)
from project_io import (
    save_project_document,
    load_project_document,
    has_draft,
    load_draft,
    discard_draft,
    get_project_sidecar_path,
    get_draft_path
)

FIXTURES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "fixtures"))

def get_file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

# ============================================================================
# R1: Close Handler Regression Tests
# ============================================================================

def test_close_handler_save_failure_blocks_destroy():
    """Verify R1: when save_current fails, destroy is NOT called and window remains."""
    app = SimpleNamespace(
        is_modified=True,
        current_image_path="photo.jpg",
        save_current=Mock(return_value=False),
        destroy=Mock()
    )
    with patch.object(PT.messagebox, "askyesnocancel", return_value=True):
        PT.PhotoTaggerApp.on_closing(app)
    assert not app.destroy.called
    assert app.is_modified is True

def test_close_handler_cancel_blocks_destroy():
    """Verify R1: when user selects Cancel, destroy is NOT called."""
    app = SimpleNamespace(
        is_modified=True,
        current_image_path="photo.jpg",
        save_current=Mock(),
        destroy=Mock()
    )
    with patch.object(PT.messagebox, "askyesnocancel", return_value=None):
        PT.PhotoTaggerApp.on_closing(app)
    assert not app.destroy.called
    assert not app.save_current.called

def test_close_handler_save_success_allows_destroy():
    """Verify R1: when save_current succeeds, destroy is called."""
    app = SimpleNamespace(
        is_modified=True,
        current_image_path="photo.jpg",
        save_current=Mock(return_value=True),
        destroy=Mock()
    )
    with patch.object(PT.messagebox, "askyesnocancel", return_value=True):
        PT.PhotoTaggerApp.on_closing(app)
    assert app.destroy.called

def test_close_handler_discard_allows_destroy_and_cleans_draft(tmp_path):
    """Verify R1: discard choice cleans draft and calls destroy."""
    photo_file = str(tmp_path / "discard_me.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "small_image.jpg"), photo_file)
    draft_file = get_draft_path(photo_file)
    with open(draft_file, "w") as f:
        f.write("{}")
    assert has_draft(photo_file)
    
    app = SimpleNamespace(
        is_modified=True,
        current_image_path=photo_file,
        save_current=Mock(),
        destroy=Mock()
    )
    with patch.object(PT.messagebox, "askyesnocancel", return_value=False):
        PT.PhotoTaggerApp.on_closing(app)
    assert app.destroy.called
    assert not has_draft(photo_file)

# ============================================================================
# R2: Navigation and Load Failure Safety
# ============================================================================

def test_load_failure_preserves_prior_state_and_path():
    """Verify R2: failed image load leaves prior photo path, faces, and desc intact."""
    app = SimpleNamespace(
        current_image_path="prior_photo.jpg",
        is_modified=False,
        faces=[{"name": "Prior Face", "x": 0.5, "y": 0.5, "w": 0.2, "h": 0.2, "id": "uuid-1"}],
        description="Prior Description",
        set_status=Mock()
    )
    with patch.object(PT.messagebox, "showerror"), patch("builtins.open", side_effect=IOError("Corrupt disk read")):
        result = PT.PhotoTaggerApp.load_image(app, "bad_image.jpg")
        
    assert result is False
    assert app.current_image_path == "prior_photo.jpg"
    assert len(app.faces) == 1
    assert app.faces[0]["name"] == "Prior Face"
    assert app.description == "Prior Description"

def test_open_file_cancel_preserves_navigation_list():
    """Verify R2: cancelled open does not overwrite image_list or index."""
    app = SimpleNamespace(
        image_list=["img1.jpg", "img2.jpg"],
        current_image_idx=0,
        current_image_path="img1.jpg",
        load_image=Mock(return_value=False)
    )
    with patch.object(PT.filedialog, "askopenfilename", return_value="new_img.jpg"), patch.object(PT.messagebox, "askyesnocancel", return_value=None):
        PT.PhotoTaggerApp.open_file(app)
        
    assert app.image_list == ["img1.jpg", "img2.jpg"]
    assert app.current_image_idx == 0

# ============================================================================
# R3: Corrupt & Future Sidecar Protection
# ============================================================================

def test_corrupt_sidecar_byte_for_byte_preservation(tmp_path):
    """Verify R3: corrupt JSON sidecar is preserved byte-for-byte and not overwritten."""
    photo_file = str(tmp_path / "corrupt_proj.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "small_image.jpg"), photo_file)
    sidecar_file = get_project_sidecar_path(photo_file)
    corrupt_bytes = b"{\n  \"schema_version\": 1,\n  INVALID JSON CONTENT\n"
    with open(sidecar_file, "wb") as f:
        f.write(corrupt_bytes)
        
    app = SimpleNamespace(
        current_image_path="previous.jpg",
        faces=[],
        description="",
        is_modified=False,
        set_status=Mock()
    )
    # User selects "Cancel" on corrupt dialog -> load aborted
    with patch.object(PT.messagebox, "askyesnocancel", return_value=None):
        result = PT.PhotoTaggerApp.load_image(app, photo_file)
        
    assert result is False
    # Verify sidecar bytes are 100% identical
    with open(sidecar_file, "rb") as f:
        assert f.read() == corrupt_bytes

def test_future_schema_blocks_sidecar_save(tmp_path):
    """Verify R3: unsupported future schema blocks saving over it."""
    photo_file = str(tmp_path / "future_proj.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "small_image.jpg"), photo_file)
    sidecar_file = get_project_sidecar_path(photo_file)
    with open(sidecar_file, "w") as f:
        f.write('{"schema_version": 999, "image": {"width": 64, "height": 64}, "tags": []}')
        
    app = SimpleNamespace(
        current_image_path=None,
        faces=[],
        description="",
        is_modified=False,
        blocked_sidecars=set(),
        set_status=Mock()
    )
    # User agrees to open read-only
    with patch.object(PT.messagebox, "askyesno", return_value=True):
        loaded = PT.PhotoTaggerApp.load_image(app, photo_file)
        
    assert loaded is True
    assert sidecar_file in app.blocked_sidecars
    
    # Routine save must be blocked!
    doc = ProjectDocument(image_path=photo_file, image_width=64, image_height=64)
    with pytest.raises(IOError) as exc_info:
        save_project_document(doc, blocked_sidecars=app.blocked_sidecars)
    assert "Cannot overwrite protected/corrupt sidecar" in str(exc_info.value)

# ============================================================================
# R4: Drafts on Empty Faces and Description Isolation
# ============================================================================

def test_draft_saved_on_zero_face_edit():
    """Verify R4: clearing all tags or deleting last face triggers draft write."""
    app = SimpleNamespace(
        current_image_path="test_zero.jpg",
        faces=[],
        title=Mock(),
        save_draft_state=Mock()
    )
    PT.PhotoTaggerApp.set_modified(app, True)
    assert app.save_draft_state.called

def test_draft_hydration_does_not_capture_old_photo_description(tmp_path):
    """Verify R4: restoring draft or loading photo does not write draft with prior photo's description."""
    photo1 = str(tmp_path / "photo1.jpg")
    photo2 = str(tmp_path / "photo2.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "small_image.jpg"), photo1)
    shutil.copyfile(os.path.join(FIXTURES_DIR, "small_image.jpg"), photo2)
    
    # Save a draft for photo2 with unique description
    doc2 = ProjectDocument(
        image_path=photo2,
        image_width=64,
        image_height=64,
        description="Photo 2 Authentic Description",
        tags=[FaceTag(name="Person 2", x=0.5, y=0.5, w=0.2, h=0.2)]
    )
    save_project_document(doc2, is_draft=True)
    assert has_draft(photo2)
    
    # Create app state currently holding photo1's description
    mock_textbox = Mock()
    mock_textbox.get.return_value = "Stale Photo 1 Description"
    app = SimpleNamespace(
        current_image_path=photo1,
        original_pil_image=None,
        faces=[],
        description="Stale Photo 1 Description",
        desc_textbox=mock_textbox,
        is_modified=False,
        set_status=Mock(),
        rebuild_sidebar=Mock(),
        draw_canvas=Mock(),
        update_navigation_controls=Mock(),
        title=Mock()
    )
    
    # User recovers draft for photo2
    with patch.object(PT.messagebox, "askyesno", return_value=True):
        loaded = PT.PhotoTaggerApp.load_image(app, photo2)
        
    assert loaded is True
    # The loaded description must be Photo 2 Authentic Description, NEVER stale photo 1!
    assert app.description == "Photo 2 Authentic Description"
    
    # Check that draft on disk also holds Photo 2 description
    reloaded_draft = load_draft(photo2)
    assert reloaded_draft.description == "Photo 2 Authentic Description"

# ============================================================================
# R5: Identity Mismatch & Conversion Collision Protection
# ============================================================================

def test_identity_mismatch_detection(tmp_path):
    """Verify R5: sidecar with mismatched dimensions warns user and can abort."""
    photo_file = str(tmp_path / "mismatch.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), photo_file) # 800x1000
    sidecar_file = get_project_sidecar_path(photo_file)
    
    # Create sidecar claiming dimensions 200x200
    doc = ProjectDocument(image_path=photo_file, image_width=200, image_height=200)
    save_project_document(doc)
    
    app = SimpleNamespace(
        current_image_path="prev.jpg",
        faces=[],
        description="",
        is_modified=False,
        set_status=Mock()
    )
    # User declines mismatch import
    with patch.object(PT.messagebox, "askyesno", return_value=False):
        loaded = PT.PhotoTaggerApp.load_image(app, photo_file)
        
    assert loaded is False
    assert app.current_image_path == "prev.jpg"

def test_conversion_target_collision_prompt(tmp_path):
    """Verify R5: converting format when target exists prompts overwrite."""
    src_file = str(tmp_path / "convert_src.jpg")
    dst_file = str(tmp_path / "convert_src.png")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "small_image.jpg"), src_file)
    shutil.copyfile(os.path.join(FIXTURES_DIR, "transparent_alpha.png"), dst_file)
    
    mock_fmt = Mock()
    mock_fmt.get.return_value = "PNG"
    
    app = SimpleNamespace(
        current_image_path=src_file,
        faces=[],
        description="",
        combo_format=mock_fmt,
        is_modified=True,
        set_status=Mock(),
        sort_faces=Mock()
    )
    # User says NO to overwriting existing dst_file
    with patch.object(PT.messagebox, "askyesno", return_value=False):
        saved = PT.PhotoTaggerApp.save_current(app)
        
    assert saved is False
    assert app.is_modified is True

# ============================================================================
# R6: Save Layout Never Touches Photo Pixels
# ============================================================================

def test_save_project_only_leaves_source_photo_hash_identical(tmp_path):
    """Verify R6: save_project_only writes sidecar but leaves image bytes 100% untouched."""
    from PIL import Image
    photo_file = str(tmp_path / "untouched_photo.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), photo_file)
    original_hash = get_file_sha256(photo_file)
    
    pil_img = Image.open(photo_file)
    app = SimpleNamespace(
        current_image_path=photo_file,
        original_pil_image=pil_img,
        faces=[{"name": "Moved Badge Subject", "x": 0.5, "y": 0.5, "w": 0.2, "h": 0.2, "bx": 0.9, "by": 0.1}],
        description="Layout test",
        combo_style_color=Mock(get=Mock(return_value="Teal")),
        combo_style_font_size=Mock(get=Mock(return_value="Auto (1.0x)")),
        is_modified=True,
        set_modified=Mock(),
        set_status=Mock()
    )
    
    result = PT.PhotoTaggerApp.save_project_only(app)
    assert result is True
    
    # 1. Sidecar exists and has the moved badge
    sidecar = load_project_document(photo_file)
    assert sidecar is not None
    assert sidecar.tags[0].bx == 0.9
    
    # 2. Source photo file SHA-256 hash must be 100% IDENTICAL (zero byte changes)
    after_hash = get_file_sha256(photo_file)
    assert after_hash == original_hash

# ============================================================================
# R7: Style Change in Layout Editor Sets Dirty
# ============================================================================

def test_editor_style_change_marks_parent_modified():
    """Verify R7: changing color or size in Output2bEditorWindow marks parent dirty."""
    parent = SimpleNamespace(
        combo_style_color=Mock(),
        combo_style_font_size=Mock(),
        set_modified=Mock()
    )
    editor = SimpleNamespace(
        parent=parent,
        render_editor_canvas=Mock()
    )
    PT.Output2bEditorWindow.on_editor_color_changed(editor, "Orange/Red")
    parent.combo_style_color.set.assert_called_with("Orange/Red")
    parent.set_modified.assert_called_with(True, project=True, metadata=False)
    assert editor.render_editor_canvas.called


# ============================================================================
# C1-C6 Corrections (Review Round 2)
# ============================================================================

def test_c1_save_current_blocked_sidecars_protects_canonical_file(tmp_path):
    """Verify C1: save_current refuses to overwrite blocked/read-only sidecars."""
    from PIL import Image
    photo = str(tmp_path / "photo.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), photo)
    sidecar = get_project_sidecar_path(photo)
    with open(sidecar, "w", encoding="utf-8") as f:
        f.write('{"protected": true}')
    orig_sidecar_bytes = open(sidecar, "rb").read()

    pil_img = Image.open(photo)
    app = SimpleNamespace(
        current_image_path=photo,
        original_pil_image=pil_img,
        faces=[{"name": "Test", "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}],
        description="test",
        blocked_sidecars={sidecar},
        combo_format=Mock(get=Mock(return_value="Original")),
        set_status=Mock(),
        sort_faces=Mock(),
        set_modified=Mock(),
        rebuild_sidebar=Mock(),
        draw_canvas=Mock(),
        update_navigation_controls=Mock()
    )

    with patch.object(PT.messagebox, "showerror"):
        saved = PT.PhotoTaggerApp.save_current(app)

    assert saved is False
    assert open(sidecar, "rb").read() == orig_sidecar_bytes


def test_c1_corrupt_sidecar_backup_failure_aborts_loading(tmp_path):
    """Verify C1: if backup_corrupt_sidecar fails, loading aborts and corrupt file remains intact."""
    photo = str(tmp_path / "photo.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), photo)
    sidecar = get_project_sidecar_path(photo)
    with open(sidecar, "w", encoding="utf-8") as f:
        f.write('INVALID JSON {{{{')
    orig_bytes = open(sidecar, "rb").read()

    app = SimpleNamespace(
        current_image_path=None,
        is_modified=False,
        set_status=Mock()
    )

    with patch.object(PT.messagebox, "askyesnocancel", return_value=True),          patch.object(PT, "backup_corrupt_sidecar", return_value=None),          patch.object(PT.messagebox, "showerror"):
        result = PT.PhotoTaggerApp.load_image(app, photo)

    assert result is False
    assert open(sidecar, "rb").read() == orig_bytes


def test_c2_failed_departure_preserves_dirty_and_recovery_draft(tmp_path):
    """Verify C2: unreadable incoming image does NOT discard old dirty state or recovery draft."""
    old_photo = str(tmp_path / "old.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), old_photo)
    draft_file = get_draft_path(old_photo)
    with open(draft_file, "w", encoding="utf-8") as f:
        f.write('{"draft": true}')

    app = SimpleNamespace(
        current_image_path=old_photo,
        is_modified=True,
        faces=[{"name": "KeepMe"}],
        description="Unsaved description",
        set_status=Mock(),
        set_modified=Mock()
    )

    bad_photo = str(tmp_path / "bad.jpg")
    with open(bad_photo, "wb") as f:
        f.write(b'NOT AN IMAGE')

    with patch.object(PT.messagebox, "askyesnocancel", return_value=False),          patch.object(PT.messagebox, "showerror"):
        result = PT.PhotoTaggerApp.load_image(app, bad_photo)

    assert result is False
    assert app.is_modified is True
    assert app.current_image_path == old_photo
    assert os.path.exists(draft_file)


def test_c3_fingerprint_rejects_different_image_with_same_dimensions(tmp_path):
    """Verify C3: same-size different image raises ProjectIdentityMismatchError."""
    from PIL import Image
    red_img = Image.new("RGB", (64, 64), color="red")
    blue_img = Image.new("RGB", (64, 64), color="blue")

    red_path = str(tmp_path / "red.jpg")
    blue_path = str(tmp_path / "blue.jpg")
    red_img.save(red_path)
    blue_img.save(blue_path)

    doc = ProjectDocument(image_path=red_path, image_width=64, image_height=64)
    doc.sync_from_app_state(faces_dicts=[], description="", color_theme="Teal", font_size_preset="Auto (1.0x)", pil_image=red_img)
    save_project_document(doc)

    # Validating red against red succeeds
    doc.validate_identity(actual_width=64, actual_height=64, actual_pil_img=red_img)

    # Validating red document against blue image fails on content fingerprint
    with pytest.raises(ProjectIdentityMismatchError) as exc_info:
        doc.validate_identity(actual_width=64, actual_height=64, actual_pil_img=blue_img)
    assert "Content fingerprint mismatch" in str(exc_info.value)


def test_c4_conversion_target_sidecar_collision_prompts_user(tmp_path):
    """Verify C4: conversion checks target sidecar collision even when target image does not exist."""
    from PIL import Image
    src_photo = str(tmp_path / "convert_me.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), src_photo)
    target_png = str(tmp_path / "convert_me.png")
    target_sidecar = get_project_sidecar_path(target_png)

    # Create target sidecar collision without target image
    assert not os.path.exists(target_png)
    with open(target_sidecar, "w", encoding="utf-8") as f:
        f.write('{"precious_sidecar": true}')
    orig_sidecar_bytes = open(target_sidecar, "rb").read()

    pil_img = Image.open(src_photo)
    app = SimpleNamespace(
        current_image_path=src_photo,
        original_pil_image=pil_img,
        faces=[],
        description="",
        combo_format=Mock(get=Mock(return_value="PNG")),
        set_status=Mock(),
        sort_faces=Mock(),
        set_modified=Mock(),
        rebuild_sidebar=Mock(),
        draw_canvas=Mock(),
        update_navigation_controls=Mock()
    )

    # User declines overwrite prompt
    with patch.object(PT.messagebox, "askyesno", return_value=False):
        saved = PT.PhotoTaggerApp.save_current(app)

    assert saved is False
    assert not os.path.exists(target_png)
    assert open(target_sidecar, "rb").read() == orig_sidecar_bytes


def test_c5_authoritative_doc_preserves_custom_fields_timestamps_and_orientation(tmp_path):
    """Verify C5: orientation, font_family, badge_shape, tag creation timestamps and extras are preserved."""
    from PIL import Image
    photo = str(tmp_path / "authoritative.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), photo)
    pil_img = Image.open(photo)

    tag = FaceTag("Original Tag", 0.2, 0.2, 0.3, 0.3, created_at="2021-05-01T12:00:00+00:00", extra={"tag_meta": 42})
    doc = ProjectDocument(
        image_path=photo,
        image_width=pil_img.size[0],
        image_height=pil_img.size[1],
        orientation=6,
        tags=[tag],
        description="Keep Doc",
        style=TagStyle(font_family="Comic Sans MS", badge_shape="round_rect"),
        created_at="2021-05-01T12:00:00+00:00",
        extra={"doc_meta": "keep"}
    )
    save_project_document(doc)

    app = SimpleNamespace(
        current_image_path=photo,
        original_pil_image=pil_img,
        current_doc=doc,
        faces=[t.to_dict() for t in doc.tags],
        description="Updated Description",
        combo_style_color=Mock(get=Mock(return_value="Teal")),
        combo_style_font_size=Mock(get=Mock(return_value="Auto (1.0x)")),
        combo_format=Mock(get=Mock(return_value="Original")),
        is_project_dirty=True,
        is_metadata_dirty=True,
        set_modified=Mock(),
        set_status=Mock(),
        sort_faces=Mock(),
        rebuild_sidebar=Mock(),
        draw_canvas=Mock(),
        update_navigation_controls=Mock()
    )

    # Save via save_project_only
    PT.PhotoTaggerApp.save_project_only(app)
    reloaded = load_project_document(photo)

    assert reloaded.orientation == 6
    assert reloaded.style.font_family == "Comic Sans MS"
    assert reloaded.created_at == "2021-05-01T12:00:00+00:00"
    assert reloaded.extra == {"doc_meta": "keep"}
    assert len(reloaded.tags) == 1
    assert reloaded.tags[0].created_at == "2021-05-01T12:00:00+00:00"
    assert reloaded.tags[0].extra == {"tag_meta": 42}


def test_c6_on_closing_unconditionally_uses_askyesnocancel():
    """Verify C6: on_closing calls askyesnocancel directly without test-mock inspection."""
    app = SimpleNamespace(
        is_modified=True,
        current_image_path="test.jpg",
        save_current=Mock(return_value=True),
        destroy=Mock()
    )
    with patch.object(PT.messagebox, "askyesnocancel", return_value=True) as mock_dialog:
        PT.PhotoTaggerApp.on_closing(app)
        assert mock_dialog.called


# ============================================================================
# D1-D3 Corrections (Review Round 3)
# ============================================================================

def test_d1_jpeg_save_and_reopen_identity_match(tmp_path):
    """Verify D1: JPEG save_current updates fingerprint to match re-encoded pixels on reopen."""
    from PIL import Image
    from types import MethodType
    path = tmp_path / "pixels.jpg"
    image = Image.new("RGB", (256, 256))
    image.putdata([((x * 17 + y * 13) % 256, (x * 31 + y * 7) % 256, (x * 3 + y * 29) % 256) for y in range(256) for x in range(256)])
    image.save(path, quality=80)

    with Image.open(path) as opened:
        source = opened.copy()

    doc = ProjectDocument(str(path), 256, 256, tags=[FaceTag("Name", 0.5, 0.5, 0.1, 0.1)])
    app = SimpleNamespace(
        current_image_path=str(path), original_pil_image=source, current_doc=doc,
        faces=[t.to_dict() for t in doc.tags], description=doc.description,
        is_modified=False, is_project_dirty=False, is_metadata_dirty=False,
        combo_format=Mock(get=Mock(return_value="Original")), title=Mock(), set_status=Mock(),
        sort_faces=Mock(), rebuild_sidebar=Mock(), draw_canvas=Mock(), update_navigation_controls=Mock(),
        image_list=[str(path)], current_image_idx=0
    )
    app.set_modified = MethodType(PT.PhotoTaggerApp.set_modified, app)
    app.save_draft_state = MethodType(PT.PhotoTaggerApp.save_draft_state, app)

    saved = PT.PhotoTaggerApp.save_current(app)
    assert saved is True

    # Reopen actual pixels and load canonical sidecar
    with Image.open(path) as reopened:
        reloaded_doc = load_project_document(str(path), expected_dimensions=(256, 256), actual_pil_img=reopened)
    assert reloaded_doc is not None
    assert reloaded_doc.content_fingerprint == compute_content_fingerprint(reopened)


def test_d1_alpha_sensitive_identity():
    """Verify D1: PNG transparency changes produce distinct fingerprints."""
    from PIL import Image
    # Same RGB content (solid red), but one is fully opaque and one has semi-transparent pixels
    opaque = Image.new("RGBA", (64, 64), (255, 0, 0, 255))
    semi_trans = Image.new("RGBA", (64, 64), (255, 0, 0, 128))

    fp_opaque = compute_content_fingerprint(opaque)
    fp_semi = compute_content_fingerprint(semi_trans)

    assert fp_opaque != ""
    assert fp_semi != ""
    assert fp_opaque != fp_semi


def test_d1_legacy_sidecar_migration(tmp_path):
    """Verify D1: sidecar without content_fingerprint loads cleanly and migrates fingerprint."""
    from PIL import Image
    photo = str(tmp_path / "legacy.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), photo)
    sidecar = get_project_sidecar_path(photo)

    pil_img = Image.open(photo)
    w, h = pil_img.size

    # Save sidecar with empty content_fingerprint (legacy format)
    legacy_doc = ProjectDocument(photo, w, h, content_fingerprint="", tags=[FaceTag("Legacy", 0.5, 0.5, 0.2, 0.2)])
    save_project_document(legacy_doc)

    # load_project_document must accept legacy sidecar and migrate fingerprint
    loaded = load_project_document(photo, expected_dimensions=(w, h), actual_pil_img=pil_img)
    assert loaded is not None
    assert loaded.content_fingerprint == compute_content_fingerprint(pil_img)


def test_d2_edit_and_split_dirty_state_lifecycle(tmp_path):
    """Verify D2: metadata edits set is_metadata_dirty; Save Project leaves is_modified True until metadata is saved."""
    from PIL import Image
    from types import MethodType
    photo = str(tmp_path / "lifecycle.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), photo)
    pil_img = Image.open(photo)

    doc = ProjectDocument(photo, pil_img.size[0], pil_img.size[1])
    app = SimpleNamespace(
        current_image_path=photo, original_pil_image=pil_img, current_doc=doc,
        faces=[], description="", is_modified=False, is_project_dirty=False, is_metadata_dirty=False,
        combo_format=Mock(get=Mock(return_value="Original")),
        combo_style_color=Mock(get=Mock(return_value="Teal")),
        combo_style_font_size=Mock(get=Mock(return_value="Auto (1.0x)")),
        title=Mock(), set_status=Mock(), sort_faces=Mock(), rebuild_sidebar=Mock(), draw_canvas=Mock(),
        update_navigation_controls=Mock(), image_list=[photo], current_image_idx=0
    )
    app.set_modified = MethodType(PT.PhotoTaggerApp.set_modified, app)
    app.save_draft_state = MethodType(PT.PhotoTaggerApp.save_draft_state, app)

    # 1. Edit description
    app.description = "New unsaved metadata"
    app.set_modified(True)

    assert app.is_metadata_dirty is True
    assert app.is_project_dirty is True
    assert app.is_modified is True

    # 2. Save project only
    PT.PhotoTaggerApp.save_project_only(app)
    assert app.is_project_dirty is False
    assert app.is_metadata_dirty is True
    assert app.is_modified is True  # App remains modified because embedded metadata is pending!

    # 3. Save current (embedded metadata)
    saved = PT.PhotoTaggerApp.save_current(app)
    assert saved is True
    assert app.is_project_dirty is False
    assert app.is_metadata_dirty is False
    assert app.is_modified is False


def test_d2_layout_only_edit_leaves_metadata_clean(tmp_path):
    """Verify D2: layout/style edit sets only is_project_dirty, and save_project_only cleans the app."""
    from PIL import Image
    from types import MethodType
    photo = str(tmp_path / "layout_only.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), photo)
    pil_img = Image.open(photo)

    doc = ProjectDocument(photo, pil_img.size[0], pil_img.size[1])
    app = SimpleNamespace(
        current_image_path=photo, original_pil_image=pil_img, current_doc=doc,
        faces=[], description="", is_modified=False, is_project_dirty=False, is_metadata_dirty=False,
        combo_format=Mock(get=Mock(return_value="Original")),
        combo_style_color=Mock(get=Mock(return_value="Teal")),
        combo_style_font_size=Mock(get=Mock(return_value="Auto (1.0x)")),
        title=Mock(), set_status=Mock(), sort_faces=Mock(), rebuild_sidebar=Mock(), draw_canvas=Mock(),
        update_navigation_controls=Mock(), image_list=[photo], current_image_idx=0
    )
    app.set_modified = MethodType(PT.PhotoTaggerApp.set_modified, app)
    app.save_draft_state = MethodType(PT.PhotoTaggerApp.save_draft_state, app)

    # Layout edit only
    app.set_modified(True, project=True, metadata=False)
    assert app.is_project_dirty is True
    assert app.is_metadata_dirty is False
    assert app.is_modified is True

    # Save project only
    saved = PT.PhotoTaggerApp.save_project_only(app)
    assert saved is True
    assert app.is_project_dirty is False
    assert app.is_metadata_dirty is False
    assert app.is_modified is False


def test_d3_failed_conversion_preserves_source_document_and_no_target_artifacts(tmp_path):
    """Verify D3: failed conversion does not mutate current_doc path or create orphan target sidecars."""
    from PIL import Image
    from types import MethodType
    src_png = str(tmp_path / "convert.png")
    image = Image.new("RGB", (64, 64), color="green")
    image.save(src_png)

    target_jpg = str(tmp_path / "convert.jpg")
    target_sidecar = get_project_sidecar_path(target_jpg)

    doc = ProjectDocument(src_png, 64, 64)
    app = SimpleNamespace(
        current_image_path=src_png, original_pil_image=image, current_doc=doc,
        faces=[], description="", is_modified=True, is_project_dirty=True, is_metadata_dirty=True,
        combo_format=Mock(get=Mock(return_value="JPEG")),
        title=Mock(), set_status=Mock(), sort_faces=Mock(), rebuild_sidebar=Mock(), draw_canvas=Mock(),
        update_navigation_controls=Mock(), image_list=[src_png], current_image_idx=0
    )
    app.set_modified = MethodType(PT.PhotoTaggerApp.set_modified, app)
    app.save_draft_state = MethodType(PT.PhotoTaggerApp.save_draft_state, app)

    # Simulate metadata writer failure during conversion
    with patch.object(PT, "write_photo_metadata", return_value=False), patch.object(PT.messagebox, "showerror"):
        saved = PT.PhotoTaggerApp.save_current(app)

    assert saved is False
    # Authoritative doc must still point to source PNG
    assert app.current_doc.image_path == src_png
    assert app.current_image_path == src_png
    # Target image and orphan sidecar must NOT exist
    assert not os.path.exists(target_jpg)
    assert not os.path.exists(target_sidecar)


def test_d3_successful_conversion_commits_state_and_updates_doc(tmp_path):
    """Verify D3: successful conversion updates current_doc and current_image_path cleanly."""
    from PIL import Image
    from types import MethodType
    src_jpg = str(tmp_path / "original.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), src_jpg)
    pil_img = Image.open(src_jpg)

    target_png = str(tmp_path / "original.png")
    target_sidecar = get_project_sidecar_path(target_png)

    doc = ProjectDocument(src_jpg, pil_img.size[0], pil_img.size[1])
    app = SimpleNamespace(
        current_image_path=src_jpg, original_pil_image=pil_img, current_doc=doc,
        faces=[], description="Converted photo", is_modified=True, is_project_dirty=True, is_metadata_dirty=True,
        combo_format=Mock(get=Mock(return_value="PNG")),
        title=Mock(), set_status=Mock(), sort_faces=Mock(), rebuild_sidebar=Mock(), draw_canvas=Mock(),
        update_navigation_controls=Mock(), image_list=[src_jpg], current_image_idx=0
    )
    app.set_modified = MethodType(PT.PhotoTaggerApp.set_modified, app)
    app.save_draft_state = MethodType(PT.PhotoTaggerApp.save_draft_state, app)

    with patch.object(PT.messagebox, "askyesno", return_value=False):  # Keep original file
        saved = PT.PhotoTaggerApp.save_current(app)

    assert saved is True
    assert app.current_image_path == target_png
    assert app.current_doc.image_path == target_png
    assert os.path.exists(target_png)
    assert os.path.exists(target_sidecar)
    assert os.path.exists(src_jpg)  # Kept original


# ============================================================================
# E1-E3 Corrections (Review Round 4)
# ============================================================================

def test_e1_failed_conversion_preserves_existing_destination_image_and_sidecar(tmp_path):
    """Verify E1: failed conversion restores existing destination image and sidecar byte-for-byte."""
    from PIL import Image
    from types import MethodType
    source = tmp_path / "source.png"
    target = tmp_path / "target.jpg"
    target_sidecar = Path(get_project_sidecar_path(str(target)))

    Image.new("RGB", (64, 64), "red").save(source)
    Image.new("RGB", (64, 64), "blue").save(target)
    orig_target_img_bytes = target.read_bytes()

    # Pre-existing destination sidecar
    with open(target_sidecar, "w", encoding="utf-8") as f:
        f.write('{"precious_existing_sidecar": true}')
    orig_target_sidecar_bytes = target_sidecar.read_bytes()

    app = SimpleNamespace(
        current_image_path=str(source), current_doc=ProjectDocument(str(source), 64, 64),
        original_pil_image=Image.new("RGB", (64, 64), "red"), faces=[], description="",
        combo_format=Mock(get=Mock(return_value="JPEG")), set_status=Mock(), sort_faces=Mock(),
        image_list=[str(source)], current_image_idx=0
    )
    app.set_modified = MethodType(PT.PhotoTaggerApp.set_modified, app)
    app.save_draft_state = MethodType(PT.PhotoTaggerApp.save_draft_state, app)

    # User approves overwrite, but project sidecar save fails
    with patch.object(PT.messagebox, "askyesno", return_value=True),          patch.object(PT, "save_project_document", side_effect=OSError("simulated disk/permission error")):
        saved = PT.PhotoTaggerApp.save_current(app)

    assert saved is False
    # Destination pair MUST be completely restored to exact original bytes
    assert target.exists()
    assert target.read_bytes() == orig_target_img_bytes
    assert target_sidecar.exists()
    assert target_sidecar.read_bytes() == orig_target_sidecar_bytes
    # Source path and current doc untouched
    assert app.current_image_path == str(source)
    assert app.current_doc.image_path == str(source)


def test_e1_failed_conversion_cleans_up_newly_created_target(tmp_path):
    """Verify E1: failed conversion when target did not exist cleans up any partial files."""
    from PIL import Image
    from types import MethodType
    source = tmp_path / "source.png"
    target = tmp_path / "target.jpg"
    target_sidecar = Path(get_project_sidecar_path(str(target)))

    Image.new("RGB", (64, 64), "red").save(source)
    assert not target.exists()
    assert not target_sidecar.exists()

    app = SimpleNamespace(
        current_image_path=str(source), current_doc=ProjectDocument(str(source), 64, 64),
        original_pil_image=Image.new("RGB", (64, 64), "red"), faces=[], description="",
        combo_format=Mock(get=Mock(return_value="JPEG")), set_status=Mock(), sort_faces=Mock(),
        image_list=[str(source)], current_image_idx=0
    )
    app.set_modified = MethodType(PT.PhotoTaggerApp.set_modified, app)
    app.save_draft_state = MethodType(PT.PhotoTaggerApp.save_draft_state, app)

    with patch.object(PT, "save_project_document", side_effect=OSError("sidecar write failure")):
        saved = PT.PhotoTaggerApp.save_current(app)

    assert saved is False
    assert not target.exists()
    assert not target_sidecar.exists()


def test_e2_style_change_accumulates_without_clearing_metadata_dirty():
    """Verify E2: main on_style_changed does NOT clear pre-existing pending metadata."""
    from types import MethodType
    app = SimpleNamespace(
        current_image_path="photo.jpg", title=Mock(), save_draft_state=Mock(),
        is_project_dirty=True, is_metadata_dirty=True, is_modified=True, draw_canvas=Mock()
    )
    app.set_modified = MethodType(PT.PhotoTaggerApp.set_modified, app)

    PT.PhotoTaggerApp.on_style_changed(app, "Purple")

    assert app.is_metadata_dirty is True
    assert app.is_project_dirty is True
    assert app.is_modified is True


def test_e2_editor_handlers_categorized_as_layout_only():
    """Verify E2: Output2bEditorWindow color, size, reset, and drag handlers only mark project dirty."""
    from types import MethodType
    parent = SimpleNamespace(
        current_image_path="photo.jpg", title=Mock(), save_draft_state=Mock(),
        is_project_dirty=False, is_metadata_dirty=False, is_modified=False,
        combo_style_color=Mock(), combo_style_font_size=Mock(),
        faces=[{"name": "Face 1", "x": 0.2, "y": 0.2, "w": 0.2, "h": 0.2, "bx": None, "by": None}]
    )
    parent.set_modified = MethodType(PT.PhotoTaggerApp.set_modified, parent)
    editor = SimpleNamespace(parent=parent, render_editor_canvas=Mock())

    # 1. Color change
    PT.Output2bEditorWindow.on_editor_color_changed(editor, "Orange/Red")
    assert parent.is_project_dirty is True
    assert parent.is_metadata_dirty is False
    assert parent.is_modified is True

    # Reset clean
    parent.set_modified(False)
    assert parent.is_modified is False

    # 2. Size change
    PT.Output2bEditorWindow.on_editor_size_changed(editor, "Large (1.25x)")
    assert parent.is_project_dirty is True
    assert parent.is_metadata_dirty is False

    # Reset clean
    parent.set_modified(False)

    # 3. Reset positions
    PT.Output2bEditorWindow.reset_positions(editor)
    assert parent.is_project_dirty is True
    assert parent.is_metadata_dirty is False


def test_e3_draft_recovery_restores_discrete_dirty_categories(tmp_path):
    """Verify E3: load_image accurately restores discrete dirty flags from draft and strips recovery markers on clean save."""
    from PIL import Image
    photo = str(tmp_path / "recovery_test.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), photo)
    pil_img = Image.open(photo)

    # Save a draft that has ONLY layout dirty (e.g. badge moved)
    draft_doc = ProjectDocument(photo, pil_img.size[0], pil_img.size[1])
    draft_doc.extra = {"_recovery_state": {"is_project_dirty": True, "is_metadata_dirty": False}}
    save_project_document(draft_doc, is_draft=True)
    assert has_draft(photo)

    app = SimpleNamespace(
        current_image_path=None, is_modified=False, set_status=Mock(),
        combo_style_color=Mock(), combo_style_font_size=Mock(), combo_format=Mock(),
        title=Mock(), rebuild_sidebar=Mock(), draw_canvas=Mock(), update_navigation_controls=Mock()
    )
    # User recovers the draft
    with patch.object(PT.messagebox, "askyesno", return_value=True):
        loaded = PT.PhotoTaggerApp.load_image(app, photo)

    assert loaded is True
    # Restored EXACT category state!
    assert app.is_project_dirty is True
    assert app.is_metadata_dirty is False
    assert app.is_modified is True

    # Now save canonical project document: clean save must strip _recovery_state from payload
    save_project_document(app.current_doc, is_draft=False)
    canonical = load_project_document(photo)
    assert canonical is not None
    assert "_recovery_state" not in canonical.extra
    assert "_dirty_project" not in canonical.extra
    assert "_dirty_metadata" not in canonical.extra


# ============================================================================
# Review 6: Safe Overwrite Restriction Verification Matrix
# ============================================================================

def test_r6_conversion_blocked_when_target_image_exists(tmp_path):
    """Verify Review 6: conversion is strictly blocked when destination image exists, leaving files byte-identical."""
    from PIL import Image
    from types import MethodType
    source = tmp_path / "photo.png"
    target = source.with_suffix(".jpg")
    Image.new("RGB", (64, 64), "red").save(source)
    Image.new("RGB", (64, 64), "blue").save(target)
    orig_target_bytes = target.read_bytes()

    app = SimpleNamespace(
        current_image_path=str(source), current_doc=ProjectDocument(str(source), 64, 64),
        original_pil_image=Image.new("RGB", (64, 64), "red"), faces=[], description="",
        combo_format=Mock(get=Mock(return_value="JPEG")), set_status=Mock(), sort_faces=Mock(),
        image_list=[str(source)], current_image_idx=0
    )
    app.set_modified = MethodType(PT.PhotoTaggerApp.set_modified, app)
    app.save_draft_state = MethodType(PT.PhotoTaggerApp.save_draft_state, app)

    with patch.object(PT, "write_photo_metadata") as mock_writer, \
         patch.object(PT, "save_project_document") as mock_saver:
        saved = PT.PhotoTaggerApp.save_current(app)

    assert saved is False
    # Neither writer is called
    assert not mock_writer.called
    assert not mock_saver.called
    # Original destination file MUST be completely untouched
    assert target.exists()
    assert target.read_bytes() == orig_target_bytes
    assert "Conversion blocked: destination already exists" in app.set_status.call_args[0][0]


def test_r6_conversion_blocked_when_target_sidecar_exists(tmp_path):
    """Verify Review 6: conversion is strictly blocked when destination sidecar exists, leaving files byte-identical."""
    from PIL import Image
    from types import MethodType
    source = tmp_path / "photo.png"
    target = source.with_suffix(".jpg")
    target_sidecar = Path(get_project_sidecar_path(str(target)))
    Image.new("RGB", (64, 64), "red").save(source)
    assert not target.exists()
    with open(target_sidecar, "w", encoding="utf-8") as f:
        f.write('{"precious_sidecar": true}')
    orig_sidecar_bytes = target_sidecar.read_bytes()

    app = SimpleNamespace(
        current_image_path=str(source), current_doc=ProjectDocument(str(source), 64, 64),
        original_pil_image=Image.new("RGB", (64, 64), "red"), faces=[], description="",
        combo_format=Mock(get=Mock(return_value="JPEG")), set_status=Mock(), sort_faces=Mock(),
        image_list=[str(source)], current_image_idx=0
    )
    app.set_modified = MethodType(PT.PhotoTaggerApp.set_modified, app)
    app.save_draft_state = MethodType(PT.PhotoTaggerApp.save_draft_state, app)

    with patch.object(PT, "write_photo_metadata") as mock_writer, \
         patch.object(PT, "save_project_document") as mock_saver:
        saved = PT.PhotoTaggerApp.save_current(app)

    assert saved is False
    assert not mock_writer.called
    assert not mock_saver.called
    assert not target.exists()
    assert target_sidecar.exists()
    assert target_sidecar.read_bytes() == orig_sidecar_bytes
    assert "Conversion blocked: destination already exists" in app.set_status.call_args[0][0]


def test_r6_conversion_succeeds_when_destination_absent(tmp_path):
    """Verify Review 6: conversion succeeds cleanly when destination files do not exist."""
    from PIL import Image
    from types import MethodType
    source = tmp_path / "original.jpg"
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), source)
    target = source.with_suffix(".png")
    target_sidecar = Path(get_project_sidecar_path(str(target)))
    assert not target.exists()
    assert not target_sidecar.exists()

    pil_img = Image.open(source)
    doc = ProjectDocument(str(source), pil_img.size[0], pil_img.size[1])
    app = SimpleNamespace(
        current_image_path=str(source), original_pil_image=pil_img, current_doc=doc,
        faces=[], description="Converted", combo_format=Mock(get=Mock(return_value="PNG")),
        set_status=Mock(), sort_faces=Mock(), rebuild_sidebar=Mock(), draw_canvas=Mock(),
        update_navigation_controls=Mock(), image_list=[str(source)], current_image_idx=0
    )
    app.set_modified = MethodType(PT.PhotoTaggerApp.set_modified, app)
    app.save_draft_state = MethodType(PT.PhotoTaggerApp.save_draft_state, app)

    with patch.object(PT.messagebox, "askyesno", return_value=False):
        saved = PT.PhotoTaggerApp.save_current(app)

    assert saved is True
    assert target.exists()
    assert target_sidecar.exists()
    assert app.current_image_path == str(target)
