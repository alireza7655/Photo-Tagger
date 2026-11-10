import os
import shutil
import pytest
from metadata import read_photo_metadata, write_photo_metadata, sort_faces_spatial

FIXTURES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "fixtures"))

def test_reproduce_layout_loss_on_save_reload(tmp_path):
    """
    Demonstrates baseline defect:
    When user moves badges (bx, by) in the layout editor,
    write_photo_metadata only serializes x, y, w, h into XMP.
    Upon reloading with read_photo_metadata, bx and by are completely lost!
    """
    src_file = os.path.join(FIXTURES_DIR, "single_portrait.jpg")
    test_photo = str(tmp_path / "test_portrait.jpg")
    shutil.copyfile(src_file, test_photo)
    
    # Simulate face with manual badge override bx=0.85, by=0.15
    faces = [
        {
            "name": "Jane Doe",
            "x": 0.5,
            "y": 0.35,
            "w": 0.25,
            "h": 0.25,
            "bx": 0.85,
            "by": 0.15
        }
    ]
    description = "Portrait photo test"
    
    # Save using current write_photo_metadata
    saved = write_photo_metadata(test_photo, faces, description)
    assert saved is True
    
    # Read back metadata using current read_photo_metadata
    loaded = read_photo_metadata(test_photo)
    assert loaded["description"] == description
    assert len(loaded["tags"]) == 1
    
    loaded_face = loaded["tags"][0]
    assert loaded_face["name"] == "Jane Doe"
    assert "x" in loaded_face
    assert "y" in loaded_face
    
    # Defect confirmation: bx and by are lost!
    assert "bx" not in loaded_face or loaded_face.get("bx") is None
    assert "by" not in loaded_face or loaded_face.get("by") is None
    print("\n[VERIFIED DEFECT] Custom badge position bx/by was discarded during metadata save/load.")

def test_delete_then_rename_vulnerability(tmp_path):
    """
    Demonstrates baseline defect in metadata.py lines 330-338:
    os.remove(image_path) followed by os.rename(temp_path, image_path).
    If write/rename fails midway or process terminates, original image is deleted.
    """
    test_photo = str(tmp_path / "protected_photo.jpg")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "small_image.jpg"), test_photo)
    
    faces = [{"name": "Test", "x": 0.5, "y": 0.5, "w": 0.2, "h": 0.2}]
    # Current behavior works when no error, but uses non-atomic remove then rename
    res = write_photo_metadata(test_photo, faces, "desc")
    assert res is True
    assert os.path.exists(test_photo)
