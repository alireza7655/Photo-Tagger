import os
import shutil
import pytest
from models import ProjectDocument, FaceTag, TagStyle, SchemaError, CorruptProjectError, CURRENT_SCHEMA_VERSION
from project_io import (
    save_project_document,
    load_project_document,
    has_draft,
    load_draft,
    discard_draft,
    import_from_image_metadata,
    get_project_sidecar_path,
    get_draft_path
)
from metadata import write_photo_metadata, read_photo_metadata

FIXTURES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "fixtures"))

def test_models_serialization_and_uuid():
    tag1 = FaceTag(name="Alice", x=0.2, y=0.3, w=0.1, h=0.1, bx=0.22, by=0.18)
    assert tag1.id is not None
    assert len(tag1.id) >= 32
    
    d = tag1.to_dict()
    assert d["name"] == "Alice"
    assert d["bx"] == 0.22
    assert d["by"] == 0.18
    
    tag2 = FaceTag.from_dict(d)
    assert tag2.id == tag1.id
    assert tag2.name == "Alice"
    assert tag2.bx == 0.22
    assert tag2.by == 0.18

def test_project_document_serialization():
    style = TagStyle(color_theme="Purple", font_size_preset="Medium (1.2x)")
    tag = FaceTag(name="Bob", x=0.5, y=0.5, w=0.2, h=0.2, bx=0.6, by=0.4)
    doc = ProjectDocument(
        image_path="test.jpg",
        image_width=1000,
        image_height=800,
        tags=[tag],
        description="A nice photo",
        style=style
    )
    
    doc_dict = doc.to_dict()
    assert doc_dict["schema_version"] == CURRENT_SCHEMA_VERSION
    assert doc_dict["style"]["color_theme"] == "Purple"
    assert len(doc_dict["tags"]) == 1
    assert doc_dict["tags"][0]["name"] == "Bob"
    assert doc_dict["tags"][0]["bx"] == 0.6
    
    loaded_doc = ProjectDocument.from_dict(doc_dict, image_path="test.jpg")
    assert loaded_doc.image_filename == "test.jpg"
    assert loaded_doc.style.color_theme == "Purple"
    assert len(loaded_doc.tags) == 1
    assert loaded_doc.tags[0].name == "Bob"
    assert loaded_doc.tags[0].bx == 0.6
    assert loaded_doc.tags[0].by == 0.4

def test_future_schema_rejection():
    future_data = {
        "schema_version": 999,
        "image": {"filename": "future.jpg", "width": 100, "height": 100},
        "tags": []
    }
    with pytest.raises(SchemaError) as exc_info:
        ProjectDocument.from_dict(future_data, image_path="future.jpg")
    assert "Unsupported future schema version" in str(exc_info.value)

def test_sidecar_save_load_roundtrip_preserves_layout(tmp_path):
    """
    Verifies that layout positions (bx, by) and styles are permanently saved and restored!
    """
    photo_path = str(tmp_path / "portrait.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), photo_path)
    
    style = TagStyle(color_theme="Blue", font_size_preset="Large (1.5x)")
    tag = FaceTag(name="Subject 1", x=0.45, y=0.35, w=0.2, h=0.2, bx=0.75, by=0.15)
    doc = ProjectDocument(
        image_path=photo_path,
        image_width=800,
        image_height=1000,
        tags=[tag],
        description="Portrait with custom badge layout",
        style=style
    )
    
    # Save project sidecar
    saved = save_project_document(doc)
    assert saved is True
    assert os.path.exists(get_project_sidecar_path(photo_path))
    
    # Reload project document (simulating app restart)
    loaded_doc = load_project_document(photo_path)
    assert loaded_doc is not None
    assert loaded_doc.description == "Portrait with custom badge layout"
    assert loaded_doc.style.color_theme == "Blue"
    assert loaded_doc.style.font_size_preset == "Large (1.5x)"
    assert len(loaded_doc.tags) == 1
    
    loaded_tag = loaded_doc.tags[0]
    assert loaded_tag.name == "Subject 1"
    assert loaded_tag.x == 0.45
    assert loaded_tag.y == 0.35
    # Defect FIX verified: bx and by are preserved across restart!
    assert loaded_tag.bx == 0.75
    assert loaded_tag.by == 0.15
    assert loaded_tag.id == tag.id

def test_corrupt_sidecar_preservation(tmp_path):
    photo_path = str(tmp_path / "corrupt.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "small_image.jpg"), photo_path)
    sidecar_path = get_project_sidecar_path(photo_path)
    
    # Write corrupt JSON
    with open(sidecar_path, "w", encoding="utf-8") as f:
        f.write("{ invalid json corrupted content ...")
        
    with pytest.raises(CorruptProjectError):
        load_project_document(photo_path)
        
    # File must NOT be deleted or overwritten
    assert os.path.exists(sidecar_path)

def test_draft_lifecycle(tmp_path):
    photo_path = str(tmp_path / "draft_test.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "small_image.jpg"), photo_path)
    
    doc = ProjectDocument(
        image_path=photo_path,
        image_width=64,
        image_height=64,
        tags=[FaceTag(name="Draft Person", x=0.5, y=0.5, w=0.3, h=0.3)]
    )
    doc.mark_dirty()
    
    assert not has_draft(photo_path)
    
    # Save draft
    save_project_document(doc, is_draft=True)
    assert has_draft(photo_path)
    
    # Load draft
    restored_draft = load_draft(photo_path)
    assert restored_draft is not None
    assert restored_draft.tags[0].name == "Draft Person"
    assert restored_draft.is_dirty is True
    
    # Final save removes draft
    save_project_document(doc, is_draft=False)
    assert not has_draft(photo_path)

def test_legacy_xmp_import_with_uuid_assignment(tmp_path):
    photo_path = str(tmp_path / "legacy_photo.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "single_portrait.jpg"), photo_path)
    
    legacy_tags = [{"name": "Legacy Tag", "x": 0.4, "y": 0.4, "w": 0.2, "h": 0.2}]
    write_photo_metadata(photo_path, legacy_tags, "Legacy description")
    
    # No sidecar exists yet
    assert load_project_document(photo_path) is None
    
    # Import legacy metadata
    doc = import_from_image_metadata(photo_path, width=800, height=1000)
    assert doc.description == "Legacy description"
    assert len(doc.tags) == 1
    assert doc.tags[0].name == "Legacy Tag"
    assert doc.tags[0].id is not None
    assert len(doc.tags[0].id) >= 32
