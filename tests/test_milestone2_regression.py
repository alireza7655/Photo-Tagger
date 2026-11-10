import sys
import os
import shutil
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from models import ProjectDocument, FaceTag, TagStyle
from project_io import (
    save_project_document,
    load_project_document,
    get_project_sidecar_path,
    has_draft,
    load_draft,
    discard_draft
)
from metadata import write_photo_metadata, read_photo_metadata

FIXTURES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "fixtures"))

def test_full_app_restart_layout_and_style_persistence(tmp_path):
    """
    Required Regression:
    Move badge, change style, save, close app entirely, reopen photo/project.
    Positions and style must match 100%.
    """
    photo_path = str(tmp_path / "restart_test.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), photo_path)
    
    # 1. Simulate Session 1: User adds face, drags badge, selects custom style
    style1 = TagStyle(color_theme="Purple", font_size_preset="Large (1.5x)")
    tag1 = FaceTag(
        name="Elena Rostova",
        x=0.5,
        y=0.35,
        w=0.2,
        h=0.2,
        bx=0.88,
        by=0.12
    )
    doc1 = ProjectDocument(
        image_path=photo_path,
        image_width=800,
        image_height=1000,
        tags=[tag1],
        description="Portrait session with custom badge",
        style=style1
    )
    
    # User saves
    saved_doc = save_project_document(doc1)
    saved_meta = write_photo_metadata(photo_path, [tag1.to_dict()], doc1.description)
    assert saved_doc is True
    assert saved_meta is True
    
    # 2. Simulate complete application exit: delete all session 1 objects from memory
    del doc1, style1, tag1
    
    # 3. Simulate Session 2: User opens app and loads photo
    sidecar_path = get_project_sidecar_path(photo_path)
    assert os.path.exists(sidecar_path)
    
    doc2 = load_project_document(photo_path)
    assert doc2 is not None
    assert doc2.style.color_theme == "Purple"
    assert doc2.style.font_size_preset == "Large (1.5x)"
    assert doc2.description == "Portrait session with custom badge"
    assert len(doc2.tags) == 1
    
    loaded_tag = doc2.tags[0]
    assert loaded_tag.name == "Elena Rostova"
    assert loaded_tag.x == 0.5
    assert loaded_tag.y == 0.35
    # Strict verification of layout persistence:
    assert loaded_tag.bx == 0.88
    assert loaded_tag.by == 0.12

def test_multilingual_unicode_preservation(tmp_path):
    """
    Verifies full Unicode roundtrip for accents, non-Latin and Persian/Arabic characters.
    """
    photo_path = str(tmp_path / "unicode_test.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "multilingual_names.jpg"), photo_path)
    
    tags = [
        FaceTag(name="علیرضا رضایی", x=0.2, y=0.3, w=0.15, h=0.15, bx=0.18, by=0.1),
        FaceTag(name="Björn Åke", x=0.5, y=0.3, w=0.15, h=0.15, bx=0.52, by=0.1),
        FaceTag(name="René François-Noël", x=0.8, y=0.3, w=0.15, h=0.15, bx=0.78, by=0.1)
    ]
    doc = ProjectDocument(
        image_path=photo_path,
        image_width=800,
        image_height=600,
        tags=tags,
        description="توضیحات عکس به زبان فارسی با حروف ویژه: é, à, ö"
    )
    
    save_project_document(doc)
    write_photo_metadata(photo_path, [t.to_dict() for t in tags], doc.description)
    
    loaded_doc = load_project_document(photo_path)
    assert loaded_doc is not None
    assert loaded_doc.description == "توضیحات عکس به زبان فارسی با حروف ویژه: é, à, ö"
    assert len(loaded_doc.tags) == 3
    assert loaded_doc.tags[0].name == "علیرضا رضایی"
    assert loaded_doc.tags[1].name == "Björn Åke"
    assert loaded_doc.tags[2].name == "René François-Noël"

def test_safe_failed_save_blocks_data_loss(tmp_path):
    """
    Verifies that if a save operation fails, the document remains marked dirty
    and draft is retained so user work is never silently lost.
    """
    photo_path = str(tmp_path / "safe_fail.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "small_image.jpg"), photo_path)
    
    doc = ProjectDocument(
        image_path=photo_path,
        image_width=64,
        image_height=64,
        tags=[FaceTag(name="Important Subject", x=0.5, y=0.5, w=0.2, h=0.2, bx=0.8, by=0.2)]
    )
    doc.mark_dirty()
    save_project_document(doc, is_draft=True)
    assert has_draft(photo_path)
    
    # Simulate failed write
    with patch("project_io.atomic_write_json", side_effect=IOError("Disk write error")):
        with pytest.raises(IOError):
            save_project_document(doc, is_draft=False)
            
    # Verification: draft is still preserved, document still dirty
    assert has_draft(photo_path)
    assert doc.is_dirty is True

def test_reset_positions_clears_overrides(tmp_path):
    """
    Verifies that resetting layout positions sets bx, by to None and dirty tracks.
    """
    photo_path = str(tmp_path / "reset_test.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "small_image.jpg"), photo_path)
    
    tag = FaceTag(name="Person", x=0.5, y=0.5, w=0.2, h=0.2, bx=0.9, by=0.1)
    doc = ProjectDocument(
        image_path=photo_path,
        image_width=64,
        image_height=64,
        tags=[tag]
    )
    save_project_document(doc)
    
    # User resets layout
    tag.bx = None
    tag.by = None
    doc.mark_dirty()
    save_project_document(doc)
    
    reloaded = load_project_document(photo_path)
    assert reloaded.tags[0].bx is None
    assert reloaded.tags[0].by is None
