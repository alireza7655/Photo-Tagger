import os
import json
import uuid
import shutil
import logging
import datetime
from typing import Optional, Tuple, Set, Union
from PIL import Image
from models import (
    ProjectDocument,
    FaceTag,
    TagStyle,
    CorruptProjectError,
    SchemaError,
    ProjectIdentityMismatchError,
    compute_content_fingerprint
)
from metadata import read_photo_metadata

logger = logging.getLogger(__name__)

SIDECAR_SUFFIX = ".phototagger.json"
DRAFT_SUFFIX = ".phototagger.draft.json"

def get_project_sidecar_path(image_path: str) -> str:
    return f"{image_path}{SIDECAR_SUFFIX}"

def get_draft_path(image_path: str) -> str:
    return f"{image_path}{DRAFT_SUFFIX}"

def has_draft(image_path: str) -> bool:
    if not image_path:
        return False
    draft_path = get_draft_path(image_path)
    return os.path.exists(draft_path) and os.path.getsize(draft_path) > 0

def discard_draft(image_path: str) -> bool:
    if not image_path:
        return False
    draft_path = get_draft_path(image_path)
    if os.path.exists(draft_path):
        try:
            os.remove(draft_path)
            return True
        except Exception as e:
            logger.warning("Failed to remove draft %s: %e", draft_path, e)
    return False

def backup_corrupt_sidecar(image_path: str) -> Optional[str]:
    """
    Creates a collision-safe timestamped backup copy of a corrupted or unsupported sidecar file.
    Guarantees the user's corrupted file is never destroyed or overwritten.
    """
    sidecar_path = get_project_sidecar_path(image_path)
    if not os.path.exists(sidecar_path):
        return None
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_suffix = uuid.uuid4().hex[:6]
    backup_path = f"{sidecar_path}.corrupt_{timestamp}_{unique_suffix}.bak"
    try:
        shutil.copy2(sidecar_path, backup_path)
        return backup_path
    except Exception as e:
        logger.error("Failed to backup corrupt sidecar %s: %e", sidecar_path, e)
        return None

def atomic_write_json(target_path: str, data: dict) -> bool:
    """
    Safely writes a JSON dictionary using an atomic replace pattern:
    1. Write to target_path + '.tmp'
    2. Flush and fsync
    3. os.replace(temp_path, target_path) to guarantee no partial or zero-byte file writes.
    """
    temp_path = f"{target_path}.tmp"
    dir_name = os.path.dirname(target_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
        
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
            
        os.replace(temp_path, target_path)
        return True
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise IOError(f"Failed to write atomically to {target_path}: {e}")

def save_project_document(
    doc: ProjectDocument,
    is_draft: bool = False,
    blocked_sidecars: Optional[Set[str]] = None
) -> bool:
    """
    Persists a ProjectDocument to disk.
    If is_draft is True, saves to the draft location.
    If is_draft is False, saves to the canonical sidecar and removes any existing draft.
    Centralized protection: if target sidecar or document path is in blocked_sidecars,
    raises IOError to prevent overwriting.
    """
    if not doc.image_path:
        return False
        
    target_path = get_draft_path(doc.image_path) if is_draft else get_project_sidecar_path(doc.image_path)
    
    if not is_draft and blocked_sidecars:
        if target_path in blocked_sidecars or doc.image_path in blocked_sidecars:
            raise IOError(f"Cannot overwrite protected/corrupt sidecar: {target_path}")
        
    if not is_draft and doc.extra:
        doc.extra.pop('_recovery_state', None)
        doc.extra.pop('_dirty_project', None)
        doc.extra.pop('_dirty_metadata', None)
    doc_dict = doc.to_dict()
    success = atomic_write_json(target_path, doc_dict)
    if success and not is_draft:
        doc.mark_clean()
        discard_draft(doc.image_path)
        
    return success

def load_project_document(
    image_path: str,
    expected_dimensions: Optional[Tuple[int, int]] = None,
    actual_pil_img: Optional[Image.Image] = None
) -> Optional[ProjectDocument]:
    """
    Loads project document from canonical sidecar if it exists.
    Raises CorruptProjectError if file exists but contains invalid JSON.
    Raises SchemaError if schema version is unsupported or malformed.
    Raises ProjectIdentityMismatchError if expected_dimensions or content fingerprint do not match.
    Returns None if sidecar does not exist.
    """
    sidecar_path = get_project_sidecar_path(image_path)
    if not os.path.exists(sidecar_path):
        return None
        
    try:
        with open(sidecar_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise CorruptProjectError(f"Sidecar project file {sidecar_path} is corrupted: {e}")
    except Exception as e:
        raise CorruptProjectError(f"Error reading sidecar project file {sidecar_path}: {e}")
        
    doc = ProjectDocument.from_dict(data, image_path=image_path)
    if expected_dimensions:
        doc.validate_identity(
            actual_width=expected_dimensions[0],
            actual_height=expected_dimensions[1],
            actual_pil_img=actual_pil_img
        )
        
    return doc

def load_draft(
    image_path: str,
    expected_dimensions: Optional[Tuple[int, int]] = None,
    actual_pil_img: Optional[Image.Image] = None
) -> Optional[ProjectDocument]:
    """
    Loads recovery draft if it exists.
    Raises CorruptProjectError if draft exists but is corrupted.
    Validates identity against actual image if provided.
    """
    draft_path = get_draft_path(image_path)
    if not os.path.exists(draft_path):
        return None
        
    try:
        with open(draft_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise CorruptProjectError(f"Recovery draft file {draft_path} is corrupted: {e}")
        
    doc = ProjectDocument.from_dict(data, image_path=image_path)
    if expected_dimensions:
        doc.validate_identity(
            actual_width=expected_dimensions[0],
            actual_height=expected_dimensions[1],
            actual_pil_img=actual_pil_img
        )
    doc.mark_dirty()
    return doc

def import_from_image_metadata(
    image_path: str,
    width: int,
    height: int,
    orientation: int = 1,
    existing_style: Optional[TagStyle] = None,
    actual_pil_img: Optional[Image.Image] = None
) -> ProjectDocument:
    """
    Imports tags and description from standard embedded XMP/EXIF.
    Generates stable UUIDs for legacy tags.
    Computes content fingerprint from actual image.
    """
    data = read_photo_metadata(image_path)
    raw_tags = data.get("tags", [])
    description = data.get("description", "")
    
    face_tags = []
    for t in raw_tags:
        tag = FaceTag(
            name=t.get("name", ""),
            x=t.get("x", 0.0),
            y=t.get("y", 0.0),
            w=t.get("w", 0.0),
            h=t.get("h", 0.0),
            tag_id=t.get("id"),
            bx=t.get("bx"),
            by=t.get("by")
        )
        face_tags.append(tag)
        
    fingerprint = compute_content_fingerprint(actual_pil_img) if actual_pil_img else ""
    
    doc = ProjectDocument(
        image_path=image_path,
        image_width=width,
        image_height=height,
        tags=face_tags,
        description=description,
        style=existing_style or TagStyle(),
        orientation=orientation,
        content_fingerprint=fingerprint,
        is_dirty=False
    )
    return doc
