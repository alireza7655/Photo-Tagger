import os
import uuid
import math
import hashlib
import datetime
from typing import List, Optional, Dict, Any
from PIL import Image

CURRENT_SCHEMA_VERSION = 1

class SchemaError(Exception):
    """Raised when project document schema is invalid, malformed, or unsupported."""
    pass

class CorruptProjectError(Exception):
    """Raised when project document cannot be parsed (malformed JSON or corrupted file)."""
    pass

class ProjectIdentityMismatchError(Exception):
    """Raised when project document image identity does not match the actual image file."""
    pass

def compute_content_fingerprint(pil_img: Image.Image) -> str:
    """
    Computes a content fingerprint from raw normalized pixels.
    Downsamples to a standard 32x32 grid.
    If the image has an alpha channel, normalizes to RGBA (alpha-sensitive).
    Otherwise normalizes to RGB.
    Hashes the normalized raw pixel bytes.
    """
    if pil_img is None:
        return ""
    try:
        has_alpha = pil_img.mode in ('RGBA', 'LA', 'PA') or (
            'transparency' in pil_img.info
        )
        target_mode = "RGBA" if has_alpha else "RGB"
        thumb = pil_img.convert(target_mode).resize((32, 32), Image.Resampling.BILINEAR)
        return hashlib.sha256(thumb.tobytes()).hexdigest()[:16]
    except Exception:
        return ""

def normalize_badge_shape(shape_val: Any) -> str:
    """
    Normalizes badge shape input to canonical values: 'auto', 'rounded_square', 'square'.
    - Maps legacy 'circle', 'pill', 'auto pill/circle' to 'auto'.
    - Maps legacy 'round_rect', 'rounded square (prototype)' to 'rounded_square'.
    - Maps 'square (prototype)', 'rect' to 'square'.
    - Unknown/None values safely fall back to 'auto'.
    """
    if shape_val is None:
        return "auto"
    s = str(shape_val).lower().strip()
    if s in ("rounded_square", "round_rect", "rounded square", "rounded square (prototype)", "rounded-square"):
        return "rounded_square"
    elif s in ("square", "rect", "square (prototype)"):
        return "square"
    elif s in ("auto", "circle", "pill", "auto pill/circle", "auto pill / circle", "auto (circle/pill)"):
        return "auto"
    return "auto"


CANONICAL_PALETTE: Dict[str, Dict[str, Any]] = {
    "Teal": {
        "name": "Teal",
        "hex": "#0d9488",
        "hover_hex": "#14b8a6",
        "rgb": (13, 148, 136),
        "text_color": "#ffffff",
        "text_rgb": (255, 255, 255, 255),
        "hover": "rgba(13, 148, 136, 0.15)"
    },
    "Blue": {
        "name": "Blue",
        "hex": "#2563eb",
        "hover_hex": "#3b82f6",
        "rgb": (37, 99, 235),
        "text_color": "#ffffff",
        "text_rgb": (255, 255, 255, 255),
        "hover": "rgba(37, 99, 235, 0.15)"
    },
    "Purple": {
        "name": "Purple",
        "hex": "#7c3aed",
        "hover_hex": "#8b5cf6",
        "rgb": (124, 58, 237),
        "text_color": "#ffffff",
        "text_rgb": (255, 255, 255, 255),
        "hover": "rgba(124, 58, 237, 0.15)"
    },
    "Green": {
        "name": "Green",
        "hex": "#059669",
        "hover_hex": "#10b981",
        "rgb": (5, 150, 105),
        "text_color": "#ffffff",
        "text_rgb": (255, 255, 255, 255),
        "hover": "rgba(5, 150, 105, 0.15)"
    },
    "Orange/Red": {
        "name": "Orange/Red",
        "hex": "#ea580c",
        "hover_hex": "#f97316",
        "rgb": (234, 88, 12),
        "text_color": "#ffffff",
        "text_rgb": (255, 255, 255, 255),
        "hover": "rgba(234, 88, 12, 0.15)"
    },
    "Yellow": {
        "name": "Yellow",
        "hex": "#eab308",
        "hover_hex": "#facc15",
        "rgb": (234, 179, 8),
        "text_color": "#000000",
        "text_rgb": (0, 0, 0, 255),
        "hover": "rgba(234, 179, 8, 0.15)"
    },
    "White": {
        "name": "White",
        "hex": "#ffffff",
        "hover_hex": "#f8fafc",
        "rgb": (255, 255, 255),
        "text_color": "#000000",
        "text_rgb": (0, 0, 0, 255),
        "hover": "rgba(255, 255, 255, 0.25)"
    },
    "Black": {
        "name": "Black",
        "hex": "#1e293b",
        "hover_hex": "#334155",
        "rgb": (30, 41, 59),
        "text_color": "#ffffff",
        "text_rgb": (255, 255, 255, 255),
        "hover": "rgba(30, 41, 59, 0.25)"
    }
}


def get_canonical_color_style(name: Optional[str]) -> Dict[str, Any]:
    """
    Resolves any color name or alias to the authoritative canonical palette definition.
    Guarantees all 8 swatches resolve consistently across Tagging, Layout, Preview, and Exports.
    """
    if not name:
        return CANONICAL_PALETTE["Teal"]
    n = str(name).strip()
    if n in CANONICAL_PALETTE:
        return CANONICAL_PALETTE[n]
    if n in ("Red", "Orange", "Orange-Red", "orange/red", "red", "orange"):
        return CANONICAL_PALETTE["Orange/Red"]
    for k, v in CANONICAL_PALETTE.items():
        if k.lower() == n.lower():
            return v
    return CANONICAL_PALETTE["Teal"]


class TagStyle:
    def __init__(
        self,
        color_theme: str = "Teal",
        font_size_preset: str = "Auto (1.0x)",
        font_family: str = "Segoe UI",
        badge_shape: str = "auto",
        preset_name: str = "Classic",
        extra: Optional[Dict[str, Any]] = None
    ):
        self.color_theme = str(color_theme)
        self.font_size_preset = str(font_size_preset)
        self.font_family = str(font_family)
        self.badge_shape = normalize_badge_shape(badge_shape)
        self.preset_name = str(preset_name)
        self.extra = dict(extra) if extra else {}

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "color_theme": self.color_theme,
            "font_size_preset": self.font_size_preset,
            "font_family": self.font_family,
            "badge_shape": normalize_badge_shape(self.badge_shape),
            "preset_name": self.preset_name
        }
        if self.extra:
            d["extra"] = self.extra
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TagStyle":
        if not isinstance(data, dict):
            return cls()
        return cls(
            color_theme=data.get("color_theme", "Teal"),
            font_size_preset=data.get("font_size_preset", "Auto (1.0x)"),
            font_family=data.get("font_family", "Segoe UI"),
            badge_shape=normalize_badge_shape(data.get("badge_shape", "auto")),
            preset_name=data.get("preset_name", "Classic"),
            extra=data.get("extra", {})
        )

def _validate_finite_float(val: Any, name: str) -> float:
    try:
        f = float(val)
    except (TypeError, ValueError):
        raise SchemaError(f"Field '{name}' must be a numeric value, got {type(val).__name__}")
    if not math.isfinite(f):
        raise SchemaError(f"Field '{name}' must be a finite number, got {val}")
    return f

class FaceTag:
    def __init__(
        self,
        name: str,
        x: float,
        y: float,
        w: float,
        h: float,
        tag_id: Optional[str] = None,
        bx: Optional[float] = None,
        by: Optional[float] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None
    ):
        self.id = str(tag_id) if tag_id else str(uuid.uuid4())
        self.name = str(name) if name is not None else ""
        self.x = _validate_finite_float(x, "x")
        self.y = _validate_finite_float(y, "y")
        self.w = _validate_finite_float(w, "w")
        self.h = _validate_finite_float(h, "h")
        self.bx = _validate_finite_float(bx, "bx") if bx is not None else None
        self.by = _validate_finite_float(by, "by") if by is not None else None
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.created_at = created_at or now_iso
        self.updated_at = updated_at or now_iso
        self.extra = dict(extra) if extra else {}

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "id": self.id,
            "name": self.name,
            "x": round(self.x, 6),
            "y": round(self.y, 6),
            "w": round(self.w, 6),
            "h": round(self.h, 6),
            "bx": round(self.bx, 6) if self.bx is not None else None,
            "by": round(self.by, 6) if self.by is not None else None,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
        if self.extra:
            d["extra"] = self.extra
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FaceTag":
        if not isinstance(data, dict):
            raise SchemaError(f"FaceTag entry must be a dictionary, got {type(data).__name__}")
        
        tag_id = data.get("id")
        if tag_id is not None and not isinstance(tag_id, str):
            raise SchemaError(f"FaceTag 'id' must be a string, got {type(tag_id).__name__}")
        
        return cls(
            name=data.get("name", ""),
            x=data.get("x", 0.0),
            y=data.get("y", 0.0),
            w=data.get("w", 0.0),
            h=data.get("h", 0.0),
            tag_id=tag_id,
            bx=data.get("bx"),
            by=data.get("by"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            extra=data.get("extra", {})
        )

class ProjectDocument:
    def __init__(
        self,
        image_path: str,
        image_width: int,
        image_height: int,
        tags: Optional[List[FaceTag]] = None,
        description: str = "",
        style: Optional[TagStyle] = None,
        orientation: int = 1,
        content_fingerprint: Optional[str] = None,
        schema_version: int = CURRENT_SCHEMA_VERSION,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        is_dirty: bool = False,
        extra: Optional[Dict[str, Any]] = None
    ):
        self.image_path = image_path
        self.image_filename = os.path.basename(image_path) if image_path else ""
        self.image_width = int(image_width)
        self.image_height = int(image_height)
        self.orientation = int(orientation)
        self.content_fingerprint = content_fingerprint or ""
        self.tags = list(tags) if tags is not None else []
        self.description = str(description) if description is not None else ""
        self.style = style if style is not None else TagStyle()
        self.schema_version = int(schema_version)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.created_at = created_at or now_iso
        self.updated_at = updated_at or now_iso
        self.is_dirty = is_dirty
        self.extra = dict(extra) if extra else {}

    def mark_dirty(self):
        self.is_dirty = True
        self.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    def mark_clean(self):
        self.is_dirty = False

    def get_tag_by_id(self, tag_id: str) -> Optional[FaceTag]:
        for tag in self.tags:
            if tag.id == tag_id:
                return tag
        return None

    def validate_identity(
        self,
        actual_width: int,
        actual_height: int,
        actual_pil_img: Optional[Image.Image] = None
    ) -> None:
        """
        Validates that document image identity matches the actual image file:
        1. Validates dimensions match (accounting for stored rotation).
        2. If content_fingerprint is recorded and actual_pil_img is supplied,
           validates that content fingerprint matches, rejecting same-size unrelated images.
        """
        if self.image_width > 0 and self.image_height > 0:
            rot = self.extra.get("rotation", 0) if self.extra else 0
            if rot in (90, 270):
                exp_w, exp_h = self.image_height, self.image_width
            else:
                exp_w, exp_h = self.image_width, self.image_height
            if exp_w != actual_width or exp_h != actual_height:
                raise ProjectIdentityMismatchError(
                    f"Project document expects dimensions {self.image_width}x{self.image_height}, "
                    f"but target photo is {actual_width}x{actual_height}."
                )
        if actual_pil_img is not None:
            rot = self.extra.get("rotation", 0) if self.extra else 0
            test_img = actual_pil_img
            if rot == 90:
                test_img = actual_pil_img.transpose(Image.Transpose.ROTATE_270)
            elif rot == 270:
                test_img = actual_pil_img.transpose(Image.Transpose.ROTATE_90)
            elif rot == 180:
                test_img = actual_pil_img.transpose(Image.Transpose.ROTATE_180)
            actual_fp = compute_content_fingerprint(test_img)
            if self.content_fingerprint:
                if actual_fp and actual_fp != self.content_fingerprint:
                    raise ProjectIdentityMismatchError(
                        f"Content fingerprint mismatch ({actual_fp} != {self.content_fingerprint}): "
                        f"image content has been replaced with a different photo."
                    )
            else:
                self.content_fingerprint = actual_fp

    def sync_from_app_state(
        self,
        faces_dicts: List[Dict[str, Any]],
        description: str,
        color_theme: str,
        font_size_preset: str,
        pil_image: Optional[Image.Image] = None,
        preset_name: Optional[str] = None,
        badge_shape: Optional[str] = None,
        font_family: Optional[str] = None
    ) -> None:
        """
        Synchronizes UI edits into this authoritative ProjectDocument:
        - Preserves document created_at, schema_version, orientation, and extra fields.
        - Preserves tag created_at and tag extra fields for all surviving tags.
        - Updates style theme & font size while preserving badge_shape, font_family, and style extra.
        - Automatically computes content_fingerprint if missing.
        """
        self.description = str(description)
        self.style.color_theme = str(color_theme)
        self.style.font_size_preset = str(font_size_preset)
        if preset_name is not None:
            self.style.preset_name = str(preset_name)
        if badge_shape is not None:
            self.style.badge_shape = normalize_badge_shape(badge_shape)
        if font_family is not None:
            self.style.font_family = str(font_family)
        
        if pil_image is not None:
            w, h = pil_image.size
            self.image_width = w
            self.image_height = h
            self.content_fingerprint = compute_content_fingerprint(pil_image)
                
        # Synchronize tags by stable UUID
        updated_tags = []
        for f in faces_dicts:
            tag_id = f.get('id') or str(uuid.uuid4())
            f['id'] = tag_id  # Ensure dictionary retains id
            existing_tag = self.get_tag_by_id(tag_id)
            if existing_tag:
                existing_tag.name = f.get('name', '')
                existing_tag.x = _validate_finite_float(f['x'], 'x')
                existing_tag.y = _validate_finite_float(f['y'], 'y')
                existing_tag.w = _validate_finite_float(f['w'], 'w')
                existing_tag.h = _validate_finite_float(f['h'], 'h')
                existing_tag.bx = _validate_finite_float(f['bx'], 'bx') if f.get('bx') is not None else None
                existing_tag.by = _validate_finite_float(f['by'], 'by') if f.get('by') is not None else None
                existing_tag.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
                updated_tags.append(existing_tag)
            else:
                new_tag = FaceTag(
                    name=f.get('name', ''),
                    x=f['x'],
                    y=f['y'],
                    w=f['w'],
                    h=f['h'],
                    tag_id=tag_id,
                    bx=f.get('bx'),
                    by=f.get('by'),
                    created_at=f.get('created_at'),
                    extra=f.get('extra', {})
                )
                updated_tags.append(new_tag)
        self.tags = updated_tags
        self.mark_dirty()

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "schema_version": self.schema_version,
            "application": "Photo Tagger Preview",
            "image": {
                "filename": self.image_filename,
                "width": self.image_width,
                "height": self.image_height,
                "orientation": self.orientation,
                "content_fingerprint": self.content_fingerprint
            },
            "description": self.description,
            "style": self.style.to_dict(),
            "tags": [tag.to_dict() for tag in self.tags],
            "metadata": {
                "created_at": self.created_at,
                "updated_at": self.updated_at
            }
        }
        if self.extra:
            d["extra"] = self.extra
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any], image_path: str) -> "ProjectDocument":
        if not isinstance(data, dict):
            raise SchemaError(f"Project data must be a dictionary, got {type(data).__name__}")
        
        raw_schema = data.get("schema_version")
        if raw_schema is None or not isinstance(raw_schema, int):
            raise SchemaError("Project data missing integer 'schema_version'")
            
        if raw_schema > CURRENT_SCHEMA_VERSION:
            raise SchemaError(
                f"Unsupported future schema version {raw_schema}. "
                f"This application supports up to version {CURRENT_SCHEMA_VERSION}."
            )
            
        migrated_data = cls.migrate_schema(data, from_version=raw_schema, to_version=CURRENT_SCHEMA_VERSION)
        
        img_info = migrated_data.get("image")
        if not isinstance(img_info, dict):
            raise SchemaError("Project data missing valid 'image' dictionary")
            
        tags_raw = migrated_data.get("tags")
        if not isinstance(tags_raw, list):
            raise SchemaError("Project data 'tags' must be a list")
            
        tags = []
        seen_ids = set()
        for i, t in enumerate(tags_raw):
            try:
                face_tag = FaceTag.from_dict(t)
            except SchemaError as se:
                raise SchemaError(f"Malformed tag at index {i}: {se}")
            if face_tag.id in seen_ids:
                raise SchemaError(f"Duplicate face tag id '{face_tag.id}' at index {i}")
            seen_ids.add(face_tag.id)
            tags.append(face_tag)
        
        style = TagStyle.from_dict(migrated_data.get("style", {}))
        meta = migrated_data.get("metadata", {})
        
        width = int(img_info.get("width", 0))
        height = int(img_info.get("height", 0))
        if width < 0 or height < 0:
            raise SchemaError(f"Invalid image dimensions: {width}x{height}")
            
        return cls(
            image_path=image_path,
            image_width=width,
            image_height=height,
            tags=tags,
            description=str(migrated_data.get("description", "")),
            style=style,
            orientation=int(img_info.get("orientation", 1)),
            content_fingerprint=str(img_info.get("content_fingerprint", "")),
            schema_version=CURRENT_SCHEMA_VERSION,
            created_at=meta.get("created_at"),
            updated_at=meta.get("updated_at"),
            is_dirty=False,
            extra=migrated_data.get("extra", {})
        )

    @staticmethod
    def migrate_schema(data: Dict[str, Any], from_version: int, to_version: int) -> Dict[str, Any]:
        """
        Migrates project data between schema versions.
        Future version migrations will be chained here.
        """
        current_data = dict(data)
        return current_data
