import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

import uuid
# Import our custom modules
from metadata import (
    read_photo_metadata, 
    write_photo_metadata, 
    write_interactive_html, 
    write_interactive_svg,
    draw_annotations_on_image,
    sort_faces_spatial,
    compute_badge_metrics,
    compute_default_badge_positions,
    get_badge_radius,
    shape_persian_arabic_text
)
from detector import detect_faces
from models import (
    ProjectDocument, 
    FaceTag, 
    TagStyle, 
    SchemaError, 
    CorruptProjectError, 
    ProjectIdentityMismatchError, 
    compute_content_fingerprint,
    CANONICAL_PALETTE,
    get_canonical_color_style
)
from project_io import (
    save_project_document,
    load_project_document,
    has_draft,
    load_draft,
    discard_draft,
    backup_corrupt_sidecar,
    import_from_image_metadata,
    get_project_sidecar_path
)

VERSION_FILE = os.path.join(os.path.dirname(__file__), "VERSION")
try:
    with open(VERSION_FILE, "r", encoding="utf-8") as _vf:
        APP_VERSION = _vf.read().strip()
except Exception:
    APP_VERSION = "3.0.0" 

# Configure customtkinter appearance
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# ==============================================================================
# Charcoal UI Design Tokens (AG_CHARCOAL_UI_POLISH)
# ==============================================================================
COLOR_WORKSPACE = "#242830"        # Main chrome & workspace background
COLOR_SETTINGS_SURFACE = "#2B303A"  # Settings panel, inspector cards & sidebar
COLOR_PHOTO_MATTE = "#16191F"       # Photo canvas matte background
COLOR_SURFACE_HOVER = "#353D4A"     # Subtle hover & pressed surface
COLOR_BORDER_SUBTLE = "#38404E"     # Subtle border for cards & quiet controls
COLOR_BORDER_STRONG = "#4B5565"     # Stronger contrast separator line
COLOR_TEXT_PRIMARY = "#F1F5F9"      # High-contrast primary text
COLOR_TEXT_SECONDARY = "#B9C3D4"    # Subtle secondary text
COLOR_TEXT_MUTED = "#64748B"        # Muted footer annotations
COLOR_ACCENT_PRIMARY = "#5B4EE7"    # Solid accent for primary action (editing)
COLOR_ACCENT_PRIMARY_HOVER = "#4338ca"
COLOR_ACCENT_EXPORT = COLOR_ACCENT_PRIMARY     # Solid accent for primary action (preview)
COLOR_ACCENT_EXPORT_HOVER = "#4338ca"
COLOR_STATUS_UNSAVED = "#F59E0B"    # Vivid amber dot for unsaved project
COLOR_STATUS_SAVED = "#94A3B8"      # Quiet slate dot for saved project
COLOR_STATUS_SYNCED = "#34D399"     # Mint check for synced metadata tags
COLOR_STATUS_PENDING = "#FBBF24"    # Amber dot for pending metadata write



class IconLabelButton(ctk.CTkButton):
    """Toolbar button with a tighter gap between its icon and label."""

    _image_label_spacing = 3


class WidgetTooltip:
    """
    Accessible floating dark-mode tooltip for Tk/CTk widgets
    with customizable delay and auto-positioning.
    """
    def __init__(self, widget, text, delay_ms=350):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.tip_window = None
        self._after_id = None
        
        self.widget.bind("<Enter>", self._on_enter, add="+")
        self.widget.bind("<Leave>", self._on_leave, add="+")
        self.widget.bind("<ButtonPress>", self._on_leave, add="+")
        self.widget.bind("<Destroy>", self._on_destroy, add="+")

    def _on_enter(self, event=None):
        self._cancel()
        self._after_id = self.widget.after(self.delay_ms, self.show_tip)

    def _on_leave(self, event=None):
        self._cancel()
        self.hide_tip()

    def _on_destroy(self, event=None):
        self._cancel()
        self.hide_tip()

    def _cancel(self):
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def show_tip(self):
        if self.tip_window or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + (self.widget.winfo_width() // 2)
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
            
            self.tip_window = tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{x}+{y}")
            tw.attributes("-topmost", True)
            
            label = tk.Label(
                tw,
                text=self.text,
                justify="left",
                background="#11111b",
                foreground="#cdd6f4",
                relief="solid",
                borderwidth=1,
                font=("Segoe UI", 9),
                padx=6,
                pady=3
            )
            label.pack(ipadx=1)
        except Exception:
            pass

    def hide_tip(self):
        if self.tip_window:
            try:
                self.tip_window.destroy()
            except Exception:
                pass
            self.tip_window = None


ToolTip = WidgetTooltip



def get_system_work_area():
    """Returns (left, top, width, height) of primary monitor usable work area (excluding taskbar)."""
    try:
        import ctypes
        from ctypes import wintypes
        class RECT(ctypes.Structure):
            _fields_ = [('left', wintypes.LONG), ('top', wintypes.LONG), ('right', wintypes.LONG), ('bottom', wintypes.LONG)]
        r = RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0):
            return r.left, r.top, r.right - r.left, r.bottom - r.top
    except Exception:
        pass
    return 0, 0, None, None


def hex_to_rgb(hex_str):
    h = str(hex_str).lstrip("#")
    if len(h) == 3:
        h = "".join([c*2 for c in h])
    if len(h) >= 6:
        try:
            return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
        except Exception:
            pass
    return (13, 148, 136)

def get_hex_luminance(hex_str):
    r, g, b = hex_to_rgb(hex_str)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0

def get_contrasting_hex(fill_hex):
    lum = get_hex_luminance(fill_hex)
    if lum > 0.5:
        return "#0f172a", "#000000"  # text, keyline
    else:
        return "#ffffff", "#ffffff"  # text, keyline


def draw_canvas_badge(canvas, cx, cy, num_str, r, fill_color, text_color="#ffffff", badge_shape="auto", tags=("badge_element",), font_family="Segoe UI", style_preset="Classic"):
    """
    Renders high-contrast circle, pill, rounded square, or square badge on Tk Canvas
    matching the shared tag renderer metrics for 1..999 and selected preset style.
    Guarantees visible badge fill changes for every preset, with mathematically
    calculated WCAG contrast for keylines and numerals.
    """
    from models import normalize_badge_shape
    shape = normalize_badge_shape(badge_shape)
    metrics = compute_badge_metrics(num_str, r, badge_shape=shape)
    w, h, is_pill = metrics
    hw = w / 2.0
    hh = h / 2.0
    cr = metrics.corner_radius
    
    preset_lower = str(style_preset or "Classic").strip().lower()
    is_single_outline = "outline" in preset_lower
    is_minimal = "minimal" in preset_lower
    is_borderless = "borderless" in preset_lower
    is_print = "print" in preset_lower
    
    calc_text, calc_keyline = get_contrasting_hex(fill_color)
    
    if is_single_outline:
        # Exactly one visible perimeter on circles and rectangles, without a halo, inset line, or shadow
        # Visible badge fill responds to Tag Color Accent
        border_col = calc_keyline
        shadow_col = None
        base_fill = fill_color
        num_color = calc_text
    elif is_minimal or is_borderless:
        # Minimal & Borderless: solid fill with no stroke (width=0), no shadow, no halo
        border_col = None
        shadow_col = None
        base_fill = fill_color
        num_color = calc_text
    elif is_print:
        # Opaque rectangular badge with crisp black/contrasting keyline and text
        border_col = "#000000" if fill_color.lower() in ("#ffffff", "#f8fafc", "#f1f5f9") else calc_keyline
        shadow_col = None
        base_fill = fill_color
        num_color = "#000000" if fill_color.lower() in ("#ffffff", "#f8fafc", "#f1f5f9") else calc_text
    else:
        # Classic / High Contrast: colored fill and contrasting keyline
        border_col = calc_keyline
        shadow_col = None
        base_fill = fill_color
        num_color = calc_text
    
    # Invisible base bounding rectangle so coords queries for tags return the outer bounding box
    canvas.create_rectangle(cx - hw, cy - hh, cx + hw, cy + hh, fill="", outline="", tags=tags)
    
    if shape == "square":
        # Sharp square / rectangle
        if shadow_col:
            canvas.create_rectangle(cx - hw - 1, cy - hh - 1, cx + hw + 1, cy + hh + 1, fill="", outline=shadow_col, width=1, tags=tags)
        b_w = 2 if border_col else 0
        canvas.create_rectangle(cx - hw, cy - hh, cx + hw, cy + hh, fill=base_fill, outline=border_col or "", width=b_w, tags=tags)
    elif shape == "rounded_square":
        # CAD rounded rectangle with corner radius cr
        if shadow_col:
            canvas.create_line(cx - hw + cr, cy - hh - 1, cx + hw - cr, cy - hh - 1, fill=shadow_col, width=1, tags=tags)
            canvas.create_line(cx - hw + cr, cy + hh + 1, cx + hw - cr, cy + hh + 1, fill=shadow_col, width=1, tags=tags)
            canvas.create_line(cx - hw - 1, cy - hh + cr, cx - hw - 1, cy + hh - cr, fill=shadow_col, width=1, tags=tags)
            canvas.create_line(cx + hw + 1, cy - hh + cr, cx + hw + 1, cy + hh - cr, fill=shadow_col, width=1, tags=tags)
        
        # Cross fill and corners
        canvas.create_rectangle(cx - hw + cr, cy - hh, cx + hw - cr, cy + hh, fill=base_fill, outline="", tags=tags)
        canvas.create_rectangle(cx - hw, cy - hh + cr, cx + hw, cy + hh - cr, fill=base_fill, outline="", tags=tags)
        canvas.create_oval(cx - hw, cy - hh, cx - hw + 2*cr, cy - hh + 2*cr, fill=base_fill, outline="", tags=tags)
        canvas.create_oval(cx + hw - 2*cr, cy - hh, cx + hw, cy - hh + 2*cr, fill=base_fill, outline="", tags=tags)
        canvas.create_oval(cx - hw, cy + hh - 2*cr, cx - hw + 2*cr, cy + hh, fill=base_fill, outline="", tags=tags)
        canvas.create_oval(cx + hw - 2*cr, cy + hh - 2*cr, cx + hw, cy + hh, fill=base_fill, outline="", tags=tags)
        
        if border_col:
            # Border lines
            canvas.create_line(cx - hw + cr, cy - hh, cx + hw - cr, cy - hh, fill=border_col, width=2, tags=tags)
            canvas.create_line(cx - hw + cr, cy + hh, cx + hw - cr, cy + hh, fill=border_col, width=2, tags=tags)
            canvas.create_line(cx - hw, cy - hh + cr, cx - hw, cy + hh - cr, fill=border_col, width=2, tags=tags)
            canvas.create_line(cx + hw, cy - hh + cr, cx + hw, cy + hh - cr, fill=border_col, width=2, tags=tags)
            
            # Border corner arcs
            canvas.create_arc(cx - hw, cy - hh, cx - hw + 2*cr, cy - hh + 2*cr, start=90, extent=90, style="arc", outline=border_col, width=2, tags=tags)
            canvas.create_arc(cx + hw - 2*cr, cy - hh, cx + hw, cy - hh + 2*cr, start=0, extent=90, style="arc", outline=border_col, width=2, tags=tags)
            canvas.create_arc(cx + hw - 2*cr, cy + hh - 2*cr, cx + hw, cy + hh, start=270, extent=90, style="arc", outline=border_col, width=2, tags=tags)
            canvas.create_arc(cx - hw, cy + hh - 2*cr, cx - hw + 2*cr, cy + hh, start=180, extent=90, style="arc", outline=border_col, width=2, tags=tags)
    else:
        # Auto: circle for single digit, pill for multi digits
        if not is_pill:
            if shadow_col:
                canvas.create_oval(cx - r - 1.5, cy - r - 1.5, cx + r + 1.5, cy + r + 1.5, 
                                   fill="", outline=shadow_col, width=1.5, tags=tags)
            b_w = 2 if border_col else 0
            canvas.create_oval(cx - r, cy - r, cx + r, cy + r, 
                               fill=base_fill, outline=border_col or "", width=b_w, tags=tags)
        else:
            if shadow_col:
                # High contrast outer shadow
                canvas.create_oval(cx - hw - 1, cy - r - 1, cx - hw + 2*r + 1, cy + r + 1, fill="", outline=shadow_col, width=1, tags=tags)
                canvas.create_oval(cx + hw - 2*r - 1, cy - r - 1, cx + hw + 1, cy + r + 1, fill="", outline=shadow_col, width=1, tags=tags)
                canvas.create_rectangle(cx - hw + r, cy - r - 1, cx + hw - r, cy + r + 1, fill="", outline="", tags=tags)
            # Inner fill
            canvas.create_oval(cx - hw, cy - r, cx - hw + 2*r, cy + r, fill=base_fill, outline="", tags=tags)
            canvas.create_oval(cx + hw - 2*r, cy - r, cx + hw, cy + r, fill=base_fill, outline="", tags=tags)
            canvas.create_rectangle(cx - hw + r, cy - r, cx + hw - r, cy + r, fill=base_fill, outline="", tags=tags)
            if border_col:
                # High contrast border
                canvas.create_line(cx - hw + r, cy - r, cx + hw - r, cy - r, fill=border_col, width=2, tags=tags)
                canvas.create_line(cx - hw + r, cy + r, cx + hw - r, cy + r, fill=border_col, width=2, tags=tags)
                canvas.create_arc(cx - hw, cy - r, cx - hw + 2*r, cy + r, start=90, extent=180, style="arc", outline=border_col, width=2, tags=tags)
                canvas.create_arc(cx + hw - 2*r, cy - r, cx + hw, cy + r, start=270, extent=180, style="arc", outline=border_col, width=2, tags=tags)
    
    digit_count = len(str(num_str))
    if digit_count <= 1:
        font_sz = max(8, int(r * 0.72))
    elif digit_count == 2:
        font_sz = max(8, int(r * 0.70))
    elif digit_count == 3:
        font_sz = max(8, int(r * 0.65))
    else:
        font_sz = max(7, int(r * 0.58))
        
    canvas.create_text(cx, cy, text=str(num_str), fill=num_color, font=(font_family, font_sz, "bold"), tags=tags)


def _resolve_app_badge_shape(app) -> str:
    """
    Safely resolves the current badge shape from an app instance or test mock.
    Checks combo_badge_shape, seg_badge_shape, or current_doc.style.
    """
    from models import normalize_badge_shape
    if hasattr(app, 'combo_badge_shape') and hasattr(app.combo_badge_shape, 'get'):
        try:
            return normalize_badge_shape(app.combo_badge_shape.get())
        except Exception:
            pass
    if hasattr(app, 'seg_badge_shape') and hasattr(app.seg_badge_shape, 'get'):
        try:
            val = app.seg_badge_shape.get()
            if val == "Square":
                return "square"
            elif val in ("Rounded", "Rounded Square"):
                return "rounded_square"
            elif val in ("Pill", "Auto Pill/Circle", "Auto Pill", "auto"):
                return "auto"
        except Exception:
            pass
    if hasattr(app, 'current_doc') and app.current_doc and hasattr(app.current_doc, 'style'):
        try:
            return normalize_badge_shape(getattr(app.current_doc.style, 'badge_shape', 'auto'))
        except Exception:
            pass
    return "auto"


def _resolve_app_tag_font(app) -> str:
    """
    Safely resolves the current tag font family from an app instance or test mock.
    Checks seg_tag_font, combo_tag_font, or current_doc.style.
    Supported initial choices: 'Segoe UI' (default), 'Tahoma', 'Arial'.
    """
    if hasattr(app, 'seg_tag_font') and hasattr(app.seg_tag_font, 'get'):
        try:
            val = app.seg_tag_font.get()
            if val in ("Segoe UI", "Tahoma", "Arial"):
                return val
        except Exception:
            pass
    if hasattr(app, 'combo_tag_font') and hasattr(app.combo_tag_font, 'get'):
        try:
            val = app.combo_tag_font.get()
            if val in ("Segoe UI", "Tahoma", "Arial"):
                return val
        except Exception:
            pass
    if hasattr(app, 'current_doc') and app.current_doc and hasattr(app.current_doc, 'style'):
        try:
            val = getattr(app.current_doc.style, 'font_family', None)
            if val:
                return val
        except Exception:
            pass
    return "Segoe UI"


class PhotoTaggerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.configure(fg_color=COLOR_WORKSPACE)
        
        # Window setup
        self.title(f"Photo Tagger v{APP_VERSION}")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        scaling = self._get_window_scaling() if hasattr(self, '_get_window_scaling') else 1.0
        _, _, work_w, work_h = get_system_work_area()
        if work_w is None:
            work_w = self.winfo_screenwidth()
            work_h = self.winfo_screenheight() - 48
        # Fit comfortably inside work area with safe 20px+ margins
        avail_w_logical = int((work_w - 52) / scaling)
        avail_h_logical = int((work_h - 76) / scaling)
        init_w = min(960, max(680, min(818, avail_w_logical)))
        init_h = min(600, max(360, min(390, avail_h_logical)))
        self.init_logical_w = init_w
        self.init_logical_h = init_h
        self.geometry(f"{init_w}x{init_h}+8+4")
        self.minsize(680, 360)
        self.lift()
        self.attributes('-topmost', True)
        self.after(500, lambda: self.attributes('-topmost', False))
        self.focus_force()
        
        # State management
        self.current_image_path = None
        self.image_list = []
        self.current_image_idx = -1
        
        # Bounding boxes: list of dicts: {'name': '...', 'x': cx, 'y': cy, 'w': nw, 'h': nh}
        self.faces = []
        self.description = ""
        self.is_modified = False
        
        # Hover and Selection state
        self.hovered_face_idx = None
        self.selected_face_idx = None
        self.mouse_in_canvas = False
        
        # Canvas display/scale cache
        self.original_pil_image = None
        self.tk_image = None  # Reference to prevent garbage collection
        self.scale = 1.0
        self.pad_x = 0
        self.pad_y = 0
        self.disp_w = 0
        self.disp_h = 0
        
        # Zoom & Pan state
        self.zoom_factor = 1.0
        self.view_center_x = 0.5
        self.view_center_y = 0.5
        self.pan_start_x = 0
        self.pan_start_y = 0
        self.is_pan_mode = False
        
        # Drawing boxes state
        self.drawing = False
        self.draw_start_x = 0
        self.draw_start_y = 0
        self.draw_current_x = 0
        self.draw_current_y = 0
        
        # Resizing and styling state (v2.2)
        self.resizing = False
        self.resize_handle = None
        self.resize_start_x = 0
        self.resize_start_y = 0
        self.resize_face_init = None
        self.hovered_resize_handle = None
        self.drag_rect_id = None

        # Milestone 3 UI Prototype State
        self.active_workspace_mode = "tagging"   # "tagging", "layout", "preview"
        self.active_tool_mode = "select"         # "select", "add_face", "pan"
        self.dragging_badge_idx = None
        self.is_filmstrip_expanded = False
        self.filmstrip_thumbnails = []
        self.filmstrip_buttons = []
        self.active_inspector_tab = "People"
        self.is_project_dirty = False
        self.is_metadata_dirty = False
        self.render_revision = 0
        self.last_bg_key = None
        self.current_preset = "Classic"
        
        # References for face thumbnails to prevent garbage collection
        self.face_images = []
        self.face_entries = []
        
        # Load brand logo assets & window icon
        self.app_logo_img = None
        self.app_logo_small = None
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(__file__))
        logo_path = os.path.join(base_dir, "app_logo.png")
        if os.path.exists(logo_path):
            try:
                pil_logo = Image.open(logo_path)
                self.app_logo_img = ctk.CTkImage(light_image=pil_logo, dark_image=pil_logo, size=(28, 28))
                self.app_logo_small = ctk.CTkImage(light_image=pil_logo, dark_image=pil_logo, size=(18, 18))
            except Exception as e:
                print("Error loading app logo:", e)
        
        ico_path = os.path.join(base_dir, "app_icon.ico")
        if os.path.exists(ico_path):
            try:
                self.iconbitmap(ico_path)
            except Exception:
                pass
        
        # Load high-craft UI vector icons
        self._load_ui_icons(base_dir)
        
        # Build UI layout
        self.create_layout()
        
        # Bind window closing protocol
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _load_ui_icons(self, base_dir):
        icons_dir = os.path.join(base_dir, "assets", "icons")
        if not os.path.exists(icons_dir):
            try:
                import generate_ui_icons
            except Exception:
                pass

        def load_one(name, size=(22, 22)):
            p = os.path.join(icons_dir, name)
            if os.path.exists(p):
                try:
                    im = Image.open(p)
                    return ctk.CTkImage(light_image=im, dark_image=im, size=size)
                except Exception:
                    return None
            return None

        self.icon_open_photo = load_one("open_photo.png", (20, 20))
        self.icon_open_folder = load_one("open_folder.png", (20, 20))
        self.icon_save = load_one("save.png", (20, 20))
        self.icon_write_tags = load_one("write_tags.png", (20, 20))
        self.icon_export = load_one("export.png", (20, 20))
        self.icon_help = load_one("help.png", (20, 20))
        self.icon_overflow = load_one("overflow.png", (17, 17))
        self.icon_tool_select = load_one("tool_select.png", (15, 15))
        self.icon_tool_add = load_one("tool_add.png", (15, 15))
        self.icon_tool_pan = load_one("tool_pan.png", (15, 15))
        self.icon_undo = load_one("undo.png", (17, 17))
        self.icon_redo = load_one("redo.png", (17, 17))
        self.icon_rotate_left = load_one("rotate_left.png", (22, 22))
        self.icon_rotate_right = load_one("rotate_right.png", (22, 22))
        self.icon_add = load_one("tool_add.png", (17, 17))
        self.icon_minus = load_one("tool_minus.png", (17, 17))
        self.icon_nav_prev = load_one("nav_prev.png", (13, 13))
        self.icon_nav_next = load_one("nav_next.png", (13, 13))
        self.icon_filmstrip = load_one("filmstrip.png", (20, 20))

    def create_layout(self):
        # Configure grid row/col weights
        self.grid_rowconfigure(0, weight=0)  # Row 0: App Brand, File Open & Primary Actions
        self.grid_rowconfigure(1, weight=0)  # Row 1: Photo Identity, Modes, Tools & Zoom
        self.grid_rowconfigure(2, weight=1)  # Row 2: Main Area (Canvas + Sidebar)
        self.grid_rowconfigure(3, weight=0)  # Row 3: Filmstrip Container
        self.grid_rowconfigure(4, weight=0)  # Row 4: Bottom Navigation / Status
        self.grid_columnconfigure(0, weight=1)

        # ----------------------------------------------------
        # 1. Top Bar (Row 0): Brand, Modes, File Open & Primary Actions
        # ----------------------------------------------------
        self.header_frame = ctk.CTkFrame(self, height=42, corner_radius=0, fg_color=COLOR_WORKSPACE, border_width=1, border_color=COLOR_BORDER_SUBTLE)
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=0)

        # Left section: Brand & File Open buttons
        self.header_left = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.header_left.pack(side="left", padx=10, pady=4)

        if hasattr(self, 'app_logo_img') and self.app_logo_img:
            self.lbl_brand_logo = ctk.CTkLabel(self.header_left, image=self.app_logo_img, text="")
            self.lbl_brand_logo.pack(side="left", padx=(0, 6))

        self.lbl_brand_title = ctk.CTkLabel(self.header_left, text="Photo Tagger", font=("Segoe UI", 16, "bold"), text_color=COLOR_TEXT_PRIMARY)
        self.lbl_brand_title.pack(side="left", padx=(0, 6))

        self.lbl_brand_badge = ctk.CTkLabel(
            self.header_left, 
            text=f"v{APP_VERSION}", 
            font=("Segoe UI", 12, "bold"), 
            text_color="#818cf8", 
            fg_color="#1e1b4b", 
            border_width=1,
            border_color="#312e81",
            corner_radius=4, 
            width=84, 
            height=20
        )
        self.lbl_brand_badge.pack(side="left", padx=(0, 8))
        self.lbl_brand_version = self.lbl_brand_badge

        self.btn_open_file = IconLabelButton(
            self.header_left, 
            text="Open Photo", 
            image=self.icon_open_photo,
            compound="left",
            command=self.open_file, 
            width=106, 
            height=34,
            fg_color="transparent", 
            border_width=0, 
            text_color=COLOR_TEXT_PRIMARY, 
            hover_color=COLOR_SURFACE_HOVER, 
            font=("Segoe UI Semibold", 13),
            corner_radius=6
        )
        self.btn_open_file.pack(side="left", padx=2)

        self.btn_open_folder = IconLabelButton(
            self.header_left, 
            text="Open Folder", 
            image=self.icon_open_folder,
            compound="left",
            command=self.open_folder, 
            width=112, 
            height=34,
            fg_color="transparent", 
            border_width=0, 
            text_color=COLOR_TEXT_PRIMARY, 
            hover_color=COLOR_SURFACE_HOVER, 
            font=("Segoe UI Semibold", 13),
            corner_radius=6
        )
        self.btn_open_folder.pack(side="left", padx=2)

        # Right section: Primary Actions (Export Files, Format Selector, Write Tags, Save Project, Overflow & Help)
        # Pack action_frame FIRST (side="right") so primary actions are always guaranteed space and never squeezed
        self.action_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.action_frame.pack(side="right", padx=10, pady=4)

        # Center section: Workspace Mode Switcher (Centered in top header in remaining space)
        self.header_center = ctk.CTkFrame(self.header_frame, width=1, height=1, fg_color="transparent")
        self.header_center.pack(side="left", fill="x", expand=True)

        self.mode_switcher = ctk.CTkSegmentedButton(
            self,
            values=["Tagging", "Layout", "Preview"],
            command=self.on_workspace_mode_changed,
            font=("Segoe UI", 14, "bold"),
            fg_color=COLOR_WORKSPACE,
            border_width=0,
            selected_color=COLOR_WORKSPACE,
            selected_hover_color=COLOR_SURFACE_HOVER,
            unselected_color=COLOR_WORKSPACE,
            unselected_hover_color=COLOR_SURFACE_HOVER,
            height=32,
            width=228
        )
        for i in range(3):
            self.mode_switcher.grid_columnconfigure(i, uniform="mode_tabs", weight=1)
        self.mode_switcher.pack(in_=self.header_center, anchor="center")
        self.mode_switcher.set("Tagging")
        self._mode_switcher_location = "header"

        # Primary Action: Export Files (Dynamic: Solid in Preview, Quiet secondary in Edit modes)
        self.btn_export_annotated = IconLabelButton(
            self.action_frame, 
            text="Export Files", 
            image=self.icon_export,
            compound="left",
            command=self.export_annotated, 
            width=108, 
            height=34,
            fg_color="transparent", 
            hover_color=COLOR_SURFACE_HOVER, 
            text_color=COLOR_TEXT_PRIMARY, 
            border_width=0,
            font=("Segoe UI", 12, "bold"),
            corner_radius=6
        )
        self.btn_export_annotated.pack(side="right", padx=2)

        # Export Format Option Menu (Placed directly beside the Export action it affects)
        self.combo_format = ctk.CTkOptionMenu(
            self.action_frame, 
            values=["Format: Original", "Format: JPEG", "Format: PNG", "Format: WebP"], 
            width=124, 
            height=34,
            font=("Segoe UI Semibold", 13),
            dropdown_fg_color=COLOR_SETTINGS_SURFACE,
            fg_color=COLOR_SETTINGS_SURFACE,
            button_color=COLOR_SURFACE_HOVER,
            button_hover_color="#434c5c",
            text_color=COLOR_TEXT_PRIMARY,
            corner_radius=6
        )
        self.combo_format.set("Format: Original")
        self.combo_format.pack(side="right", padx=2)

        # Neutral Action: Write Tags (Directly writes EXIF/XMP to photo)
        self.btn_write_tags = IconLabelButton(
            self.action_frame, 
            text="Write Tags", 
            image=self.icon_write_tags,
            compound="left",
            command=self.save_current, 
            width=106, 
            height=34,
            fg_color="transparent", 
            hover_color=COLOR_SURFACE_HOVER, 
            border_width=0,
            text_color=COLOR_TEXT_PRIMARY, 
            font=("Segoe UI Semibold", 13),
            corner_radius=6
        )
        self.btn_write_tags.pack(side="right", padx=2)
        self.btn_save = self.btn_write_tags

        # Primary Action: Save Project (Solid accent button in Edit modes)
        self.btn_save_project = IconLabelButton(
            self.action_frame, 
            text="Save Project", 
            image=self.icon_save,
            compound="left",
            command=self.save_project_only, 
            width=108, 
            height=34,
            fg_color=COLOR_ACCENT_PRIMARY, 
            hover_color=COLOR_ACCENT_PRIMARY_HOVER, 
            text_color="#ffffff", 
            font=("Segoe UI", 12, "bold"),
            corner_radius=6
        )
        self.btn_save_project.pack(side="right", padx=2)

        # Grouped Overflow for secondary actions (Open Folder, Help, About)
        self.btn_overflow = ctk.CTkButton(
            self.action_frame,
            text="",
            image=self.icon_overflow,
            command=self.show_overflow_menu,
            width=32,
            height=34,
            fg_color="transparent", 
            hover_color=COLOR_SURFACE_HOVER, 
            border_width=0,
            corner_radius=6
        )
        self.btn_overflow.pack(side="right", padx=2)

        # Help Action Button in Header (Single authoritative Help button in wide view)
        self.btn_help = IconLabelButton(
            self.action_frame,
            text="Help",
            image=self.icon_help,
            compound="left",
            command=self.show_help_dialog,
            width=76, 
            height=34,
            fg_color="transparent", 
            hover_color=COLOR_SURFACE_HOVER, 
            border_width=0,
            text_color=COLOR_TEXT_PRIMARY, 
            font=("Segoe UI Semibold", 13),
            corner_radius=6
        )
        self.btn_help.pack(side="right", padx=2)

        # ----------------------------------------------------
        # 2. Toolbar (Row 1): Photo Breadcrumb, Specs, Tools & Zoom
        # ----------------------------------------------------
        self.toolbar_frame = ctk.CTkFrame(self, height=38, corner_radius=0, fg_color=COLOR_WORKSPACE, border_width=1, border_color=COLOR_BORDER_SUBTLE)
        self.toolbar_frame.grid(row=1, column=0, sticky="ew", padx=0, pady=0)

        # Left section: Photo Identity and Status Indicators
        self.identity_frame = ctk.CTkFrame(self.toolbar_frame, fg_color="transparent")
        self.identity_frame.pack(side="left", padx=10, pady=4)

        self.lbl_photo_identity = ctk.CTkLabel(
            self.identity_frame,
            text="No Photo Loaded",
            font=("Segoe UI", 12, "bold"),
            text_color=COLOR_TEXT_PRIMARY
        )
        self.lbl_photo_identity.pack(side="left", padx=(0, 6))

        self.lbl_identity_sep = ctk.CTkLabel(
            self.identity_frame,
            text="/",
            font=("Segoe UI", 12),
            text_color=COLOR_TEXT_MUTED
        )
        self.lbl_identity_sep.pack(side="left", padx=(0, 6))

        self.pill_project_status = ctk.CTkLabel(
            self.identity_frame,
            text="● Saved",
            font=("Segoe UI", 12, "bold"),
            text_color=COLOR_STATUS_SAVED,
            fg_color="transparent",
            padx=4,
            pady=2
        )
        self.pill_project_status.pack(side="left", padx=2)

        self.pill_metadata_status = ctk.CTkLabel(
            self.identity_frame,
            text="✓ Tags synced",
            font=("Segoe UI", 12, "bold"),
            text_color=COLOR_STATUS_SYNCED,
            fg_color="transparent",
            padx=4,
            pady=2
        )
        self.pill_metadata_status.pack(side="left", padx=2)

        # Right section: Technical Specs & Tool Switcher
        self.tool_zoom_frame = ctk.CTkFrame(self.toolbar_frame, fg_color="transparent")
        self.tool_zoom_frame.pack(side="right", padx=10, pady=4)

        # Photo Metadata Specs readout (e.g. 2400 × 3000 px • 84 KB • 300 DPI)
        self.lbl_photo_metadata = ctk.CTkLabel(
            self.tool_zoom_frame,
            text="",
            font=("Segoe UI", 12),
            text_color="#94A3B8"
        )
        if getattr(self, 'init_logical_w', 818) >= 1180:
            self.lbl_photo_metadata.pack(side="left", padx=(0, 12))

        self.tool_switcher = ctk.CTkSegmentedButton(
            self.tool_zoom_frame,
            values=["Select", "Add Tag", "Pan"],
            command=self.on_tool_mode_changed,
            font=("Segoe UI", 12, "bold"),
            fg_color=COLOR_WORKSPACE,
            border_width=0,
            selected_color=COLOR_SURFACE_HOVER,
            selected_hover_color="#434c5c",
            unselected_color=COLOR_WORKSPACE,
            unselected_hover_color=COLOR_SURFACE_HOVER,
            width=192,
            height=26
        )
        for i in range(3):
            self.tool_switcher.grid_columnconfigure(i, uniform="tool_tabs", weight=1)
        self.tool_switcher.pack(side="left", padx=2)
        self.tool_switcher.set("Select")

        # Honestly labeled disabled prototype controls
        self.btn_undo = ctk.CTkButton(
            self.tool_zoom_frame, 
            text="", 
            image=self.icon_undo,
            command=self.on_undo,
            width=28, 
            height=26,
            fg_color="transparent", 
            hover_color=COLOR_WORKSPACE, 
            text_color=COLOR_TEXT_MUTED,
            border_width=0,
            state="disabled",
            corner_radius=4
        )

        self.btn_redo = ctk.CTkButton(
            self.tool_zoom_frame, 
            text="", 
            image=self.icon_redo,
            command=self.on_redo,
            width=28, 
            height=26,
            fg_color="transparent", 
            hover_color=COLOR_WORKSPACE, 
            text_color=COLOR_TEXT_MUTED,
            border_width=0,
            state="disabled",
            corner_radius=4
        )

        # Rotate Left and Rotate Right controls (Windows-style pale landscape thumbnail with blue quarter-turn arrow)
        self.btn_rotate_left = IconLabelButton(
            self.tool_zoom_frame,
            text="L",
            compound="left",
            font=("Segoe UI", 12, "bold"),
            text_color=COLOR_TEXT_PRIMARY,
            image=self.icon_rotate_left,
            command=lambda: self.rotate_photo("left"),
            width=45,
            height=26,
            fg_color="transparent",
            hover_color=COLOR_SURFACE_HOVER,
            border_width=0,
            corner_radius=4
        )
        self.btn_rotate_left.pack(side="left", padx=1)

        self.btn_rotate_right = IconLabelButton(
            self.tool_zoom_frame,
            text="R",
            compound="left",
            font=("Segoe UI", 12, "bold"),
            text_color=COLOR_TEXT_PRIMARY,
            image=self.icon_rotate_right,
            command=lambda: self.rotate_photo("right"),
            width=45,
            height=26,
            fg_color="transparent",
            hover_color=COLOR_SURFACE_HOVER,
            border_width=0,
            corner_radius=4
        )
        self.btn_rotate_right.pack(side="left", padx=(1, 2))

        # Center section: Workspace Mode Switcher container for compact responsive reflow
        self.toolbar_center = ctk.CTkFrame(self.toolbar_frame, width=1, height=1, fg_color="transparent")
        self.toolbar_center.pack(side="left", fill="x", expand=True, padx=4)

        # ----------------------------------------------------
        # 3. Main Split (Left: Dominant Canvas, Right: Resizable Inspector)
        # ----------------------------------------------------
        self.main_split = tk.PanedWindow(self, orient=tk.HORIZONTAL, bd=0, sashwidth=6, sashrelief="flat", bg=COLOR_PHOTO_MATTE)
        self.main_split.grid(row=2, column=0, sticky="nsew", padx=10, pady=6)

        # Left: Canvas Container
        self.canvas_container = ctk.CTkFrame(self.main_split, corner_radius=8, fg_color=COLOR_PHOTO_MATTE, border_width=1, border_color=COLOR_BORDER_SUBTLE)
        self.canvas_container.grid_rowconfigure(0, weight=1)
        self.canvas_container.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self.canvas_container, bg=COLOR_PHOTO_MATTE, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        # Persistent floating zoom & fit overlay in canvas bottom-right
        self.canvas_zoom_pill = ctk.CTkFrame(self.canvas_container, fg_color=COLOR_WORKSPACE, corner_radius=8, border_width=1, border_color=COLOR_BORDER_SUBTLE)
        self.canvas_zoom_pill.place(relx=1, rely=1, x=-16, y=-16, anchor="se")
        
        def zoom_icon(kind):
            art = Image.new("RGBA", (88, 88))
            draw = ImageDraw.Draw(art)
            silver, blue = "#DDE7F3", "#65B7FF"
            if kind == "fit":
                for x, y, dx, dy in ((14, 14, 1, 1), (74, 14, -1, 1),
                                      (14, 74, 1, -1), (74, 74, -1, -1)):
                    draw.line(((x, y + 18 * dy), (x, y), (x + 18 * dx, y)),
                              fill=blue, width=7)
                draw.rectangle((33, 34, 55, 54), outline=silver, width=5)
            else:
                draw.line((54, 54, 76, 76), fill=silver, width=9)
                draw.ellipse((9, 9, 62, 62), outline=silver, width=7)
                draw.line((23, 35, 48, 35), fill=blue, width=7)
                if kind == "in":
                    draw.line((35, 23, 35, 48), fill=blue, width=7)
            return ctk.CTkImage(light_image=art, dark_image=art, size=(22, 22))

        self.c_btn_zoom_out = ctk.CTkButton(self.canvas_zoom_pill, text="", image=zoom_icon("out"), command=self.zoom_out, width=30, height=30, fg_color="transparent", hover_color=COLOR_SURFACE_HOVER, corner_radius=6)
        self.c_btn_zoom_out.pack(side="left", padx=2, pady=2)
        
        self.c_lbl_zoom = ctk.CTkLabel(self.canvas_zoom_pill, text="100%", font=("Segoe UI", 12, "bold"), text_color=COLOR_TEXT_PRIMARY, width=42)
        self.c_lbl_zoom.pack(side="left", padx=1, pady=2)
        
        self.c_btn_zoom_in = ctk.CTkButton(self.canvas_zoom_pill, text="", image=zoom_icon("in"), command=self.zoom_in, width=30, height=30, fg_color="transparent", hover_color=COLOR_SURFACE_HOVER, corner_radius=6)
        self.c_btn_zoom_in.pack(side="left", padx=2, pady=2)
        
        self.c_btn_fit = IconLabelButton(self.canvas_zoom_pill, text="Fit", image=zoom_icon("fit"), compound="left", command=self.zoom_reset, width=58, height=30, font=("Segoe UI Semibold", 13), fg_color="transparent", hover_color=COLOR_SURFACE_HOVER, text_color=COLOR_TEXT_SECONDARY, corner_radius=6)
        self.c_btn_fit.pack(side="left", padx=(1, 2), pady=2)

        # Map canonical zoom control attributes directly to persistent floating canvas controls
        self.btn_zoom_out = self.c_btn_zoom_out
        self.lbl_zoom_level = self.c_lbl_zoom
        self.btn_zoom_in = self.c_btn_zoom_in
        self.btn_zoom_reset = self.c_btn_fit
        self.btn_pan_mode = self.c_btn_fit

        self.canvas.bind("<Configure>", self.on_canvas_resize)
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<Motion>", self.on_canvas_motion)
        self.canvas.bind("<Leave>", self.on_canvas_leave)
        self.canvas.bind("<ButtonPress-3>", self.on_pan_press)
        self.canvas.bind("<B3-Motion>", self.on_pan_drag)
        self.canvas.bind("<ButtonRelease-3>", self.on_pan_release)
        self.canvas.bind("<MouseWheel>", self.on_mouse_zoom)
        self.canvas.bind("<Button-4>", lambda event: self.on_mouse_zoom_linux(event, True))
        self.canvas.bind("<Button-5>", lambda event: self.on_mouse_zoom_linux(event, False))

        # Right: Resizable / Tabbed Inspector Sidebar
        self.sidebar_frame = ctk.CTkFrame(self.main_split, corner_radius=8, width=340, fg_color=COLOR_SETTINGS_SURFACE, border_width=1, border_color=COLOR_BORDER_SUBTLE)
        self.sidebar_frame.grid_propagate(False)

        self.main_split.add(self.canvas_container, minsize=350, stretch="always")
        self.main_split.add(self.sidebar_frame, minsize=320, stretch="never", width=380)

        # Attach accessible tooltips to icon-only and primary action controls
        self.setup_tooltips()

        # Keyboard shortcuts and navigation alternatives
        self.setup_keyboard_shortcuts()

        # Bind responsive window configure handler
        self.bind("<Configure>", self.on_window_configure, add="+")

        # Inspector Tabs Switcher
        self.inspector_tab_segmented = ctk.CTkSegmentedButton(
            self.sidebar_frame,
            values=["People", "Details", "Appearance"],
            command=self.on_inspector_tab_changed,
            font=("Segoe UI", 12, "bold"),
            fg_color=COLOR_SETTINGS_SURFACE,
            border_width=0,
            selected_color=COLOR_SETTINGS_SURFACE,
            selected_hover_color=COLOR_SURFACE_HOVER,
            unselected_color=COLOR_SETTINGS_SURFACE,
            unselected_hover_color=COLOR_SURFACE_HOVER,
            height=30
        )
        for i in range(3):
            self.inspector_tab_segmented.grid_columnconfigure(i, uniform="inspector_tabs", weight=1)
        self.inspector_tab_segmented.pack(fill="x", padx=10, pady=(10, 6))
        self.inspector_tab_segmented.set("People")

        # Container for Tab Views
        self.tab_container = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.tab_container.pack(fill="both", expand=True, padx=6, pady=4)

        # Tab 1: People Tab Frame
        self.tab_people_frame = ctk.CTkFrame(self.tab_container, fg_color="transparent")
        self.tab_people_frame.pack(fill="both", expand=True)

        self.people_header_frame = ctk.CTkFrame(self.tab_people_frame, fg_color="transparent")
        self.people_header_frame.pack(fill="x", padx=4, pady=(2, 6))

        self.faces_header = ctk.CTkLabel(self.people_header_frame, text="People", font=("Segoe UI", 14, "bold"), text_color=COLOR_TEXT_PRIMARY)
        self.faces_header.pack(side="left", padx=4)

        self.btn_clear_tags = ctk.CTkButton(
            self.people_header_frame,
            text="✕ Clear",
            command=self.clear_all_tags,
            width=64,
            height=30,
            fg_color="transparent",
            border_width=0,
            border_color="#f38ba8",
            text_color="#f38ba8",
            hover_color=COLOR_SURFACE_HOVER,
            font=("Segoe UI Semibold", 13),
            corner_radius=6
        )
        self.btn_clear_tags.pack(side="right", padx=2)

        self.btn_redetect = ctk.CTkButton(
            self.people_header_frame,
            text="Detect",
            command=self.redetect_faces,
            width=64,
            height=30,
            fg_color="transparent",
            border_width=0,
            border_color="#89b4fa",
            text_color="#89b4fa",
            hover_color=COLOR_SURFACE_HOVER,
            font=("Segoe UI Semibold", 13),
            corner_radius=6
        )
        self.btn_redetect.pack(side="right", padx=2)

        self.faces_scroll = ctk.CTkScrollableFrame(self.tab_people_frame, fg_color="transparent")
        self.faces_scroll.pack(fill="both", expand=True, padx=2, pady=2)

        # Quick Instructions Card in People Tab
        self.instr_card = ctk.CTkFrame(self.tab_people_frame, fg_color=COLOR_WORKSPACE, corner_radius=6, border_width=1, border_color=COLOR_BORDER_SUBTLE)
        self.instr_card.pack(fill="x", padx=4, pady=(4, 2))

        self.instr_header_frame = ctk.CTkFrame(self.instr_card, fg_color="transparent")
        self.instr_header_frame.pack(fill="x", padx=6, pady=4)

        self.instr_title = ctk.CTkLabel(self.instr_header_frame, text="ℹ️ Quick Instructions", font=("Segoe UI", 12, "bold"), text_color="#89b4fa")
        self.instr_title.pack(side="left", padx=2)

        self.btn_toggle_instr = ctk.CTkButton(
            self.instr_header_frame, 
            text="▼ Expand", 
            width=60, 
            height=20, 
            font=("Segoe UI", 10, "bold"), 
            fg_color=COLOR_SURFACE_HOVER, 
            hover_color="#45475a", 
            text_color=COLOR_TEXT_PRIMARY,
            corner_radius=4,
            command=self.toggle_instructions
        )
        self.btn_toggle_instr.pack(side="right", padx=2)

        instr_text = (
            "• Tagging: Click and drag to add face box.\n"
            "• Naming: Type names in cards above.\n"
            "• Layout: Switch to Layout mode to drag badges.\n"
            "• Persistence: Save Project writes sidecar only.\n"
            "• Photo Safe: Image bytes are never modified by project saves."
        )
        self.instr_desc = ctk.CTkLabel(self.instr_card, text=instr_text, font=("Segoe UI", 12), justify="left", text_color="#a6adc8")
        self.instr_expanded = False

        # Tab 2: Photo Details Tab Frame
        self.tab_details_frame = ctk.CTkScrollableFrame(self.tab_container, fg_color="transparent")

        self.details_info_card = ctk.CTkFrame(self.tab_details_frame, fg_color=COLOR_WORKSPACE, corner_radius=6, border_width=1, border_color=COLOR_BORDER_SUBTLE)
        self.details_info_card.pack(fill="x", padx=4, pady=4)

        self.lbl_detail_filename = ctk.CTkLabel(self.details_info_card, text="File: (No photo)", font=("Segoe UI", 13, "bold"), text_color=COLOR_TEXT_PRIMARY, anchor="w")
        self.lbl_detail_filename.pack(fill="x", padx=8, pady=(6, 2))

        self.lbl_detail_dimensions = ctk.CTkLabel(self.details_info_card, text="Dimensions: -", font=("Segoe UI", 12), text_color="#a6adc8", anchor="w")
        self.lbl_detail_dimensions.pack(fill="x", padx=8, pady=1)

        self.lbl_detail_size = ctk.CTkLabel(self.details_info_card, text="Disk Size: -", font=("Segoe UI", 12), text_color="#a6adc8", anchor="w")
        self.lbl_detail_size.pack(fill="x", padx=8, pady=(1, 6))

        # Description Header & Input Box
        self.desc_label = ctk.CTkLabel(self.tab_details_frame, text="General Photo Description", font=("Segoe UI", 14, "bold"), text_color=COLOR_TEXT_PRIMARY, anchor="w")
        self.desc_label.pack(fill="x", padx=6, pady=(6, 2))

        self.desc_textbox = ctk.CTkTextbox(
            self.tab_details_frame, 
            height=70, 
            corner_radius=6, 
            border_width=1, 
            border_color=COLOR_BORDER_SUBTLE,
            fg_color=COLOR_PHOTO_MATTE,
            text_color=COLOR_TEXT_PRIMARY
        )
        self.desc_textbox.pack(fill="x", padx=4, pady=(0, 8))
        self.desc_textbox.bind("<KeyRelease>", self.on_description_changed)

        # Safe Preview Restriction Advisory Card
        self.advisory_card = ctk.CTkFrame(self.tab_details_frame, fg_color=COLOR_WORKSPACE, corner_radius=6, border_width=1, border_color=COLOR_BORDER_SUBTLE)
        self.advisory_card.pack(fill="x", padx=4, pady=4)

        self.lbl_advisory_title = ctk.CTkLabel(self.advisory_card, text="🛡️ Safe Preview Active", font=("Segoe UI", 13, "bold"), text_color="#89b4fa", anchor="w")
        self.lbl_advisory_title.pack(fill="x", padx=10, pady=(6, 2))

        advisory_msg = (
            "Format conversion overwrite is disabled for data integrity. "
            "Destination files must not already exist on disk."
        )
        self.lbl_advisory_text = ctk.CTkLabel(self.advisory_card, text=advisory_msg, font=("Segoe UI", 12), justify="left", anchor="w", text_color="#a6adc8", wraplength=180)
        self.lbl_advisory_text.pack(fill="x", padx=10, pady=(0, 6))

        def _on_advisory_card_resize(event):
            if hasattr(self, 'lbl_advisory_text') and self.lbl_advisory_text.winfo_exists():
                wrap_w = max(1, int(self.lbl_advisory_text._reverse_widget_scaling(event.width)) - 20)
                self.lbl_advisory_text.configure(wraplength=wrap_w)

        self.advisory_card.bind("<Configure>", _on_advisory_card_resize)

        # Write Tags Button in Details Tab (Retired in favor of authoritative top action)
        self.btn_write_tags_tab = ctk.CTkButton(
            self.tab_details_frame,
            text="Write Tags to Photo (EXIF/XMP)",
            image=self.icon_write_tags,
            compound="left",
            command=self.save_current,
            height=32,
            fg_color="#4f46e5",
            hover_color="#4338ca",
            text_color="#ffffff",
            font=("Segoe UI", 13, "bold"),
            corner_radius=6
        )
        # self.btn_write_tags_tab is retired from UI to avoid duplicate actions

        # Tab 3: Appearance Tab Frame
        self.tab_appearance_frame = ctk.CTkScrollableFrame(self.tab_container, fg_color="transparent")

        self.appearance_card = ctk.CTkFrame(self.tab_appearance_frame, fg_color=COLOR_WORKSPACE, corner_radius=8, border_width=1, border_color=COLOR_BORDER_SUBTLE)
        self.appearance_card.pack(fill="x", padx=4, pady=4)

        # Section 1: Preset & Palette
        self.lbl_sec_style = ctk.CTkLabel(
            self.appearance_card,
            text="Preset & Palette",
            font=("Segoe UI", 14, "bold"),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w"
        )
        self.lbl_sec_style.pack(fill="x", padx=10, pady=(10, 4))

        self.lbl_preset = ctk.CTkLabel(
            self.appearance_card,
            text="Preset Profile",
            font=("Segoe UI", 13),
            text_color="#cbd5e1",
            anchor="w"
        )
        self.lbl_preset.pack(fill="x", padx=10, pady=(2, 2))

        self.combo_preset = ctk.CTkComboBox(
            self.appearance_card,
            values=["Single Outline", "Classic", "Borderless", "Minimal", "High Contrast", "Print"],
            font=("Segoe UI", 13),
            command=self.on_preset_changed,
            dropdown_fg_color=COLOR_SETTINGS_SURFACE,
            fg_color=COLOR_PHOTO_MATTE,
            border_width=1,
            border_color=COLOR_BORDER_SUBTLE,
            corner_radius=6,
            height=32
        )
        self.combo_preset.pack(fill="x", padx=10, pady=(0, 6))
        self.combo_preset.set("Classic")

        # Color Accent Header
        self.lbl_style_color = ctk.CTkLabel(
            self.appearance_card,
            text="Tag Color Accent (Teal)",
            font=("Segoe UI", 13),
            text_color="#cbd5e1",
            anchor="w"
        )
        self.lbl_style_color.pack(fill="x", padx=10, pady=(2, 2))

        # Full Range of 8 Accent Color Swatches: Teal, Blue, Purple, Green, Red, Yellow, White, Black
        self.swatches_frame = ctk.CTkFrame(self.appearance_card, fg_color="transparent")
        self.swatches_frame.pack(anchor="center", pady=(4, 10))

        self.swatch_defs = [
            ("Teal", CANONICAL_PALETTE["Teal"]["hex"], CANONICAL_PALETTE["Teal"]["hover_hex"]),
            ("Blue", CANONICAL_PALETTE["Blue"]["hex"], CANONICAL_PALETTE["Blue"]["hover_hex"]),
            ("Purple", CANONICAL_PALETTE["Purple"]["hex"], CANONICAL_PALETTE["Purple"]["hover_hex"]),
            ("Green", CANONICAL_PALETTE["Green"]["hex"], CANONICAL_PALETTE["Green"]["hover_hex"]),
            ("Orange/Red", CANONICAL_PALETTE["Orange/Red"]["hex"], CANONICAL_PALETTE["Orange/Red"]["hover_hex"]),
            ("Yellow", CANONICAL_PALETTE["Yellow"]["hex"], CANONICAL_PALETTE["Yellow"]["hover_hex"]),
            ("White", CANONICAL_PALETTE["White"]["hex"], CANONICAL_PALETTE["White"]["hover_hex"]),
            ("Black", CANONICAL_PALETTE["Black"]["hex"], CANONICAL_PALETTE["Black"]["hover_hex"]),
        ]
        self.swatch_buttons = {}
        for name, col, hover_col in self.swatch_defs:
            btn = ctk.CTkButton(
                self.swatches_frame,
                text="",
                fg_color=col,
                hover_color=hover_col,
                width=22,
                height=22,
                corner_radius=11,
                font=("Segoe UI", 13, "bold"),
                border_width=2 if name == "Teal" else (1 if name == "White" else 0),
                border_color="#ffffff" if name == "Teal" else ("#64748b" if name == "White" else col),
                command=lambda n=name: self.on_swatch_clicked(n)
            )
            btn.grid_propagate(False)
            btn.pack(side="left", padx=1.5)
            WidgetTooltip(btn, name)
            self.swatch_buttons[name] = btn

        # Retain combo_style_color in memory for programmatic access and backwards compatibility
        self.combo_style_color = ctk.CTkComboBox(
            self.appearance_card, 
            values=["Teal", "Blue", "Purple", "Green", "Orange/Red", "Yellow", "White", "Black"], 
            height=26,
            font=("Segoe UI", 13),
            dropdown_fg_color=COLOR_SETTINGS_SURFACE,
            fg_color=COLOR_PHOTO_MATTE,
            border_width=1,
            border_color=COLOR_BORDER_SUBTLE,
            corner_radius=6,
            command=self.on_style_changed
        )
        self.combo_style_color.set("Teal")

        # Section 2: Badge Geometry
        self.lbl_sec_geom = ctk.CTkLabel(
            self.appearance_card,
            text="Badge Geometry",
            font=("Segoe UI", 14, "bold"),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w"
        )
        self.lbl_sec_geom.pack(fill="x", padx=10, pady=(14, 4))

        # Badge Scale Header with live numeric readout
        self.scale_header_frame = ctk.CTkFrame(self.appearance_card, fg_color="transparent")
        self.scale_header_frame.pack(fill="x", padx=10, pady=(1, 1))

        self.lbl_scale_title = ctk.CTkLabel(
            self.scale_header_frame,
            text="Badge Scale",
            font=("Segoe UI", 13),
            text_color="#cbd5e1"
        )
        self.lbl_scale_title.pack(side="left")

        self.lbl_scale_value = ctk.CTkLabel(
            self.scale_header_frame,
            text="1.00x",
            font=("Segoe UI Semibold", 13),
            text_color="#818cf8"
        )
        self.lbl_scale_value.pack(side="right")

        self.slider_badge_scale = ctk.CTkSlider(
            self.appearance_card,
            from_=0.5,
            to=2.0,
            number_of_steps=150,
            command=self.on_scale_slider_changed,
            progress_color=COLOR_ACCENT_PRIMARY,
            button_color="#818cf8",
            button_hover_color="#a5b4fc",
            fg_color=COLOR_BORDER_SUBTLE,
            height=16
        )
        self.slider_badge_scale.pack(fill="x", padx=10, pady=(1, 4))
        self.slider_badge_scale.set(1.0)

        # Retain combo_style_font_size in memory for programmatic test access
        self.combo_style_font_size = ctk.CTkComboBox(
            self.appearance_card, 
            values=["Micro (0.5x)", "Small (0.7x)", "Auto (1.0x)", "Medium (1.2x)", "Large (1.5x)", "X-Large (2.0x)"], 
            height=26,
            font=("Segoe UI", 13),
            dropdown_fg_color=COLOR_SETTINGS_SURFACE,
            fg_color=COLOR_PHOTO_MATTE,
            border_width=1,
            border_color=COLOR_BORDER_SUBTLE,
            corner_radius=6,
            command=self.on_style_changed
        )
        self.combo_style_font_size.set("Auto (1.0x)")

        # Corner Geometry
        self.lbl_badge_shape = ctk.CTkLabel(
            self.appearance_card,
            text="Corner Geometry",
            font=("Segoe UI", 14, "bold"),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w"
        )
        self.lbl_badge_shape.pack(fill="x", padx=10, pady=(12, 4))

        self.seg_badge_shape = ctk.CTkSegmentedButton(
            self.appearance_card,
            values=["Square", "Pill", "Rounded"],
            font=("Segoe UI Semibold", 13),
            fg_color=COLOR_SETTINGS_SURFACE,
            border_width=0,
            selected_color=COLOR_SURFACE_HOVER,
            selected_hover_color="#434c5c",
            unselected_color=COLOR_SETTINGS_SURFACE,
            unselected_hover_color=COLOR_SURFACE_HOVER,
            height=46,
            command=self.on_seg_shape_changed
        )
        for i in range(3):
            self.seg_badge_shape.grid_columnconfigure(i, uniform="shape_tabs", weight=1)
        for name, bounds, radius in (
            ("Square", (14, 6, 66, 58), 0),
            ("Pill", (4, 14, 76, 50), 18),
            ("Rounded", (14, 6, 66, 58), 13),
        ):
            glyph = Image.new("RGBA", (80, 64))
            ImageDraw.Draw(glyph).rounded_rectangle(
                bounds, radius=radius, fill="#353D4A", outline="#9AC7FF", width=5
            )
            icon = ctk.CTkImage(light_image=glyph, dark_image=glyph, size=(20, 16))
            self.seg_badge_shape._buttons_dict[name].configure(image=icon, compound="top")
        self.seg_badge_shape.pack(fill="x", padx=10, pady=(0, 4))
        self.seg_badge_shape.set("Pill")

        # Retain combo_badge_shape in memory for existing test suite compatibility
        self.combo_badge_shape = ctk.CTkComboBox(
            self.appearance_card,
            values=["Auto Pill/Circle", "Rounded Square", "Square"],
            height=26,
            font=("Segoe UI", 13),
            dropdown_fg_color=COLOR_SETTINGS_SURFACE,
            fg_color=COLOR_PHOTO_MATTE,
            border_width=1,
            border_color=COLOR_BORDER_SUBTLE,
            corner_radius=6,
            command=self.on_shape_changed
        )
        self.combo_badge_shape.set("Auto Pill/Circle")

        # Live Visual Badge Shape Preview Card
        self.badge_preview_frame = ctk.CTkFrame(self.appearance_card, fg_color=COLOR_PHOTO_MATTE, corner_radius=6, border_width=1, border_color=COLOR_BORDER_SUBTLE, height=34)
        self.badge_preview_frame.pack(fill="x", padx=10, pady=(0, 6))
        self.badge_preview_canvas = tk.Canvas(self.badge_preview_frame, bg=COLOR_PHOTO_MATTE, highlightthickness=0, height=42)
        self.badge_preview_canvas.pack(fill="both", expand=True, padx=4, pady=2)
        self.badge_preview_canvas.bind("<Configure>", lambda e: self.update_badge_shape_preview())

        # Section 3: Tag Typography
        self.lbl_sec_font = ctk.CTkLabel(
            self.appearance_card,
            text="Tag Typography",
            font=("Segoe UI", 14, "bold"),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w"
        )
        self.lbl_sec_font.pack(fill="x", padx=10, pady=(14, 4))

        self.lbl_tag_font = ctk.CTkLabel(
            self.appearance_card,
            text="Tag Font Family",
            font=("Segoe UI", 13),
            text_color="#cbd5e1",
            anchor="w"
        )
        self.lbl_tag_font.pack(fill="x", padx=10, pady=(2, 1))

        self.seg_tag_font = ctk.CTkSegmentedButton(
            self.appearance_card,
            values=["Segoe UI", "Tahoma", "Arial"],
            font=("Segoe UI Semibold", 13),
            fg_color=COLOR_SETTINGS_SURFACE,
            border_width=0,
            selected_color=COLOR_SURFACE_HOVER,
            selected_hover_color="#434c5c",
            unselected_color=COLOR_SETTINGS_SURFACE,
            unselected_hover_color=COLOR_SURFACE_HOVER,
            height=30,
            command=self.on_tag_font_changed
        )
        for i in range(3):
            self.seg_tag_font.grid_columnconfigure(i, uniform="font_tabs", weight=1)
        self.seg_tag_font.pack(fill="x", padx=10, pady=(0, 4))
        self.seg_tag_font.set("Segoe UI")

        # Retain combo_tag_font in memory for compatibility/testing
        self.combo_tag_font = ctk.CTkComboBox(
            self.appearance_card,
            values=["Segoe UI", "Tahoma", "Arial"],
            height=26,
            font=("Segoe UI", 13),
            dropdown_fg_color=COLOR_SETTINGS_SURFACE,
            fg_color=COLOR_PHOTO_MATTE,
            border_width=1,
            border_color=COLOR_BORDER_SUBTLE,
            corner_radius=6,
            command=self.on_tag_font_changed
        )
        self.combo_tag_font.set("Segoe UI")

        # Live Font Preview Box showing English, Persian, and digits
        self.font_preview_frame = ctk.CTkFrame(self.appearance_card, fg_color=COLOR_PHOTO_MATTE, corner_radius=6, border_width=1, border_color=COLOR_BORDER_SUBTLE)
        self.font_preview_frame.pack(fill="x", padx=10, pady=(1, 8))

        self.lbl_font_sample = ctk.CTkLabel(
            self.font_preview_frame,
            text="12 • دکتر مریم (Dr. Maryam)",
            font=("Segoe UI", 13),
            text_color="#e2e8f0",
            anchor="center"
        )
        self.lbl_font_sample.pack(fill="x", padx=6, pady=7)

        # Reset Positions Button
        self.btn_reset_badges = ctk.CTkButton(
            self.tab_appearance_frame,
            text="Reset Tag Positions",
            command=self.reset_positions,
            height=32,
            fg_color="transparent",
            hover_color=COLOR_SURFACE_HOVER,
            border_width=1,
            border_color=COLOR_BORDER_SUBTLE,
            text_color=COLOR_TEXT_PRIMARY,
            font=("Segoe UI Semibold", 13),
            corner_radius=6
        )
        self.btn_reset_badges.pack(fill="x", padx=4, pady=(4, 2))

        # Dedicated Editor Window (Retired from UI: Layout mode on main canvas supports all editing tasks)
        self.btn_finetune_2b = ctk.CTkButton(
            self.tab_appearance_frame,
            text="✏️ Dedicated Editor Window",
            command=self.open_editor_2b,
            height=32,
            fg_color="transparent",
            border_width=1,
            border_color="#4f46e5",
            text_color="#818cf8",
            hover_color="#1e2230",
            font=("Segoe UI Semibold", 13),
            corner_radius=6
        )
        # self.btn_finetune_2b is retired from UI in favor of main canvas Layout mode

        # ----------------------------------------------------
        # 4. Collapsible Filmstrip Bar
        # ----------------------------------------------------
        self.filmstrip_frame = ctk.CTkFrame(self, height=95, corner_radius=0, fg_color="#181825", border_width=1, border_color=COLOR_BORDER_SUBTLE)
        self.filmstrip_frame.grid(row=3, column=0, sticky="ew", padx=0, pady=0)
        self.filmstrip_scroll = ctk.CTkScrollableFrame(self.filmstrip_frame, orientation="horizontal", height=85, fg_color=COLOR_PHOTO_MATTE)
        self.filmstrip_scroll.pack(fill="both", expand=True, padx=4, pady=4)
        # Hidden by default
        self.filmstrip_frame.grid_remove()

        # ----------------------------------------------------
        # 5. Bottom Navigation & Status Bar
        # ----------------------------------------------------
        self.bottom_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=COLOR_WORKSPACE, border_width=1, border_color=COLOR_BORDER_SUBTLE)
        self.bottom_frame.grid(row=4, column=0, sticky="ew", padx=0, pady=0)

        # Primary Navigation and Status Row
        self.bottom_nav_status = ctk.CTkFrame(self.bottom_frame, fg_color="transparent")
        self.bottom_nav_status.pack(fill="x", side="top", padx=0, pady=(2, 0))

        # Navigation Controls in Left container
        self.bottom_left = ctk.CTkFrame(self.bottom_nav_status, fg_color="transparent")
        self.bottom_left.pack(side="left", padx=10, pady=(1, 1))

        # Distinct Filmstrip Toggle on the left as in mockup
        self.btn_toggle_filmstrip = IconLabelButton(
            self.bottom_left,
            text="Filmstrip (0)",
            image=self.icon_filmstrip,
            compound="left",
            command=self.toggle_filmstrip,
            width=104,
            height=32,
            font=("Segoe UI Semibold", 13),
            fg_color="transparent",
            hover_color=COLOR_SURFACE_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            corner_radius=6,
            border_width=0
        )
        self.btn_toggle_filmstrip.pack(side="left", padx=(0, 8))

        # Unified Nav Group: < | Counter | >
        self.nav_group = ctk.CTkFrame(self.bottom_left, fg_color=COLOR_SETTINGS_SURFACE, corner_radius=6, border_width=1, border_color=COLOR_BORDER_SUBTLE, height=28)
        self.nav_group.pack(side="left", padx=0)

        self.btn_prev = ctk.CTkButton(self.nav_group, text="", image=self.icon_nav_prev, command=self.prev_image, width=26, height=26, fg_color="transparent", hover_color="#1e2230", corner_radius=4)
        self.btn_prev.pack(side="left", padx=1, pady=1)

        self.lbl_counter = ctk.CTkLabel(self.nav_group, text="No Photos Loaded", font=("Segoe UI", 12), text_color="#cbd5e1", width=110)
        self.lbl_counter.pack(side="left", padx=4, pady=1)

        self.btn_next = ctk.CTkButton(self.nav_group, text="", image=self.icon_nav_next, command=self.next_image, width=26, height=26, fg_color="transparent", hover_color="#1e2230", corner_radius=4)
        self.btn_next.pack(side="left", padx=1, pady=1)

        # Status Label and Indicator Dot in Right container
        self.bottom_right = ctk.CTkFrame(self.bottom_nav_status, fg_color="transparent")
        self.bottom_right.pack(side="right", padx=10, pady=(1, 1))

        self.lbl_status = ctk.CTkLabel(self.bottom_right, text="Ready — open a photo or folder to begin.", font=("Segoe UI", 12), text_color="#94a3b8", anchor="e")
        self.lbl_status.pack(side="right", padx=(4, 0))

        self.lbl_status_icon = ctk.CTkLabel(self.bottom_right, text="●", font=("Segoe UI", 10), text_color="#10b981")
        self.lbl_status_icon.pack(side="right", padx=(0, 2))

        # Subtle Footer Attribution Line (Restored author credit without squeezing navigation/status)
        self.bottom_credit_row = ctk.CTkFrame(self.bottom_frame, fg_color="transparent")
        self.bottom_credit_row.pack(fill="x", side="bottom", padx=10, pady=(0, 2))

        self.lbl_credit = ctk.CTkLabel(
            self.bottom_credit_row,
            text="Created by Alireza Mostaghasi, 2026",
            font=("Segoe UI", 11),
            text_color="#94A3B8"
        )
        self.lbl_credit.pack(anchor="center")

        # Initial responsive reflow pass based on launch geometry
        scale = 1.0
        try:
            scale = self._get_window_scaling()
        except Exception:
            pass
        if scale <= 0:
            scale = 1.0
        init_w = getattr(self, 'init_logical_w', 818)
        self.reflow_header(init_w)


    def get_export_format(self):
        """Returns canonical export format string, stripping any UI label prefix."""
        val = self.combo_format.get() if hasattr(self, 'combo_format') else "Original"
        return val.replace("Format: ", "").strip()

    def set_export_format(self, fmt):
        """Sets export format option menu, accepting either raw format or prefixed string."""
        if not hasattr(self, 'combo_format'):
            return
        target = f"Format: {fmt}" if not fmt.startswith("Format: ") else fmt
        if target in self.combo_format.cget("values"):
            self.combo_format.set(target)
        else:
            self.combo_format.set("Format: Original")

    def show_overflow_menu(self):
        """Displays grouped overflow popup menu for secondary actions."""
        menu = tk.Menu(self, tearoff=0, bg="#181a26", fg="#f8fafc", activebackground="#4f46e5", activeforeground="#ffffff", bd=1, relief="flat", font=("Segoe UI", 9))
        menu.add_command(label="Open Folder...", command=self.open_folder)
        menu.add_separator()
        menu.add_command(label="Help & Keyboard Shortcuts (F1)", command=self.show_help_dialog)
        menu.add_command(label="About Photo Tagger", command=self.show_help_dialog)
        try:
            x = self.btn_overflow.winfo_rootx()
            y = self.btn_overflow.winfo_rooty() + self.btn_overflow.winfo_height() + 2
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def show_help_dialog(self):
        """Displays single authoritative user guide, keyboard shortcuts, and creator credit modal."""
        if hasattr(self, '_help_window') and self._help_window and self._help_window.winfo_exists():
            self._help_window.deiconify()
            self._help_window.lift()
            self._help_window.focus_force()
            return

        help_win = ctk.CTkToplevel(self)
        self._help_window = help_win
        help_win.title(f"Photo Tagger v{APP_VERSION} — User Guide & About")
        help_win.geometry("580x560")
        help_win.configure(fg_color="#0f111a")
        help_win.resizable(False, False)
        help_win.attributes("-topmost", True)
        
        # Header card
        header = ctk.CTkFrame(help_win, fg_color="#181a26", corner_radius=8, border_width=1, border_color="#2b3046")
        header.pack(fill="x", padx=16, pady=(16, 10))
        
        if self.app_logo_img:
            logo = ctk.CTkImage(
                light_image=self.app_logo_img.cget("light_image"),
                dark_image=self.app_logo_img.cget("dark_image"),
                size=(76, 76),
            )
            ctk.CTkLabel(header, text="", image=logo).pack(pady=(12, 2))

        lbl_title = ctk.CTkLabel(header, text="Photo Tagger", font=("Segoe UI", 20, "bold"), text_color=COLOR_TEXT_PRIMARY)
        lbl_title.pack(pady=(2, 2))
        lbl_sub = ctk.CTkLabel(header, text=f"Version v{APP_VERSION}\nCreated by Alireza Mostaghasi\nRelease date: 2026", font=("Segoe UI", 11), justify="center", text_color=COLOR_TEXT_SECONDARY)
        lbl_sub.pack(pady=(0, 12))

        # Scrollable Shortcuts & Guide
        content = ctk.CTkScrollableFrame(help_win, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=16, pady=4)
        
        sections = [
            ("WORKSPACE & MODES", [
                ("Tagging Mode", "Detect faces, draw bounding boxes, assign names, and order tags spatially."),
                ("Layout Mode", "Reposition tags freely with magnetic leader lines, scale badges, and customize palette."),
                ("Preview Mode", "Inspect exact final composite export with non-destructive overlays.")
            ]),
            ("KEYBOARD SHORTCUTS", [
                ("Ctrl + O", "Open a single photo"),
                ("Ctrl + S", "Save project sidecar (.phototagger.json)"),
                ("Ctrl + W", "Write metadata tags directly to photo (EXIF/XMP)"),
                ("Ctrl + E", "Export tagged composite image to disk"),
                ("Ctrl + 0", "Reset zoom and fit photo to canvas view"),
                ("Left / Right", "Navigate through photos in filmstrip"),
                ("V / A / H", "Switch tool: Select (V), Add Tag (A), Pan Canvas (H)"),
                ("F1", "Open this Help & User Guide dialog")
            ]),
            ("MOUSE & CANVAS ACTIONS", [
                ("Mouse Wheel", "Zoom in / out at cursor position"),
                ("Middle Drag", "Pan around the magnified photo"),
                ("Left Drag", "Draw face box (Tagging mode) or move tag (Layout mode)")
            ]),
            ("ABOUT & CREDITS", [
                ("Application", f"Photo Tagger v{APP_VERSION}"),
                ("Developer", "Alireza Mostaghasi"),
                ("Release date", "2026"),
                ("Engine", "Pillow, Tkinter, CustomTkinter"),
                ("Edition", "Charcoal")
            ])
        ]
        
        for sec_title, items in sections:
            sec_card = ctk.CTkFrame(content, fg_color="#141722", corner_radius=6, border_width=1, border_color="#232738")
            sec_card.pack(fill="x", pady=6)
            
            lbl_s = ctk.CTkLabel(sec_card, text=sec_title, font=("Segoe UI", 10, "bold"), text_color="#94a3b8")
            lbl_s.pack(anchor="w", padx=12, pady=(8, 4))
            
            for k, desc in items:
                row = ctk.CTkFrame(sec_card, fg_color="transparent")
                row.pack(fill="x", padx=12, pady=2)
                lbl_k = ctk.CTkLabel(row, text=k, font=("Segoe UI", 10, "bold"), text_color="#38bdf8", width=110, anchor="w")
                lbl_k.pack(side="left")
                lbl_d = ctk.CTkLabel(row, text=desc, font=("Segoe UI", 10), text_color="#cbd5e1", anchor="w")
                lbl_d.pack(side="left", fill="x", expand=True)
            
            ctk.CTkLabel(sec_card, text="", height=4).pack()

        btn_close = ctk.CTkButton(help_win, text="Close", command=help_win.destroy, fg_color="#312e81", hover_color="#4338ca", font=("Segoe UI", 10, "bold"), width=90, height=28)
        btn_close.pack(pady=10)

    def on_undo(self):
        self.set_status("Undo is unavailable in this release.")

    def on_redo(self):
        self.set_status("Redo is unavailable in this release.")

    def toggle_instructions(self):
        if getattr(self, 'instr_expanded', False):
            if hasattr(self, 'instr_desc'):
                self.instr_desc.pack_forget()
            if hasattr(self, 'btn_toggle_instr'):
                self.btn_toggle_instr.configure(text="▼ Expand")
            self.instr_expanded = False
        else:
            if hasattr(self, 'instr_desc'):
                self.instr_desc.pack(fill="x", padx=6, pady=(0, 6))
            if hasattr(self, 'btn_toggle_instr'):
                self.btn_toggle_instr.configure(text="▲ Hide")
            self.instr_expanded = True


    def setup_tooltips(self):
        """Attaches accessible dark-mode tooltips to controls."""
        try:
            # Primary Header Actions
            WidgetTooltip(self.btn_open_file, "Open Single Photo (Ctrl+O)")
            if hasattr(self, 'btn_open_folder'):
                WidgetTooltip(self.btn_open_folder, "Open Folder with Filmstrip")
            WidgetTooltip(self.btn_save_project, "Save Project: Saves badge layout, styles, and tags to sidecar file (.phototagger.json) without touching photo bytes. (Ctrl+S)")
            WidgetTooltip(self.btn_write_tags, "Write Tags to Photo: Embeds names, face regions, and description directly into the photo file (EXIF/XMP). (Ctrl+W)")
            if hasattr(self, 'combo_format'):
                WidgetTooltip(self.combo_format, "Export Format: Output image format for Export Files (Original, JPEG, PNG, WebP). Does not alter original photo during Write Tags.")
            WidgetTooltip(self.btn_export_annotated, "Export Files: Generates standalone HTML, SVG, and tagged JPEG/PNG/WebP composite copies. (Ctrl+E)")
            if hasattr(self, 'btn_overflow'):
                WidgetTooltip(self.btn_overflow, "More actions: Open Folder, Help, About")
            if hasattr(self, 'btn_help'):
                WidgetTooltip(self.btn_help, "User Guide & Keyboard Shortcuts (F1)")
            
            # Workspace Modes
            if hasattr(self, 'mode_switcher'):
                WidgetTooltip(self.mode_switcher, "Workspace Modes: Tagging (1), Layout (2), Preview (3)")

            # Toolbar Tools
            WidgetTooltip(self.tool_switcher, "Tool: Select & Move (V) | Draw Box (A) | Pan Canvas (H)")
            WidgetTooltip(self.btn_undo, "Undo last action (Ctrl+Z)")
            WidgetTooltip(self.btn_redo, "Redo last action (Ctrl+Y)")
            if hasattr(self, 'btn_rotate_left'):
                WidgetTooltip(self.btn_rotate_left, "Rotate Photo Counter-Clockwise 90° (Left)")
            if hasattr(self, 'btn_rotate_right'):
                WidgetTooltip(self.btn_rotate_right, "Rotate Photo Clockwise 90° (Right)")
            if hasattr(self, 'btn_redetect'):
                WidgetTooltip(self.btn_redetect, "Auto-detect faces in photo")
            
            # Toolbar Zoom
            WidgetTooltip(self.btn_zoom_out, "Zoom Out (Ctrl+-)")
            WidgetTooltip(self.lbl_zoom_level, "Current Zoom Factor (Click to Reset)")
            WidgetTooltip(self.btn_zoom_in, "Zoom In (Ctrl++)")
            WidgetTooltip(self.btn_zoom_reset, "Fit Image to Canvas / 100% (Ctrl+0 / F)")

            # Floating Canvas Zoom Overlay
            if hasattr(self, 'canvas_zoom_pill'):
                WidgetTooltip(self.c_btn_zoom_out, "Zoom Out (Ctrl+-)")
                WidgetTooltip(self.c_btn_zoom_in, "Zoom In (Ctrl++)")
                WidgetTooltip(self.c_btn_fit, "Fit Image to Canvas (Ctrl+0 / F)")
        except Exception:
            pass

    def setup_keyboard_shortcuts(self):
        buttons = (
            self.btn_open_file, self.btn_open_folder, self.btn_help, self.btn_overflow,
            self.btn_save_project, self.btn_write_tags, self.btn_export_annotated,
            self.btn_rotate_left, self.btn_rotate_right, self.c_btn_zoom_in,
            self.c_btn_zoom_out, self.c_btn_fit,
            *self.mode_switcher._buttons_dict.values(),
            *self.tool_switcher._buttons_dict.values(),
        )

        def draw_focus(button, focused):
            canvas = button._canvas
            canvas.delete("keyboard_focus")
            if focused:
                canvas.create_rectangle(2, 2, canvas.winfo_width() - 2,
                                        canvas.winfo_height() - 2,
                                        outline="#9AC7FF", width=2,
                                        tags="keyboard_focus")

        def activate(button):
            if button.cget("state") != "disabled":
                button.invoke()
            return "break"

        for button in buttons:
            # CTkButton does not expose the underlying Tk frame's takefocus option.
            button.tk.call(button._w, "configure", "-takefocus", 1)
            tk.Misc.bind(button, "<FocusIn>", lambda event, b=button: draw_focus(b, True), "+")
            tk.Misc.bind(button, "<FocusOut>", lambda event, b=button: draw_focus(b, False), "+")
            for target in (button, *button.winfo_children()):
                for key in ("<Return>", "<space>"):
                    tk.Misc.bind(target, key, lambda event, b=button: activate(b), "+")

        """Configures accessible keyboard shortcuts."""
        # File / Action shortcuts
        self.bind("<Control-s>", lambda e: self.on_save_project())
        self.bind("<Control-S>", lambda e: self.on_save_project())
        self.bind("<Control-w>", lambda e: self.save_current())
        self.bind("<Control-W>", lambda e: self.save_current())
        self.bind("<Control-e>", lambda e: self.export_annotated_photo())
        self.bind("<Control-E>", lambda e: self.export_annotated_photo())
        self.bind("<Control-o>", lambda e: self.open_image())
        self.bind("<Control-O>", lambda e: self.open_image())
        
        # Zoom shortcuts
        self.bind("<Control-plus>", lambda e: self.zoom_in())
        self.bind("<Control-equal>", lambda e: self.zoom_in())
        self.bind("<Control-minus>", lambda e: self.zoom_out())
        self.bind("<Control-0>", lambda e: self.zoom_reset())
        self.bind("<F1>", lambda e: self.show_help_dialog())

        # Rotation shortcuts
        self.bind("<Control-bracketleft>", lambda e: self.rotate_photo("left"))
        self.bind("<Control-bracketright>", lambda e: self.rotate_photo("right"))
        self.bind("<Control-r>", lambda e: self.rotate_photo("right"))
        self.bind("<Control-R>", lambda e: self.rotate_photo("right"))

        # Single key shortcuts (when not typing in entry / textbox)
        self.bind("<KeyPress>", self.on_global_key_press, add="+")

    def on_global_key_press(self, event):
        widget = event.widget
        # Do not intercept keys when user is typing into text inputs
        if isinstance(widget, (ctk.CTkEntry, ctk.CTkTextbox, tk.Entry, tk.Text)):
            return
        w_class = getattr(widget, 'winfo_class', lambda: '')()
        if w_class in ('Entry', 'Text', 'TEntry', 'CustomTkinterEntry'):
            return

        key = event.keysym.lower()
        if key == 'v':
            self.on_tool_mode_changed("Select")
            if hasattr(self, 'tool_switcher'):
                self.tool_switcher.set("Select")
        elif key == 'a':
            self.on_tool_mode_changed("Add Tag")
            if hasattr(self, 'tool_switcher'):
                self.tool_switcher.set("Add Tag")
        elif key == 'h':
            self.on_tool_mode_changed("Pan")
            if hasattr(self, 'tool_switcher'):
                self.tool_switcher.set("Pan")
        elif key in ('1', 'exclam'):
            self.on_workspace_mode_changed("Tagging")
        elif key in ('2', 'at'):
            self.on_workspace_mode_changed("Layout")
        elif key in ('3', 'numbersign'):
            self.on_workspace_mode_changed("Preview")
        elif key == 'f':
            self.zoom_reset()

    def on_window_configure(self, event):
        if event.widget != self:
            return
        scale = 1.0
        try:
            scale = self._get_window_scaling()
        except Exception:
            pass
        if scale <= 0:
            scale = 1.0
        logical_w = event.width / scale
        self.reflow_header(logical_w)

    def reflow_header(self, logical_w):
        # 1. Mode Switcher Placement:
        # At logical_w < 1180 (including default 818px launch size and 680px minimum supported size),
        # reflow mode switcher down to Row 1 (toolbar_center) to eliminate text clipping
        # and preserve primary action clearances. At wide layouts (>= 1180), place on Row 0.
        if logical_w < 1180:
            if hasattr(self, 'mode_switcher') and hasattr(self, 'toolbar_center'):
                if getattr(self, '_mode_switcher_location', None) != "toolbar":
                    self.mode_switcher.pack_forget()
                    self.mode_switcher.pack(in_=self.toolbar_center, anchor="center")
                    self._mode_switcher_location = "toolbar"
                self.mode_switcher.lift()
            if hasattr(self, 'lbl_photo_metadata') and self.lbl_photo_metadata.winfo_manager() == "pack":
                self.lbl_photo_metadata.pack_forget()
            
            # Maintain persistent status indicators with responsive filename truncation
            if hasattr(self, 'pill_project_status') and self.pill_project_status.winfo_manager() != "pack" and hasattr(self, 'identity_frame'):
                self.pill_project_status.pack(side="left", padx=2)
            if hasattr(self, 'lbl_identity_sep') and self.lbl_identity_sep.winfo_manager() != "pack" and hasattr(self, 'identity_frame'):
                if hasattr(self, 'pill_project_status') and self.pill_project_status.winfo_manager() == "pack":
                    self.lbl_identity_sep.pack(side="left", padx=(0, 6), before=self.pill_project_status)
                else:
                    self.lbl_identity_sep.pack(side="left", padx=(0, 6))
            if hasattr(self, 'pill_metadata_status') and self.pill_metadata_status.winfo_manager() != "pack" and hasattr(self, 'identity_frame'):
                self.pill_metadata_status.pack(side="left", padx=2)
            
        else:
            if hasattr(self, 'mode_switcher') and hasattr(self, 'header_center'):
                if getattr(self, '_mode_switcher_location', None) != "header":
                    self.mode_switcher.pack_forget()
                    self.mode_switcher.pack(in_=self.header_center, anchor="center")
                    self._mode_switcher_location = "header"
                self.mode_switcher.lift()
            if hasattr(self, 'lbl_photo_metadata') and self.lbl_photo_metadata.winfo_manager() != "pack" and hasattr(self, 'tool_switcher'):
                self.lbl_photo_metadata.pack(side="left", padx=(0, 12), before=self.tool_switcher)
            if hasattr(self, 'pill_project_status') and self.pill_project_status.winfo_manager() != "pack" and hasattr(self, 'identity_frame'):
                self.pill_project_status.pack(side="left", padx=2)
            if hasattr(self, 'lbl_identity_sep') and self.lbl_identity_sep.winfo_manager() != "pack" and hasattr(self, 'pill_project_status'):
                self.lbl_identity_sep.pack(side="left", padx=(0, 6), before=self.pill_project_status)
            if hasattr(self, 'pill_metadata_status') and self.pill_metadata_status.winfo_manager() != "pack" and hasattr(self, 'identity_frame'):
                self.pill_metadata_status.pack(side="left", padx=2)

        # At narrow widths reserve a full row for the enlarged workspace tabs.
        if logical_w < 850:
            self.toolbar_center.pack_configure(side="bottom", before=self.identity_frame)
        else:
            self.toolbar_center.pack_configure(side="left", after=self.tool_zoom_frame)

        if 1180 <= logical_w < 1450:
            self.header_center.pack_configure(side="bottom", before=self.header_left)
        else:
            self.header_center.pack_configure(side="left", after=self.action_frame)

        # 2. Header Action Buttons & Overflow:
        if logical_w < 1180:
            # Compact Layout (< 1180): Retain primary actions, fold secondary actions into overflow [•••]
            if hasattr(self, 'btn_save_project'):
                self.btn_save_project.configure(text="Save Project", width=108)
            if hasattr(self, 'btn_write_tags'):
                self.btn_write_tags.configure(text="Write Tags", width=106)
            if hasattr(self, 'btn_export_annotated'):
                self.btn_export_annotated.configure(text="Export Files", width=108)
            if hasattr(self, 'btn_open_file'):
                self.btn_open_file.configure(text="Open Photo", width=106)
            if hasattr(self, 'btn_open_folder') and self.btn_open_folder.winfo_manager() == "pack":
                self.btn_open_folder.pack_forget()
            if hasattr(self, 'btn_help') and self.btn_help.winfo_manager() == "pack":
                self.btn_help.pack_forget()
            if hasattr(self, 'btn_overflow') and self.btn_overflow.winfo_manager() != "pack":
                self.btn_overflow.pack(side="right", padx=2)
            if logical_w < 960:
                if hasattr(self, 'lbl_brand_badge') and self.lbl_brand_badge.winfo_manager() == "pack":
                    self.lbl_brand_badge.pack_forget()
            else:
                if hasattr(self, 'lbl_brand_badge') and self.lbl_brand_badge.winfo_manager() != "pack" and hasattr(self, 'btn_open_file'):
                    self.lbl_brand_badge.pack(side="left", padx=(0, 8), before=self.btn_open_file)
        else:
            # Wide Layout (>= 1180): Show secondary actions directly, hide overflow
            if hasattr(self, 'lbl_brand_badge') and self.lbl_brand_badge.winfo_manager() != "pack" and hasattr(self, 'btn_open_file'):
                self.lbl_brand_badge.pack(side="left", padx=(0, 8), before=self.btn_open_file)
            if hasattr(self, 'btn_save_project'):
                self.btn_save_project.configure(text="Save Project", width=108)
            if hasattr(self, 'btn_write_tags'):
                self.btn_write_tags.configure(text="Write Tags to Photo", width=140)
            if hasattr(self, 'btn_export_annotated'):
                self.btn_export_annotated.configure(text="Export Files", width=108)
            if hasattr(self, 'btn_open_file'):
                self.btn_open_file.configure(text="Open Photo", width=106)
            if hasattr(self, 'btn_open_folder') and self.btn_open_folder.winfo_manager() != "pack":
                self.btn_open_folder.pack(side="left", padx=2)
            if hasattr(self, 'btn_help') and self.btn_help.winfo_manager() != "pack":
                self.btn_help.pack(side="right", padx=2)
            if hasattr(self, 'btn_overflow') and self.btn_overflow.winfo_manager() == "pack":
                self.btn_overflow.pack_forget()
        
        # Enforce charcoal action hierarchy
        self._update_primary_action_hierarchy()

    def _draw_tab_underline(self, btn, is_active):
        canvas = btn._canvas
        canvas.delete("active_underline")
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if is_active and width > 8 and height > 4:
            canvas.create_line(4, height - 2, width - 4, height - 2,
                               fill="#818cf8", width=2, tags="active_underline")

    def _update_primary_action_hierarchy(self):
        """
        Enforces Charcoal UI Primary Action Rule:
        - In Tagging or Layout mode: Save Project is the sole solid accent button (#4f46e5).
          Export Files is a quiet secondary button with no idle border.
        - In Preview mode: Export Files is the sole solid accent button (#4f46e5).
          Save Project is a quiet secondary button with no idle border.
        - All secondary controls are quiet semibold text with two-tone icons, no idle border, and #353D4A hover.
        """
        is_preview = (getattr(self, 'active_workspace_mode', 'tagging') == "preview")
        
        # Save Project button
        if hasattr(self, 'btn_save_project'):
            if not is_preview:
                self.btn_save_project.configure(
                    fg_color=COLOR_ACCENT_PRIMARY,
                    hover_color=COLOR_ACCENT_PRIMARY_HOVER,
                    text_color="#ffffff",
                    font=("Segoe UI", 13, "bold"),
                    border_width=0
                )
            else:
                self.btn_save_project.configure(
                    fg_color="transparent",
                    hover_color=COLOR_SURFACE_HOVER,
                    text_color=COLOR_TEXT_PRIMARY,
                    font=("Segoe UI Semibold", 13),
                    border_width=0
                )

        # Export Files button
        if hasattr(self, 'btn_export_annotated'):
            if is_preview:
                self.btn_export_annotated.configure(
                    fg_color=COLOR_ACCENT_EXPORT,
                    hover_color=COLOR_ACCENT_EXPORT_HOVER,
                    text_color="#ffffff",
                    font=("Segoe UI", 13, "bold"),
                    border_width=0
                )
            else:
                self.btn_export_annotated.configure(
                    fg_color="transparent",
                    hover_color=COLOR_SURFACE_HOVER,
                    text_color=COLOR_TEXT_PRIMARY,
                    font=("Segoe UI Semibold", 13),
                    border_width=0
                )

        # Mode switcher visual state, active underline and accessible cue
        if hasattr(self, 'mode_switcher') and hasattr(self.mode_switcher, '_buttons_dict'):
            curr_mode = getattr(self, 'active_workspace_mode', 'tagging')
            for tab_name, btn in self.mode_switcher._buttons_dict.items():
                is_active = ((curr_mode == "tagging" and "Tag" in tab_name) or
                             (curr_mode == "layout" and "Layout" in tab_name) or
                             (curr_mode == "preview" and "Preview" in tab_name))
                btn._pt_tab_active = is_active
                if not getattr(btn, "_pt_underline_bound", False):
                    btn._canvas.bind("<Configure>", lambda event, tab=btn:
                                     self._draw_tab_underline(tab, tab._pt_tab_active), add="+")
                    btn._pt_underline_bound = True
                self._draw_tab_underline(btn, is_active)
                try:
                    if is_active:
                        btn.configure(font=("Segoe UI", 14, "bold"), text_color="#ffffff", fg_color=COLOR_WORKSPACE)
                    else:
                        btn.configure(font=("Segoe UI", 13, "normal"), text_color=COLOR_TEXT_SECONDARY, fg_color=COLOR_WORKSPACE)
                except Exception:
                    pass

        # Inspector tab visual state and active underline
        if hasattr(self, 'inspector_tab_segmented') and hasattr(self.inspector_tab_segmented, '_buttons_dict'):
            curr_tab = getattr(self, 'active_inspector_tab', 'People')
            for tab_name, btn in self.inspector_tab_segmented._buttons_dict.items():
                is_active = ((curr_tab == "People" and "People" in tab_name) or
                             ((curr_tab == "Details" or curr_tab == "Photo Details") and "Detail" in tab_name) or
                             (curr_tab == "Appearance" and "Appearance" in tab_name))
                btn._pt_tab_active = is_active
                if not getattr(btn, "_pt_underline_bound", False):
                    btn._canvas.bind("<Configure>", lambda event, tab=btn:
                                     self._draw_tab_underline(tab, tab._pt_tab_active), add="+")
                    btn._pt_underline_bound = True
                self._draw_tab_underline(btn, is_active)
                try:
                    if is_active:
                        btn.configure(font=("Segoe UI", 12, "bold"), text_color="#ffffff", fg_color=COLOR_SETTINGS_SURFACE)
                    else:
                        btn.configure(font=("Segoe UI", 12, "normal"), text_color=COLOR_TEXT_SECONDARY, fg_color=COLOR_SETTINGS_SURFACE)
                except Exception:
                    pass

    def on_workspace_mode_changed(self, mode_name):
        self.render_revision = getattr(self, 'render_revision', 0) + 1
        self.last_bg_key = None
        self.canvas.delete("bg_image")
        
        target_val = mode_name
        if hasattr(self, 'mode_switcher'):
            vals = self.mode_switcher.cget("values")
            for v in vals:
                if ("Preview" in mode_name and "Preview" in v) or \
                   ("Layout" in mode_name and "Layout" in v) or \
                   ("Tag" in mode_name and "Tag" in v):
                    target_val = v
                    break
            self.mode_switcher.set(target_val)

        if "Tag" in mode_name:
            self.active_workspace_mode = "tagging"
            if hasattr(self, 'inspector_tab_segmented'):
                self.inspector_tab_segmented.set("People")
                self.on_inspector_tab_changed("People")
        elif "Layout" in mode_name:
            self.active_workspace_mode = "layout"
            if hasattr(self, 'inspector_tab_segmented'):
                self.inspector_tab_segmented.set("Appearance")
                self.on_inspector_tab_changed("Appearance")
        elif "Preview" in mode_name:
            self.active_workspace_mode = "preview"
            if hasattr(self, 'inspector_tab_segmented'):
                self.inspector_tab_segmented.set("Photo Details")
                self.on_inspector_tab_changed("Photo Details")

        self._update_primary_action_hierarchy()

        if hasattr(self, '_sync_modified_status') and callable(self._sync_modified_status):
            self._sync_modified_status()
        self.draw_canvas()

    def on_tool_mode_changed(self, tool_name):
        if "Select" in tool_name or "↖" in tool_name:
            self.active_tool_mode = "select"
            self.is_pan_mode = False
        elif "Add" in tool_name or "➕" in tool_name or "+" in tool_name:
            self.active_tool_mode = "add_face"
            self.is_pan_mode = False
        elif "Pan" in tool_name or "🖐" in tool_name or "✥" in tool_name:
            self.active_tool_mode = "pan"
            self.is_pan_mode = True
        if hasattr(self, "canvas"):
            self.canvas.configure(cursor="hand2" if self.is_pan_mode else "")

    def on_inspector_tab_changed(self, tab_name):
        self.active_inspector_tab = tab_name
        if hasattr(self, 'tab_people_frame') and hasattr(self, 'tab_details_frame') and hasattr(self, 'tab_appearance_frame'):
            self.tab_people_frame.pack_forget()
            self.tab_details_frame.pack_forget()
            self.tab_appearance_frame.pack_forget()
            if "People" in tab_name:
                self.tab_people_frame.pack(fill="both", expand=True)
            elif "Detail" in tab_name:
                self.tab_details_frame.pack(fill="both", expand=True)
                self.update_details_view()
            elif "Appearance" in tab_name:
                self.tab_appearance_frame.pack(fill="both", expand=True)
                if hasattr(self, 'update_badge_shape_preview'):
                    self.update_badge_shape_preview()
                if hasattr(self, 'update_swatch_selection'):
                    self.update_swatch_selection()
        self._update_primary_action_hierarchy()

    def on_preset_changed(self, preset_name):
        self.current_preset = preset_name
        p = str(preset_name).strip().lower()
        if "outline" in p:
            self.combo_style_color.set("White")
            self.combo_style_font_size.set("Auto (1.0x)")
        elif "borderless" in p:
            self.combo_style_color.set("Teal")
            self.combo_style_font_size.set("Auto (1.0x)")
        elif "high" in p:
            self.combo_style_color.set("Yellow")
            self.combo_style_font_size.set("Auto (1.0x)")
        elif "minimal" in p:
            self.combo_style_color.set("White")
            self.combo_style_font_size.set("Small (0.7x)")
        elif "print" in p:
            self.combo_style_color.set("White")
            self.combo_style_font_size.set("Auto (1.0x)")
        else: # Classic / Studio Minimal
            self.combo_style_color.set("Teal")
            self.combo_style_font_size.set("Auto (1.0x)")
        if hasattr(self, 'combo_style_font_size') and hasattr(self, 'get_selected_font_size_style') and callable(self.get_selected_font_size_style):
            style_info = self.get_selected_font_size_style()
            scale_val = style_info["scale"]
            self._badge_scale_factor = scale_val
            if hasattr(self, 'slider_badge_scale'):
                self.slider_badge_scale.set(scale_val)
            if hasattr(self, 'lbl_scale_value'):
                self.lbl_scale_value.configure(text=f"{scale_val:.2f}x")
        if hasattr(self, 'update_swatch_selection'):
            self.update_swatch_selection()
        self.render_revision = getattr(self, 'render_revision', 0) + 1
        self.last_bg_key = None
        self.set_modified(True, project=True, metadata=False)
        self.draw_canvas()

    def reset_positions(self):
        for f in self.faces:
            f['bx'] = None
            f['by'] = None
        self.render_revision = getattr(self, 'render_revision', 0) + 1
        self.last_bg_key = None
        self.set_modified(True, project=True, metadata=False)
        self.draw_canvas()
        self.set_status("Reset all badge positions to automatic default.")

    def rotate_photo(self, direction="right"):
        """
        Rotates the photo 90 degrees CCW (left) or CW (right), transforming
        face bounding boxes and badge coordinates with exact geometric fidelity.
        """
        if not getattr(self, 'original_pil_image', None):
            self.set_status("No photo loaded to rotate.")
            return

        self._image_rotated = True
        curr_angle = getattr(self, '_image_rotation_angle', 0)
        if direction == "left":
            self._image_rotation_angle = (curr_angle + 270) % 360
            self.original_pil_image = self.original_pil_image.transpose(Image.Transpose.ROTATE_90)
        else:
            self._image_rotation_angle = (curr_angle + 90) % 360
            self.original_pil_image = self.original_pil_image.transpose(Image.Transpose.ROTATE_270)

        new_w, new_h = self.original_pil_image.size
        self.image_dimensions = (new_w, new_h)

        # Transform face coordinates & badge positions
        for f in self.faces:
            ox, oy, ow, oh = f['x'], f['y'], f['w'], f['h']
            if direction == "left":
                f['x'] = oy
                f['y'] = 1.0 - ox
                f['w'] = oh
                f['h'] = ow
                if f.get('bx') is not None and f.get('by') is not None:
                    obx, oby = f['bx'], f['by']
                    f['bx'] = oby
                    f['by'] = 1.0 - obx
            else:
                f['x'] = 1.0 - oy
                f['y'] = ox
                f['w'] = oh
                f['h'] = ow
                if f.get('bx') is not None and f.get('by') is not None:
                    obx, oby = f['bx'], f['by']
                    f['bx'] = 1.0 - oby
                    f['by'] = obx

        # Invalidate canvas caches and redraw
        self.render_revision = getattr(self, 'render_revision', 0) + 1
        self.last_bg_key = None
        self.set_modified(True, project=True, metadata=True)
        if hasattr(self, 'draw_canvas'):
            self.draw_canvas()
        if hasattr(self, 'rebuild_sidebar'):
            self.rebuild_sidebar()
        if hasattr(self, 'lbl_photo_metadata') and self.current_image_path:
            try:
                size_bytes = os.path.getsize(self.current_image_path)
                if size_bytes >= 1024 * 1024:
                    size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
                elif size_bytes >= 1024:
                    size_str = f"{size_bytes / 1024:.0f} KB"
                else:
                    size_str = f"{size_bytes} B"
                self.lbl_photo_metadata.configure(text=f"{new_w} \u00d7 {new_h} px  \u2022  {size_str}")
            except Exception:
                pass
        self.set_status(f"Rotated photo 90° {'Counter-Clockwise (Left)' if direction == 'left' else 'Clockwise (Right)'}.")

    def toggle_filmstrip(self):
        self.is_filmstrip_expanded = not self.is_filmstrip_expanded
        if self.is_filmstrip_expanded:
            self.filmstrip_frame.grid()
            self.btn_toggle_filmstrip.configure(text="🎞️ Filmstrip (▼)")
            self.populate_filmstrip()
        else:
            self.filmstrip_frame.grid_remove()
            self.btn_toggle_filmstrip.configure(text=f"🎞️ Filmstrip ({len(self.image_list)}) ▲")

    def populate_filmstrip(self):
        if not hasattr(self, 'filmstrip_scroll'):
            return
        for widget in self.filmstrip_scroll.winfo_children():
            widget.destroy()
        self.filmstrip_thumbnails = []
        self.filmstrip_buttons = []
        if not self.image_list:
            lbl = ctk.CTkLabel(self.filmstrip_scroll, text="No photos open", text_color="#a6adc8")
            lbl.pack(padx=20, pady=20)
            return

        for idx, img_path in enumerate(self.image_list):
            is_active = (idx == self.current_image_idx)
            btn_frame = ctk.CTkFrame(
                self.filmstrip_scroll,
                fg_color="#313244" if is_active else "#181825",
                border_width=2 if is_active else 1,
                border_color="#89b4fa" if is_active else "#45475a",
                corner_radius=6
            )
            btn_frame.pack(side="left", padx=4, pady=4)
            try:
                with Image.open(img_path) as thumb_img:
                    thumb_img.thumbnail((50, 50))
                    ctk_thumb = ctk.CTkImage(light_image=thumb_img, dark_image=thumb_img, size=(thumb_img.width, thumb_img.height))
                    self.filmstrip_thumbnails.append(ctk_thumb)
                    lbl_thumb = ctk.CTkLabel(btn_frame, image=ctk_thumb, text="")
                    lbl_thumb.pack(padx=4, pady=(4, 2))
                    lbl_thumb.bind("<Button-1>", lambda event, i=idx: self.switch_to_filmstrip_index(i))
            except Exception:
                lbl_thumb = ctk.CTkLabel(btn_frame, text="🖼️", font=("Segoe UI", 14))
                lbl_thumb.pack(padx=8, pady=(8, 2))
                lbl_thumb.bind("<Button-1>", lambda event, i=idx: self.switch_to_filmstrip_index(i))

            lbl_name = ctk.CTkLabel(btn_frame, text=os.path.basename(img_path)[:12], font=("Segoe UI", 8), text_color="#cdd6f4")
            lbl_name.pack(padx=2, pady=(0, 2))
            btn_frame.bind("<Button-1>", lambda event, i=idx: self.switch_to_filmstrip_index(i))
            close = ctk.CTkButton(
                btn_frame, text="×", width=22, height=22, corner_radius=5,
                font=("Segoe UI", 16, "bold"), fg_color=COLOR_WORKSPACE,
                hover_color=COLOR_SURFACE_HOVER, command=lambda i=idx: self.close_filmstrip_photo(i),
            )
            close.place(relx=1, x=-2, y=2, anchor="ne")
            WidgetTooltip(close, "Close photo")


    def switch_to_filmstrip_index(self, idx):
        if idx == self.current_image_idx or idx < 0 or idx >= len(self.image_list):
            return
        target_path = self.image_list[idx]
        if self.load_image(target_path):
            self.current_image_idx = idx
            self.update_navigation_controls()
            self.populate_filmstrip()

    def close_filmstrip_photo(self, idx):
        if not 0 <= idx < len(self.image_list):
            return
        remaining = self.image_list[:idx] + self.image_list[idx + 1:]
        next_idx = self.current_image_idx
        if idx == next_idx:
            if remaining:
                next_idx = min(idx, len(remaining) - 1)
                if not self.load_image(remaining[next_idx]):
                    return
            else:
                if self.is_modified:
                    response = messagebox.askyesnocancel(
                        "Unsaved Changes",
                        "Save your changes before closing this photo?",
                        parent=self,
                    )
                    if response is None or (response and not self.save_current()):
                        return
                    if not response:
                        discard_draft(self.current_image_path)
                self.current_image_path = None
                self.original_pil_image = None
                self.current_doc = None
                self.faces = []
                self.description = ""
                self.selected_face_idx = self.hovered_face_idx = None
                self.last_bg_key = None
                self._image_rotated = False
                self._image_rotation_angle = 0
                self.set_modified(False)
                self.zoom_reset()
                self.rebuild_sidebar()
                self.update_details_view()
                self.set_status("Photo closed.")
                next_idx = -1
        elif idx < next_idx:
            next_idx -= 1

        self.image_list = remaining
        self.current_image_idx = next_idx
        self.update_navigation_controls()
        self.populate_filmstrip()

    def update_details_view(self):
        if not hasattr(self, 'lbl_detail_filename'):
            return
        if self.current_image_path and self.original_pil_image:
            name = os.path.basename(self.current_image_path)
            w, h = self.original_pil_image.size
            size_kb = os.path.getsize(self.current_image_path) / 1024.0 if os.path.exists(self.current_image_path) else 0.0
            self.lbl_detail_filename.configure(text=f"File: {name}")
            self.lbl_detail_dimensions.configure(text=f"Dimensions: {w} × {h} px ({self.original_pil_image.mode})")
            self.lbl_detail_size.configure(text=f"Disk Size: {size_kb:.1f} KB")
        else:
            self.lbl_detail_filename.configure(text="File: (No photo loaded)")
            self.lbl_detail_dimensions.configure(text="Dimensions: -")
            self.lbl_detail_size.configure(text="Disk Size: -")

    def _sync_modified_status(self):
        title_base = f"Photo Tagger v{APP_VERSION}"
        active_mode = getattr(self, 'active_workspace_mode', 'tagging').capitalize()
        is_dirty = bool(getattr(self, 'is_project_dirty', False) or getattr(self, 'is_metadata_dirty', False) or getattr(self, 'is_modified', False))
        dirty_status = " *" if is_dirty else ""
        if getattr(self, 'current_image_path', None):
            name = os.path.basename(self.current_image_path)
            if hasattr(self, 'title') and callable(self.title):
                self.title(f"{title_base} - [{name}] ({active_mode}){dirty_status}")
            if hasattr(self, 'lbl_photo_identity'):
                scale = self._get_window_scaling() if hasattr(self, '_get_window_scaling') else 1.0
                curr_w = self.winfo_width() / scale if self.winfo_width() > 1 else getattr(self, 'init_logical_w', 818)
                max_chars = 14 if curr_w < 760 else (22 if curr_w < 950 else (34 if curr_w < 1180 else 46))
                short_n = (name[:max_chars - 6] + "…" + name[-5:]) if len(name) > max_chars else name
                self.lbl_photo_identity.configure(text=short_n)
        else:
            if hasattr(self, 'title') and callable(self.title):
                self.title(f"{title_base} ({active_mode})")
            if hasattr(self, 'lbl_photo_identity'):
                self.lbl_photo_identity.configure(text="No Photo Loaded")
            if hasattr(self, 'lbl_photo_metadata'):
                self.lbl_photo_metadata.configure(text="")

        # Update discrete status indicators in top toolbar (Charcoal UI spec)
        if hasattr(self, 'pill_project_status'):
            if getattr(self, 'is_project_dirty', False):
                self.pill_project_status.configure(text="● Unsaved", text_color=COLOR_STATUS_UNSAVED, fg_color="transparent")
            else:
                self.pill_project_status.configure(text="● Saved", text_color=COLOR_STATUS_SAVED, fg_color="transparent")

        if hasattr(self, 'pill_metadata_status'):
            if getattr(self, 'is_metadata_dirty', False):
                self.pill_metadata_status.configure(text="● Tags pending", text_color=COLOR_STATUS_PENDING, fg_color="transparent")
            else:
                self.pill_metadata_status.configure(text="✓ Tags synced", text_color=COLOR_STATUS_SYNCED, fg_color="transparent")

    def set_modified(self, modified=True, project=None, metadata=None):
        if not modified:
            self.is_project_dirty = False
            self.is_metadata_dirty = False
            self.is_modified = False
        else:
            if project is None and metadata is None:
                self.is_project_dirty = True
                self.is_metadata_dirty = True
            else:
                if project:
                    self.is_project_dirty = True
                if metadata:
                    self.is_metadata_dirty = True
            self.is_modified = bool(getattr(self, 'is_project_dirty', False) or getattr(self, 'is_metadata_dirty', False))

        if hasattr(self, '_sync_modified_status') and callable(self._sync_modified_status):
            self._sync_modified_status()
        elif hasattr(self, 'title') and callable(self.title):
            title_base = f"Photo Tagger v{APP_VERSION}"
            name = os.path.basename(self.current_image_path) if getattr(self, 'current_image_path', None) else ""
            dirty_star = " *" if getattr(self, 'is_modified', False) else ""
            self.title(f"{title_base} - [{name}]{dirty_star}")
            
        if not getattr(self, '_hydrating', False):
            if self.is_modified and getattr(self, 'current_image_path', None):
                if hasattr(self, 'save_draft_state') and callable(self.save_draft_state):
                    try:
                        self.save_draft_state()
                    except Exception as e:
                        print(f"Warning: Failed to save draft: {e}")
            elif not self.is_modified and getattr(self, 'current_image_path', None):
                try:
                    discard_draft(self.current_image_path)
                except Exception:
                    pass

    def mark_changed(self, project: bool = True, metadata: bool = False):
        self.set_modified(True, project=project, metadata=metadata)

    def mark_saved(self, project: bool = False, metadata: bool = False):
        if project:
            self.is_project_dirty = False
        if metadata:
            self.is_metadata_dirty = False
        self.is_modified = bool(getattr(self, 'is_project_dirty', False) or getattr(self, 'is_metadata_dirty', False))
        if hasattr(self, '_sync_modified_status') and callable(self._sync_modified_status):
            self._sync_modified_status()
        if not self.is_modified and getattr(self, 'current_image_path', None):
            try:
                discard_draft(self.current_image_path)
            except Exception:
                pass

    def save_draft_state(self):
        if not getattr(self, 'current_image_path', None):
            return
        w = 0
        h = 0
        if getattr(self, 'original_pil_image', None):
            w, h = self.original_pil_image.size
            
        if not getattr(self, 'current_doc', None):
            self.current_doc = ProjectDocument(image_path=self.current_image_path, image_width=w, image_height=h)
            
        color_val = self.combo_style_color.get() if hasattr(self, 'combo_style_color') else "Teal"
        size_val = self.combo_style_font_size.get() if hasattr(self, 'combo_style_font_size') else "Auto (1.0x)"
        desc_text = getattr(self, 'description', '')
        if hasattr(self, 'desc_textbox') and not getattr(self, '_hydrating', False):
            try:
                desc_text = self.desc_textbox.get("1.0", "end-1c").strip()
                self.description = desc_text
            except Exception:
                pass
                
        self.current_doc.sync_from_app_state(
            faces_dicts=getattr(self, 'faces', []),
            description=desc_text,
            color_theme=color_val,
            font_size_preset=size_val,
            pil_image=getattr(self, 'original_pil_image', None),
            preset_name=getattr(self, 'current_preset', 'Classic'),
            badge_shape=_resolve_app_badge_shape(self),
            font_family=_resolve_app_tag_font(self)
        )
        if not self.current_doc.extra:
            self.current_doc.extra = {}
        self.current_doc.extra['_recovery_state'] = {
            'is_project_dirty': bool(getattr(self, 'is_project_dirty', True)),
            'is_metadata_dirty': bool(getattr(self, 'is_metadata_dirty', True))
        }
        save_project_document(self.current_doc, is_draft=True)

    def on_closing(self):
        if getattr(self, 'is_modified', False):
            name = os.path.basename(self.current_image_path) if getattr(self, 'current_image_path', None) else "Current Photo"
            resp = messagebox.askyesnocancel(
                "Unsaved Changes",
                f"You have unsaved changes in '{name}'.\n\n"
                "• Click Yes to save before exiting.\n"
                "• Click No to discard unsaved changes and exit.\n"
                "• Click Cancel to return to the application."
            )
            if resp is None:  # Cancel -> Return to application without closing
                return
            elif resp is True:  # Yes -> Save
                if not self.save_current():
                    if hasattr(self, 'winfo_exists'):
                        try:
                            messagebox.showerror("Save Failed", "Could not save changes. Exit cancelled to prevent data loss.")
                        except Exception:
                            pass
                    return
            else:  # No -> Discard
                if getattr(self, 'current_image_path', None):
                    discard_draft(self.current_image_path)
        self.destroy()

    def on_style_changed(self, val=None):
        self.render_revision = getattr(self, 'render_revision', 0) + 1
        self.last_bg_key = None
        if hasattr(self, 'update_swatch_selection'):
            self.update_swatch_selection()
        self.set_modified(True, project=True, metadata=False)
        if hasattr(self, 'update_badge_shape_preview'):
            self.update_badge_shape_preview()
        self.draw_canvas()

    def on_swatch_clicked(self, name):
        if hasattr(self, 'combo_style_color'):
            self.combo_style_color.set(name)
        self.on_style_changed(name)

    def update_swatch_selection(self, selected_name=None):
        if selected_name is None and hasattr(self, 'combo_style_color'):
            selected_name = self.combo_style_color.get()
        if hasattr(self, 'lbl_style_color') and selected_name:
            self.lbl_style_color.configure(text=f"Tag Color Accent ({selected_name})")
        if hasattr(self, 'swatch_buttons'):
            for name, btn in self.swatch_buttons.items():
                if name == selected_name or (name == "Orange/Red" and selected_name in ("Orange/Red", "Red", "Orange")):
                    fill = CANONICAL_PALETTE[name]["hex"]
                    text_color, _ = get_contrasting_hex(fill)
                    btn.configure(text="✓", text_color=text_color, border_width=2, border_color="#ffffff")
                    # Reserve space for the check without widening the circular swatch.
                    btn.grid_columnconfigure(0, minsize=3)
                    btn.grid_columnconfigure(4, minsize=3)
                else:
                    btn.configure(text="")
                    if name in ("White", "Yellow"):
                        btn.configure(border_width=1, border_color="#64748b")
                    else:
                        btn.configure(border_width=0)

    def on_scale_slider_changed(self, val):
        try:
            val_float = round(float(val), 2)
        except (TypeError, ValueError):
            val_float = 1.0

        self._badge_scale_factor = val_float
        if hasattr(self, 'lbl_scale_value'):
            self.lbl_scale_value.configure(text=f"{val_float:.2f}x")

        scale_preset_map = {
            0.5: "Micro (0.5x)",
            0.7: "Small (0.7x)",
            1.0: "Auto (1.0x)",
            1.2: "Medium (1.2x)",
            1.5: "Large (1.5x)",
            2.0: "X-Large (2.0x)"
        }
        matched_preset = None
        for p_scale, p_name in scale_preset_map.items():
            if abs(val_float - p_scale) < 0.01:
                matched_preset = p_name
                break

        if hasattr(self, 'combo_style_font_size'):
            if matched_preset:
                self.combo_style_font_size.set(matched_preset)
            else:
                self.combo_style_font_size.set(f"Custom ({val_float:.2f}x)")

        self.on_style_changed()

    def on_seg_shape_changed(self, seg_val):
        if seg_val == "Square":
            combo_val = "Square"
            canon = "square"
        elif seg_val in ("Rounded", "Rounded Square"):
            combo_val = "Rounded Square"
            canon = "rounded_square"
        else:
            combo_val = "Auto Pill/Circle"
            canon = "auto"
        if hasattr(self, 'combo_badge_shape'):
            self.combo_badge_shape.set(combo_val)
        if hasattr(self, 'current_doc') and self.current_doc:
            self.current_doc.style.badge_shape = canon
        self.render_revision = getattr(self, 'render_revision', 0) + 1
        self.last_bg_key = None
        if not getattr(self, '_hydrating', False):
            self.set_modified(True, project=True, metadata=False)
        if hasattr(self, 'update_badge_shape_preview'):
            self.update_badge_shape_preview()
        self.draw_canvas()

    def get_selected_badge_shape(self) -> str:
        return _resolve_app_badge_shape(self)

    def shape_canonical_to_ui(self, canonical_shape: str) -> str:
        from models import normalize_badge_shape
        c = normalize_badge_shape(canonical_shape)
        if c == "rounded_square":
            return "Rounded Square"
        elif c == "square":
            return "Square"
        return "Auto Pill/Circle"

    def get_selected_tag_font(self) -> str:
        """Returns the currently selected tag font family ('Segoe UI', 'Tahoma', or 'Arial')."""
        return _resolve_app_tag_font(self)

    def on_tag_font_changed(self, choice=None):
        font = choice or self.get_selected_tag_font()
        if font not in ("Segoe UI", "Tahoma", "Arial"):
            font = "Segoe UI"
        if hasattr(self, 'seg_tag_font') and self.seg_tag_font.get() != font:
            self.seg_tag_font.set(font)
        if hasattr(self, 'combo_tag_font') and self.combo_tag_font.get() != font:
            self.combo_tag_font.set(font)
        if hasattr(self, 'lbl_font_sample'):
            self.lbl_font_sample.configure(font=(font, 13))
        if hasattr(self, 'current_doc') and self.current_doc:
            self.current_doc.style.font_family = font
        self.render_revision = getattr(self, 'render_revision', 0) + 1
        self.last_bg_key = None
        if not getattr(self, '_hydrating', False):
            self.set_modified(True, project=True, metadata=False)
        if hasattr(self, 'update_badge_shape_preview'):
            self.update_badge_shape_preview()
        self.draw_canvas()

    def update_badge_shape_preview(self):
        """Draws a live sample of the active badge geometry on the appearance card preview."""
        if not hasattr(self, 'badge_preview_canvas'):
            return
        cv = self.badge_preview_canvas
        try:
            cv.delete("all")
            shape = self.get_selected_badge_shape()
            color_preset = self.combo_style_color.get() if hasattr(self, 'combo_style_color') else "Teal"
            style = get_canonical_color_style(color_preset)
            fill_col = style["hex"]
            text_col = style["text_color"]
            tag_font = self.get_selected_tag_font()
            
            style_preset = getattr(self, 'current_preset', 'Classic')
            width = cv.winfo_width()
            if width < 100:
                return
            center_y = cv.winfo_height() / 2
            radius = min(14, width // 16, int(center_y) - 4)
            if radius < 8:
                return
            for fraction, number in ((.22, "1"), (.5, "42"), (.78, "125")):
                draw_canvas_badge(cv, width * fraction, center_y, number, radius,
                                  fill_col, text_color=text_col, badge_shape=shape,
                                  font_family=tag_font, style_preset=style_preset)
        except Exception as e:
            print(f"[ERROR] Failed to draw badge shape preview: {e}")

    def on_shape_changed(self, choice=None):
        self.render_revision = getattr(self, 'render_revision', 0) + 1
        self.last_bg_key = None
        from models import normalize_badge_shape
        if choice is not None:
            selected_shape = normalize_badge_shape(choice)
        elif hasattr(self, 'combo_badge_shape'):
            selected_shape = normalize_badge_shape(self.combo_badge_shape.get())
        else:
            selected_shape = _resolve_app_badge_shape(self)
        if hasattr(self, 'current_doc') and self.current_doc:
            self.current_doc.style.badge_shape = selected_shape
        if hasattr(self, 'seg_badge_shape'):
            if selected_shape == "square":
                self.seg_badge_shape.set("Square")
            elif selected_shape == "rounded_square":
                self.seg_badge_shape.set("Rounded")
            else:
                self.seg_badge_shape.set("Pill")
        if hasattr(self, 'combo_badge_shape'):
            self.combo_badge_shape.set(self.shape_canonical_to_ui(selected_shape))
        if not getattr(self, '_hydrating', False):
            self.set_modified(True, project=True, metadata=False)
        if hasattr(self, 'update_badge_shape_preview'):
            self.update_badge_shape_preview()
        self.draw_canvas()

    def on_save_project(self):
        return self.save_project_only()

    def save_project_only(self):
        """
        Saves ONLY the project sidecar (.phototagger.json).
        Never touches the source photo file, never re-encodes pixels.
        """
        if not getattr(self, 'current_image_path', None) or not getattr(self, 'original_pil_image', None):
            return False
            
        if not getattr(self, 'current_doc', None):
            w, h = self.original_pil_image.size
            self.current_doc = ProjectDocument(image_path=self.current_image_path, image_width=w, image_height=h)
            
        desc_text = getattr(self, 'description', '')
        if hasattr(self, 'desc_textbox') and not getattr(self, '_hydrating', False):
            try:
                desc_text = self.desc_textbox.get("1.0", "end-1c").strip()
                self.description = desc_text
            except Exception:
                pass
            
        color_val = self.combo_style_color.get() if hasattr(self, 'combo_style_color') else "Teal"
        size_val = self.combo_style_font_size.get() if hasattr(self, 'combo_style_font_size') else "Auto (1.0x)"
        
        self.current_doc.sync_from_app_state(
            faces_dicts=getattr(self, 'faces', []),
            description=desc_text,
            color_theme=color_val,
            font_size_preset=size_val,
            pil_image=self.original_pil_image,
            preset_name=getattr(self, 'current_preset', 'Classic'),
            badge_shape=_resolve_app_badge_shape(self),
            font_family=_resolve_app_tag_font(self)
        )
        
        if getattr(self, '_image_rotated', False):
            self.current_doc.extra["rotation"] = getattr(self, '_image_rotation_angle', 0)

        try:
            blocked = getattr(self, 'blocked_sidecars', set())
            saved = save_project_document(self.current_doc, is_draft=False, blocked_sidecars=blocked)
            if saved:
                self.is_project_dirty = False
                self.set_modified(getattr(self, 'is_metadata_dirty', False), project=False, metadata=False)
                self.set_status("Project sidecar saved (photo untouched).")
                return True
        except Exception as e:
            if hasattr(self, 'winfo_exists'):
                try:
                    messagebox.showerror("Save Project Error", f"Failed to save project sidecar: {e}")
                except Exception:
                    pass
        return False

    def load_image(self, path):
        if not path:
            return False

        staged_rotation = 0

        # 1. Unsaved changes guard on departure (STAGED, transactional)
        pending_discard_departure = False
        if getattr(self, 'is_modified', False) and getattr(self, 'current_image_path', None):
            resp = messagebox.askyesnocancel(
                "Unsaved Changes",
                f"You have unsaved changes in '{os.path.basename(self.current_image_path)}'.\n\n"
                "• Click Yes to save before switching.\n"
                "• Click No to discard unsaved changes.\n"
                "• Click Cancel to remain on current photo."
            )
            if resp is None:  # Cancel -> Abort departure completely
                return False
            elif resp is True:  # Yes -> Save
                if not self.save_current():
                    return False
            else:  # No -> Stage discard for when incoming image successfully loads
                pending_discard_departure = True
                
        # 2. Stage incoming load in local variables.
        # DO NOT TOUCH current_image_path, faces, description, or original_pil_image until everything succeeds!
        try:
            import io
            with open(path, "rb") as f:
                img_data = f.read()
            staged_pil = Image.open(io.BytesIO(img_data))
            staged_pil.load()
            w, h = staged_pil.size
            
            # C1: Inspect canonical sidecar FIRST to establish blocked_sidecars protection
            sidecar_path = get_project_sidecar_path(path)
            canonical_doc = None
            if not hasattr(self, 'blocked_sidecars'):
                self.blocked_sidecars = set()
                
            if os.path.exists(sidecar_path):
                try:
                    canonical_doc = load_project_document(path, expected_dimensions=(w, h), actual_pil_img=staged_pil)
                    if canonical_doc and canonical_doc.extra and canonical_doc.extra.get('rotation'):
                        rot = canonical_doc.extra.get('rotation', 0)
                        if rot == 90:
                            staged_pil = staged_pil.transpose(Image.Transpose.ROTATE_270)
                        elif rot == 270:
                            staged_pil = staged_pil.transpose(Image.Transpose.ROTATE_90)
                        elif rot == 180:
                            staged_pil = staged_pil.transpose(Image.Transpose.ROTATE_180)
                        w, h = staged_pil.size
                        self._image_rotated = bool(rot)
                        staged_rotation = rot
                except CorruptProjectError as e:
                    backup_choice = messagebox.askyesnocancel(
                        "Corrupt Project File",
                        f"Warning: The project file for '{os.path.basename(path)}' is corrupt:\n{e}\n\n"
                        "• Click Yes to create a safety backup and recover tags from photo metadata.\n"
                        "• Click No to view read-only (saving sidecar blocked).\n"
                        "• Click Cancel to abort loading."
                    )
                    if backup_choice is None:
                        return False
                    elif backup_choice is True:
                        bak = backup_corrupt_sidecar(path)
                        if not bak:
                            messagebox.showerror("Backup Failed", "Failed to create safety backup of corrupt sidecar. Loading aborted to prevent data loss.")
                            return False
                    else:
                        self.blocked_sidecars.add(sidecar_path)
                except SchemaError as e:
                    schema_choice = messagebox.askyesno(
                        "Unsupported Schema",
                        f"Warning: {e}\n\n"
                        "Do you want to view the photo with embedded metadata read-only?\n"
                        "(Sidecar overwriting will be blocked)."
                    )
                    if not schema_choice:
                        return False
                    self.blocked_sidecars.add(sidecar_path)
                except ProjectIdentityMismatchError as e:
                    ident_choice = messagebox.askyesno(
                        "Image Mismatch",
                        f"Warning: {e}\n\n"
                        "The image content does not match the saved project. Read embedded metadata instead?"
                    )
                    if not ident_choice:
                        return False
                    self.blocked_sidecars.add(sidecar_path)

            # Check for recovery draft
            restored_from_draft = False
            staged_doc = None
            if has_draft(path):
                if messagebox.askyesno(
                    "Recover Draft",
                    f"An unsaved draft was found for '{os.path.basename(path)}'.\n\n"
                    "Would you like to recover this draft?",
                    parent=self,
                ):
                    try:
                        draft_doc = load_draft(path, expected_dimensions=(w, h), actual_pil_img=staged_pil)
                        if draft_doc:
                            staged_doc = draft_doc
                            restored_from_draft = True
                    except Exception as e:
                        messagebox.showwarning("Draft Error", f"Could not recover draft: {e}", parent=self)
                else:
                    discard_draft(path)
                    
            if not restored_from_draft:
                if canonical_doc is not None:
                    staged_doc = canonical_doc
                else:
                    # Read embedded metadata and assign stable UUIDs
                    imported_doc = import_from_image_metadata(path, width=w, height=h, actual_pil_img=staged_pil)
                    if not imported_doc.tags:
                        if hasattr(self, 'set_status') and callable(self.set_status):
                            self.set_status("Detecting faces in background...")
                        detected = detect_faces(path)
                        for d in detected:
                            d['id'] = str(uuid.uuid4())
                        imported_doc.tags = [
                            FaceTag(name=d.get('name', ''), x=d['x'], y=d['y'], w=d['w'], h=d['h'], tag_id=d['id'])
                            for d in detected
                        ]
                    staged_doc = imported_doc

            # Extract view state from staged_doc
            staged_faces = [t.to_dict() for t in staged_doc.tags]
            for f in staged_faces:
                if 'id' not in f or not f['id']:
                    f['id'] = str(uuid.uuid4())
            staged_faces = sort_faces_spatial(staged_faces)
            staged_desc = staged_doc.description
            staged_color = staged_doc.style.color_theme
            staged_size = staged_doc.style.font_size_preset
            staged_modified = restored_from_draft or (canonical_doc is None and bool(staged_faces))
            
            # --- 3. ALL STAGED OPERATIONS SUCCEEDED. COMMIT TRANSACTION TO APP STATE ---
            if pending_discard_departure and getattr(self, 'current_image_path', None):
                discard_draft(self.current_image_path)
                
            self._hydrating = True
            try:
                self.current_image_path = path
                self.original_pil_image = staged_pil
                self._image_rotation_angle = staged_rotation
                self._image_rotated = bool(staged_rotation)
                self.current_doc = staged_doc
                self.faces = staged_faces
                self.description = staged_desc
                self.selected_face_idx = None
                self.hovered_face_idx = None
                self.drawing = False
                self.zoom_factor = 1.0
                self.view_center_x = 0.5
                self.view_center_y = 0.5
                if hasattr(self, 'lbl_zoom_level'):
                    self.lbl_zoom_level.configure(text="Zoom: 100%")
                if hasattr(self, 'combo_format'):
                    self.combo_format.set("Format: Original")
                loaded_preset = getattr(staged_doc.style, 'preset_name', 'Classic')
                self.current_preset = loaded_preset
                if hasattr(self, 'combo_preset'):
                    self.combo_preset.set(loaded_preset)
                if hasattr(self, 'combo_style_color'):
                    self.combo_style_color.set(staged_color)
                    if hasattr(self, 'update_swatch_selection'):
                        self.update_swatch_selection(staged_color)
                    if hasattr(self, 'update_badge_shape_preview'):
                        self.update_badge_shape_preview()
                if hasattr(self, 'combo_style_font_size'):
                    self.combo_style_font_size.set(staged_size)
                    if hasattr(self, 'get_selected_font_size_style') and callable(self.get_selected_font_size_style):
                        style_info = self.get_selected_font_size_style()
                        scale_val = style_info["scale"]
                        self._badge_scale_factor = scale_val
                        if hasattr(self, 'slider_badge_scale'):
                            self.slider_badge_scale.set(scale_val)
                        if hasattr(self, 'lbl_scale_value'):
                            self.lbl_scale_value.configure(text=f"{scale_val:.2f}x")
                loaded_shape = getattr(staged_doc.style, 'badge_shape', 'auto')
                from models import normalize_badge_shape
                norm_shape = normalize_badge_shape(loaded_shape)
                if hasattr(self, 'combo_badge_shape'):
                    self.combo_badge_shape.set(self.shape_canonical_to_ui(norm_shape))
                if hasattr(self, 'seg_badge_shape'):
                    if norm_shape == "square":
                        self.seg_badge_shape.set("Square")
                    elif norm_shape == "rounded_square":
                        self.seg_badge_shape.set("Rounded")
                    else:
                        self.seg_badge_shape.set("Pill")
                loaded_font = getattr(staged_doc.style, 'font_family', 'Segoe UI') or 'Segoe UI'
                if loaded_font not in ("Segoe UI", "Tahoma", "Arial"):
                    loaded_font = "Segoe UI"
                if hasattr(self, 'combo_tag_font'):
                    self.combo_tag_font.set(loaded_font)
                if hasattr(self, 'seg_tag_font'):
                    self.seg_tag_font.set(loaded_font)
                if hasattr(self, 'lbl_font_sample'):
                    self.lbl_font_sample.configure(font=(loaded_font, 13))
                if hasattr(self, 'desc_textbox'):
                    self.desc_textbox.delete("1.0", "end")
                    if self.description:
                        self.desc_textbox.insert("1.0", self.description)
            finally:
                self._hydrating = False
                
            staged_is_project_dirty = False
            staged_is_metadata_dirty = False
            if restored_from_draft:
                rec = staged_doc.extra.pop('_recovery_state', None) if staged_doc.extra else None
                if rec and isinstance(rec, dict):
                    staged_is_project_dirty = bool(rec.get('is_project_dirty', True))
                    staged_is_metadata_dirty = bool(rec.get('is_metadata_dirty', True))
                elif staged_doc.extra and ('_dirty_project' in staged_doc.extra or '_dirty_metadata' in staged_doc.extra):
                    staged_is_project_dirty = bool(staged_doc.extra.pop('_dirty_project', True))
                    staged_is_metadata_dirty = bool(staged_doc.extra.pop('_dirty_metadata', True))
                else:
                    staged_is_project_dirty = True
                    staged_is_metadata_dirty = True
            elif canonical_doc is None and bool(staged_faces):
                staged_is_project_dirty = True
                staged_is_metadata_dirty = True

            self.is_project_dirty = staged_is_project_dirty
            self.is_metadata_dirty = staged_is_metadata_dirty
            self.is_modified = staged_is_project_dirty or staged_is_metadata_dirty
            if hasattr(self, '_sync_modified_status') and callable(self._sync_modified_status):
                self._sync_modified_status()
                
            if hasattr(self, 'lbl_photo_metadata') and staged_pil:
                try:
                    w, h = staged_pil.size
                    size_bytes = os.path.getsize(path)
                    if size_bytes >= 1024 * 1024:
                        size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
                    elif size_bytes >= 1024:
                        size_str = f"{size_bytes / 1024:.0f} KB"
                    else:
                        size_str = f"{size_bytes} B"
                    dpi = staged_pil.info.get('dpi')
                    if dpi and isinstance(dpi, (tuple, list)) and len(dpi) > 0 and dpi[0] and dpi[0] > 0:
                        dpi_str = f"{int(dpi[0])} DPI"
                    else:
                        dpi_str = "DPI unavailable"
                    self.lbl_photo_metadata.configure(text=f"{w} \u00d7 {h} px  \u2022  {size_str}  \u2022  {dpi_str}")
                except Exception:
                    pass
            if hasattr(self, 'update_swatch_selection'):
                self.update_swatch_selection()

            if hasattr(self, 'rebuild_sidebar') and callable(self.rebuild_sidebar):
                self.rebuild_sidebar()
            if hasattr(self, 'draw_canvas') and callable(self.draw_canvas):
                self.draw_canvas()
            if hasattr(self, 'update_navigation_controls') and callable(self.update_navigation_controls):
                self.update_navigation_controls()
            if hasattr(self, 'set_status') and callable(self.set_status):
                self.set_status(f"Loaded {os.path.basename(path)} successfully.")
            if hasattr(self, 'reflow_header') and callable(self.reflow_header):
                scale = self._get_window_scaling() if hasattr(self, '_get_window_scaling') else 1.0
                curr_w = self.winfo_width() / scale if self.winfo_width() > 1 else getattr(self, 'init_logical_w', 818)
                self.reflow_header(curr_w)
            return True
            
        except Exception as e:
            err_msg = str(e)
            win_err = getattr(e, 'winerror', None)
            is_cloud = (win_err in (1920, 433, 121, 5, 2) or
                        "cannot be accessed" in err_msg.lower() or
                        "device which does not exist" in err_msg.lower() or
                        "offline" in err_msg.lower() or
                        "google drive" in path.lower() or
                        "onedrive" in path.lower() or
                        (len(path) >= 3 and path[1:3] == ":\\" and path[0].upper() in ("G", "D", "E")))

            if is_cloud:
                user_msg = (
                    f"Cannot access cloud image:\n'{os.path.basename(path)}'\n\n"
                    f"Windows Error: {e}\n\n"
                    "Actionable Guidance:\n"
                    "• If this file is stored on Google Drive or OneDrive, ensure the cloud client is running and online.\n"
                    "• Right-click the file in Windows Explorer and choose 'Always keep on this device' (Available offline) before opening.\n"
                    "• Your current photo and any unsaved edits remain safe and untouched."
                )
            else:
                user_msg = (
                    f"Failed to open image:\n'{os.path.basename(path)}'\n\n"
                    f"Error: {e}\n\n"
                    "Your current photo and any unsaved edits remain safe and untouched."
                )

            if hasattr(self, 'winfo_exists'):
                try:
                    messagebox.showerror("File Access Error", user_msg)
                except Exception:
                    pass
            if hasattr(self, 'set_status') and callable(self.set_status):
                self.set_status(f"Could not open {os.path.basename(path)}: {e}")
            return False

    def draw_canvas(self):
        if not self.original_pil_image:
            return
            
        canvas_w = max(50, self.canvas.winfo_width())
        canvas_h = max(50, self.canvas.winfo_height())
        
        self.canvas.delete("overlay")
        
        mode = getattr(self, 'active_workspace_mode', 'tagging')
        selected_shape = self.get_selected_badge_shape()
        selected_tag_font = self.get_selected_tag_font()
        
        current_rev = getattr(self, 'render_revision', 0)
        current_preset = getattr(self, 'current_preset', 'Classic')

        # Handle Preview & Export mode (pure in-memory generation with unified styling)
        if mode == "preview":
            color_style = self.get_selected_color_style()
            rot_key = getattr(self, '_rotation_angle', 0)
            current_key = ("preview", self.current_image_path, canvas_w, canvas_h, self.zoom_factor, self.view_center_x, self.view_center_y, current_rev, current_preset, selected_shape, color_style["hex"], selected_tag_font, rot_key)
            if not hasattr(self, 'last_bg_key') or self.last_bg_key != current_key:
                self.last_bg_key = current_key
                self.canvas.delete("bg_image")
                font_style = self.get_selected_font_size_style()
                try:
                    img_source = self.original_pil_image if getattr(self, '_image_rotated', False) and self.original_pil_image is not None else self.current_image_path
                    pimg = draw_annotations_on_image(
                        img_source,
                        self.faces,
                        output_path=None, # Pure in-memory composite generation!
                        draw_names=True,
                        color_style=color_style,
                        font_size_style=font_style,
                        description=self.description,
                        for_editor=False,
                        style_preset=current_preset,
                        badge_shape=selected_shape,
                        font_family=selected_tag_font
                    )
                    if pimg and isinstance(pimg, Image.Image):
                        pw, ph = pimg.size
                        scale = min(canvas_w / pw, canvas_h / ph) * self.zoom_factor
                        disp_w = max(10, int(pw * scale))
                        disp_h = max(10, int(ph * scale))
                        resized_prev = pimg.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
                        self.tk_preview = ImageTk.PhotoImage(resized_prev)
                        self.canvas.create_image(canvas_w // 2, canvas_h // 2, image=self.tk_preview, anchor="center", tags="bg_image")
                        self.canvas.tag_lower("bg_image")
                    else:
                        self.canvas.create_text(canvas_w // 2, canvas_h // 2, text="⚠️ Preview generation error", fill="#f38ba8", font=("Segoe UI", 12, "bold"), tags="bg_image")
                except Exception as e:
                    self.canvas.create_text(canvas_w // 2, canvas_h // 2, text=f"⚠️ Preview generation error: {e}", fill="#f38ba8", font=("Segoe UI", 11, "bold"), tags="bg_image")
            return

        # Background caching check for normal image display (Tagging & Layout modes)
        current_key = ("normal", self.current_image_path, canvas_w, canvas_h, self.zoom_factor, self.view_center_x, self.view_center_y)
        if not hasattr(self, 'last_bg_key') or self.last_bg_key != current_key:
            self.last_bg_key = current_key
            self.canvas.delete("bg_image")
            
            orig_w, orig_h = self.original_pil_image.size
            base_scale = min(canvas_w / orig_w, canvas_h / orig_h)
            scale = base_scale * self.zoom_factor
            
            crop_w = min(orig_w, canvas_w / scale)
            crop_h = min(orig_h, canvas_h / scale)
            
            half_visible_w_norm = (crop_w / 2.0) / orig_w
            self.view_center_x = max(half_visible_w_norm, min(1.0 - half_visible_w_norm, self.view_center_x))
            half_visible_h_norm = (crop_h / 2.0) / orig_h
            self.view_center_y = max(half_visible_h_norm, min(1.0 - half_visible_h_norm, self.view_center_y))
            
            crop_left = self.view_center_x * orig_w - crop_w / 2.0
            crop_right = self.view_center_x * orig_w + crop_w / 2.0
            crop_top = self.view_center_y * orig_h - crop_h / 2.0
            crop_bottom = self.view_center_y * orig_h + crop_h / 2.0
            
            display_w = int(orig_w * scale) if orig_w * scale < canvas_w else canvas_w
            display_h = int(orig_h * scale) if orig_h * scale < canvas_h else canvas_h
            
            self.pad_x = (canvas_w - display_w) // 2
            self.pad_y = (canvas_h - display_h) // 2
            self.scale = scale
            
            cropped = self.original_pil_image.crop((crop_left, crop_top, crop_right, crop_bottom))
            resized_pil = cropped.resize((display_w, display_h), Image.Resampling.LANCZOS)
            self.tk_image = ImageTk.PhotoImage(resized_pil)
            
            self.canvas.create_image(canvas_w // 2, canvas_h // 2, image=self.tk_image, anchor="center", tags="bg_image")
            self.canvas.tag_lower("bg_image")
            
        color_style = self.get_selected_color_style()
        default_color = color_style["hex"]
        badge_text_color = color_style.get("text_color", "#ffffff")
        selected_color = "#818cf8"
        hover_color = "#f59e0b"
        
        font_style = self.get_selected_font_size_style()
        orig_w, orig_h = self.original_pil_image.size
        # Unified badge metrics scaling proportionally with canvas view and font style
        r_img = get_badge_radius(orig_w, orig_h, font_style)
        base_badge_r = max(11, int(r_img * self.scale))
        
        # Unified default positions from shared metadata engine
        default_positions = compute_default_badge_positions(self.faces, orig_w, orig_h, font_style, badge_shape=selected_shape)

        if mode == "tagging":
            # Tagging Mode: Draw interactive bounding boxes with corner handles and label pills
            for idx, face in enumerate(self.faces):
                cx, cy = self.normalized_to_canvas(face['x'] - face['w']/2.0, face['y'] - face['h']/2.0)
                w_px, h_px = self.normalized_size_to_canvas(face['w'], face['h'])
                
                if idx == self.selected_face_idx:
                    outline_color = selected_color
                    box_width = 3
                elif idx == self.hovered_face_idx:
                    outline_color = hover_color
                    box_width = 3
                else:
                    outline_color = default_color
                    box_width = 2
                    
                self.canvas.create_rectangle(cx, cy, cx + w_px, cy + h_px, outline=outline_color, width=box_width, tags="overlay")
                
                if idx == self.selected_face_idx:
                    handle_size = 6
                    corners = [
                        (cx, cy), (cx + w_px, cy),
                        (cx, cy + h_px), (cx + w_px, cy + h_px)
                    ]
                    for hx, hy in corners:
                        self.canvas.create_rectangle(
                            hx - handle_size/2, hy - handle_size/2,
                            hx + handle_size/2, hy + handle_size/2,
                            fill=selected_color, outline="white", width=1, tags="overlay"
                        )
                
                # Draw number badge pill/circle at top-left
                badge_x = cx + 12
                badge_y = cy - 12 if cy - 12 > 12 else cy + 12
                draw_canvas_badge(self.canvas, badge_x, badge_y, str(idx + 1), base_badge_r, default_color, text_color=badge_text_color, badge_shape=selected_shape, tags=("overlay", f"badge_{idx}"), font_family=selected_tag_font, style_preset=getattr(self, 'current_preset', 'Classic'))

                # Draw name label if present (with high-contrast dark backing for pale portraits)
                name = face['name'].strip() if face['name'] else ""
                if name:
                    display_name = shape_persian_arabic_text(name)
                    lbl_x = badge_x + base_badge_r + 6
                    txt_id = self.canvas.create_text(
                        lbl_x, badge_y, 
                        text=display_name, 
                        fill="#f8fafc", 
                        font=(selected_tag_font, 9, "bold"), 
                        anchor="w", 
                        tags="overlay"
                    )
                    bbox = self.canvas.bbox(txt_id)
                    if bbox:
                        pad_x, pad_y = 6, 2
                        bg_rect = self.canvas.create_rectangle(
                            bbox[0] - pad_x, bbox[1] - pad_y,
                            bbox[2] + pad_x, bbox[3] + pad_y,
                            fill="#0f111a", outline="#31384e", width=1, tags="overlay"
                        )
                        self.canvas.tag_raise(txt_id, bg_rect)

        elif mode == "layout":
            # Layout (Badges) Mode: Draw photo with draggable badge pills and anchor lines
            for idx, face in enumerate(self.faces):
                # Face box center
                fcx, fcy = self.normalized_to_canvas(face['x'], face['y'])
                
                # Badge position (fine-tuned bx, by or unified default from metadata engine!)
                if face.get('bx') is not None and face.get('by') is not None:
                    bx_norm, by_norm = face['bx'], face['by']
                elif idx < len(default_positions):
                    bx_norm, by_norm = default_positions[idx]
                else:
                    bx_norm, by_norm = face['x'], face['y'] - face['h']/2.0 - 0.03
                    
                bcx, bcy = self.normalized_to_canvas(bx_norm, by_norm)
                
                is_sel = (idx == self.selected_face_idx)
                is_drag = (idx == getattr(self, 'dragging_badge_idx', None))
                line_color = selected_color if (is_sel or is_drag) else "#89b4fa"
                
                # Anchor line
                self.canvas.create_line(fcx, fcy, bcx, bcy, fill=line_color, width=1.5, dash=(4, 3), tags=("overlay", "anchor_line"))
                self.canvas.create_oval(fcx - 3, fcy - 3, fcx + 3, fcy + 3, fill=line_color, outline="white", width=1, tags=("overlay", "anchor_dot"))
                
                # Selection halo ring while keeping chosen fill visible
                if is_sel or is_drag:
                    ring_r = base_badge_r + 4
                    if selected_shape == "square":
                        self.canvas.create_rectangle(bcx - ring_r, bcy - ring_r, bcx + ring_r, bcy + ring_r, outline=selected_color, width=2, tags="overlay")
                    else:
                        self.canvas.create_oval(bcx - ring_r, bcy - ring_r, bcx + ring_r, bcy + ring_r, outline=selected_color, width=2, tags="overlay")

                # Draw circle-to-pill badge (chosen fill remains visible!)
                badge_fill = default_color
                draw_canvas_badge(self.canvas, bcx, bcy, str(idx + 1), base_badge_r, badge_fill, text_color=badge_text_color, badge_shape=selected_shape, tags=("overlay", "badge_element", f"badge_{idx}"), font_family=selected_tag_font, style_preset=getattr(self, 'current_preset', 'Classic'))

        # Footer description overlay on canvas if present
        if self.mouse_in_canvas and self.hovered_face_idx is None and self.description and mode != "preview":
            overlay_h = 32
            self.canvas.create_rectangle(0, canvas_h - overlay_h, canvas_w, canvas_h, fill="#181825", outline="#313244", width=1, tags="overlay")
            self.canvas.create_text(15, canvas_h - overlay_h // 2, text=f"💬 {self.description}", fill="#cdd6f4", font=("Segoe UI", 9.5), anchor="w", tags="overlay")

    def rebuild_sidebar(self):
        for widget in self.faces_scroll.winfo_children():
            widget.destroy()

        self.face_images = []
        self.face_entries = []

        if hasattr(self, 'faces_header'):
            self.faces_header.configure(text=f"People ({len(self.faces)})")
        if hasattr(self, 'update_details_view'):
            self.update_details_view()

        if not self.original_pil_image:
            return

        orig_w, orig_h = self.original_pil_image.size

        for idx, face in enumerate(self.faces):
            is_selected = (idx == self.selected_face_idx)
            card_frame = ctk.CTkFrame(
                self.faces_scroll,
                fg_color="#313244" if is_selected else "#252536",
                border_width=1,
                border_color="#89b4fa" if is_selected else "#313244",
                corner_radius=6
            )
            card_frame.pack(fill="x", padx=4, pady=3)
            card_frame.grid_columnconfigure(0, weight=0) # Number badge pill
            card_frame.grid_columnconfigure(1, weight=0) # Thumbnail
            card_frame.grid_columnconfigure(2, weight=1) # Entry & UUID
            card_frame.grid_columnconfigure(3, weight=0) # Delete button

            # Number badge pill
            lbl_num = ctk.CTkLabel(
                card_frame, 
                text=f"#{idx + 1}", 
                font=("Segoe UI", 12, "bold"), 
                width=24, 
                height=22,
                fg_color="#181825",
                text_color="#89b4fa",
                corner_radius=4
            )
            lbl_num.grid(row=0, column=0, padx=(8, 4), pady=(6, 2))
            lbl_num.bind("<Button-1>", lambda event, i=idx: self.select_face(i))

            # Crop thumbnail
            left = max(0, min(orig_w, int((face['x'] - face['w'] / 2.0) * orig_w)))
            top = max(0, min(orig_h, int((face['y'] - face['h'] / 2.0) * orig_h)))
            right = max(0, min(orig_w, int((face['x'] + face['w'] / 2.0) * orig_w)))
            bottom = max(0, min(orig_h, int((face['y'] + face['h'] / 2.0) * orig_h)))

            thumbnail_label = None
            if right > left and bottom > top:
                try:
                    cropped = self.original_pil_image.crop((left, top, right, bottom))
                    cropped = cropped.resize((36, 36), Image.Resampling.LANCZOS)
                    ctk_thumb = ctk.CTkImage(light_image=cropped, dark_image=cropped, size=(36, 36))
                    self.face_images.append(ctk_thumb)
                    thumbnail_label = ctk.CTkLabel(card_frame, image=ctk_thumb, text="")
                    thumbnail_label.grid(row=0, column=1, padx=(2, 6), pady=(6, 2))
                except Exception as e:
                    print("Error cropping thumbnail:", e)

            if not thumbnail_label:
                thumbnail_label = ctk.CTkLabel(card_frame, text="👤", font=("Segoe UI", 18))
                thumbnail_label.grid(row=0, column=1, padx=(2, 6), pady=(6, 2))

            thumbnail_label.bind("<Button-1>", lambda event, i=idx: self.select_face(i))

            # Header label in top row
            lbl_person = ctk.CTkLabel(
                card_frame,
                text=f"Person #{idx + 1}",
                font=("Segoe UI", 12, "bold"),
                text_color="#cdd6f4" if is_selected else "#a6adc8",
                anchor="w"
            )
            lbl_person.grid(row=0, column=2, sticky="w", padx=2, pady=(6, 2))
            lbl_person.bind("<Button-1>", lambda event, i=idx: self.select_face(i))

            # Delete button in top row
            btn_delete = ctk.CTkButton(
                card_frame, 
                text="✕", 
                width=22, 
                height=22, 
                fg_color="transparent", 
                hover_color="#45475a", 
                text_color="#f38ba8", 
                font=("Segoe UI", 12, "bold"), 
                corner_radius=4,
                command=lambda i=idx: self.delete_face(i)
            )
            btn_delete.grid(row=0, column=3, sticky="e", padx=(4, 8), pady=(6, 2))

            # Dedicated full-width edit row (Row 1, columns 0-3) for person name
            var = tk.StringVar(value=face['name'])
            var.trace_add("write", lambda *args, i=idx, v=var: self.on_name_changed(i, v))

            entry = ctk.CTkEntry(
                card_frame, 
                textvariable=var, 
                placeholder_text="Enter name...", 
                font=("Segoe UI", 13),
                fg_color="#181825",
                text_color="#cdd6f4",
                border_width=1,
                border_color="#45475a",
                height=28,
                corner_radius=4
            )
            entry.grid(row=1, column=0, columnspan=4, sticky="ew", padx=8, pady=(2, 8))
            entry.bind("<FocusIn>", lambda event, i=idx: self.select_face(i))
            self.face_entries.append(entry)

            # Stable UUID preserved in internal state, hidden from routine tagging UI
            pass

    def canvas_to_normalized(self, cx, cy):
        """
        Converts canvas coordinate (cx, cy) to normalized image coordinate (nx, ny).
        Returns (None, None) if the coordinate is outside the display boundaries.
        """
        if not self.original_pil_image:
            return None, None
            
        canvas_w = max(50, self.canvas.winfo_width())
        canvas_h = max(50, self.canvas.winfo_height())
        orig_w, orig_h = self.original_pil_image.size
        
        base_scale = min(canvas_w / orig_w, canvas_h / orig_h)
        scale = base_scale * self.zoom_factor
        
        crop_w = min(orig_w, canvas_w / scale)
        crop_h = min(orig_h, canvas_h / scale)
        
        crop_left = self.view_center_x * orig_w - crop_w / 2.0
        crop_top = self.view_center_y * orig_h - crop_h / 2.0
        
        display_w = int(orig_w * scale) if orig_w * scale < canvas_w else canvas_w
        display_h = int(orig_h * scale) if orig_h * scale < canvas_h else canvas_h
        
        pad_x = (canvas_w - display_w) // 2
        pad_y = (canvas_h - display_h) // 2
        
        px_x = cx - pad_x
        px_y = cy - pad_y
        
        if px_x < 0 or px_x > display_w or px_y < 0 or px_y > display_h:
            return None, None
            
        orig_pixel_x = crop_left + (px_x / display_w) * crop_w
        orig_pixel_y = crop_top + (px_y / display_h) * crop_h
        
        nx = orig_pixel_x / orig_w
        ny = orig_pixel_y / orig_h
        
        nx = max(0.0, min(1.0, nx))
        ny = max(0.0, min(1.0, ny))
        return nx, ny

    def normalized_to_canvas(self, nx, ny):
        """
        Converts normalized image coordinate (nx, ny) to canvas coordinate (cx, cy).
        """
        if not self.original_pil_image:
            return 0, 0
            
        canvas_w = max(50, self.canvas.winfo_width())
        canvas_h = max(50, self.canvas.winfo_height())
        orig_w, orig_h = self.original_pil_image.size
        
        base_scale = min(canvas_w / orig_w, canvas_h / orig_h)
        scale = base_scale * self.zoom_factor
        
        crop_w = min(orig_w, canvas_w / scale)
        crop_h = min(orig_h, canvas_h / scale)
        
        crop_left = self.view_center_x * orig_w - crop_w / 2.0
        crop_top = self.view_center_y * orig_h - crop_h / 2.0
        
        display_w = int(orig_w * scale) if orig_w * scale < canvas_w else canvas_w
        display_h = int(orig_h * scale) if orig_h * scale < canvas_h else canvas_h
        
        pad_x = (canvas_w - display_w) // 2
        pad_y = (canvas_h - display_h) // 2
        
        cx = pad_x + ((nx * orig_w - crop_left) / crop_w) * display_w
        cy = pad_y + ((ny * orig_h - crop_top) / crop_h) * display_h
        return cx, cy

    def normalized_size_to_canvas(self, nw, nh):
        """
        Converts normalized width and height to canvas pixel dimensions.
        """
        if not self.original_pil_image:
            return 0, 0
            
        canvas_w = max(50, self.canvas.winfo_width())
        canvas_h = max(50, self.canvas.winfo_height())
        orig_w, orig_h = self.original_pil_image.size
        
        base_scale = min(canvas_w / orig_w, canvas_h / orig_h)
        scale = base_scale * self.zoom_factor
        
        crop_w = min(orig_w, canvas_w / scale)
        crop_h = min(orig_h, canvas_h / scale)
        
        display_w = int(orig_w * scale) if orig_w * scale < canvas_w else canvas_w
        display_h = int(orig_h * scale) if orig_h * scale < canvas_h else canvas_h
        
        cw = (nw * orig_w / crop_w) * display_w
        ch = (nh * orig_h / crop_h) * display_h
        return cw, ch

    def get_resize_handle(self, event_x, event_y):
        if self.selected_face_idx is None or not self.original_pil_image:
            return None
            
        face = self.faces[self.selected_face_idx]
        cx, cy = self.normalized_to_canvas(face['x'] - face['w']/2.0, face['y'] - face['h']/2.0)
        w_px, h_px = self.normalized_size_to_canvas(face['w'], face['h'])
        
        x1, y1 = cx, cy
        x2, y2 = cx + w_px, cy + h_px
        
        tol = 8  # Hit tolerance in pixels
        
        # Check corners first
        if abs(event_x - x1) <= tol and abs(event_y - y1) <= tol:
            return "nw"
        if abs(event_x - x2) <= tol and abs(event_y - y1) <= tol:
            return "ne"
        if abs(event_x - x1) <= tol and abs(event_y - y2) <= tol:
            return "sw"
        if abs(event_x - x2) <= tol and abs(event_y - y2) <= tol:
            return "se"
            
        # Check edges
        if x1 - tol <= event_x <= x2 + tol and abs(event_y - y1) <= tol:
            return "n"
        if x1 - tol <= event_x <= x2 + tol and abs(event_y - y2) <= tol:
            return "s"
        if abs(event_x - x1) <= tol and y1 - tol <= event_y <= y2 + tol:
            return "w"
        if abs(event_x - x2) <= tol and y1 - tol <= event_y <= y2 + tol:
            return "e"
            
        return None

    def handle_resize_drag(self, event):
        face = self.resize_face_init
        cx, cy = self.normalized_to_canvas(face['x'] - face['w']/2.0, face['y'] - face['h']/2.0)
        w_px, h_px = self.normalized_size_to_canvas(face['w'], face['h'])
        
        x1, y1 = cx, cy
        x2, y2 = cx + w_px, cy + h_px
        
        dx = event.x - self.resize_start_x
        dy = event.y - self.resize_start_y
        
        # Apply delta
        if "w" in self.resize_handle:
            x1 += dx
        if "e" in self.resize_handle:
            x2 += dx
        if "n" in self.resize_handle:
            y1 += dy
        if "s" in self.resize_handle:
            y2 += dy
            
        # Impose min size (15 pixels)
        min_size = 15
        if x2 - x1 < min_size:
            if "w" in self.resize_handle:
                x1 = x2 - min_size
            else:
                x2 = x1 + min_size
        if y2 - y1 < min_size:
            if "n" in self.resize_handle:
                y1 = y2 - min_size
            else:
                y2 = y1 + min_size
                
        # Map back to normalized
        nx1, ny1 = self.canvas_to_normalized(x1, y1)
        nx2, ny2 = self.canvas_to_normalized(x2, y2)
        
        if nx1 is not None and nx2 is not None:
            new_w = abs(nx2 - nx1)
            new_h = abs(ny2 - ny1)
            new_x = (nx1 + nx2) / 2.0
            new_y = (ny1 + ny2) / 2.0
            
            self.faces[self.selected_face_idx]['x'] = new_x
            self.faces[self.selected_face_idx]['y'] = new_y
            self.faces[self.selected_face_idx]['w'] = new_w
            self.faces[self.selected_face_idx]['h'] = new_h
            self.set_modified(True)
            
            self.draw_canvas()

    def get_selected_color_style(self):
        val = self.combo_style_color.get() if hasattr(self, 'combo_style_color') else "Teal"
        return get_canonical_color_style(val)

    def get_selected_font_size_style(self):
        font_size_map = {
            "Micro (0.5x)": {"scale": 0.5, "px": 8},
            "Small (0.7x)": {"scale": 0.7, "px": 10},
            "Auto (1.0x)": {"scale": 1.0, "px": 13},
            "Medium (1.2x)": {"scale": 1.2, "px": 16},
            "Large (1.5x)": {"scale": 1.5, "px": 20},
            "X-Large (2.0x)": {"scale": 2.0, "px": 26}
        }
        val = self.combo_style_font_size.get() if hasattr(self, 'combo_style_font_size') else "Auto (1.0x)"
        if val in font_size_map:
            return font_size_map[val]

        import re
        m = re.search(r'([\d\.]+)x?', str(val))
        if m:
            try:
                scale = float(m.group(1))
            except ValueError:
                scale = 1.0
        elif hasattr(self, '_badge_scale_factor') and self._badge_scale_factor is not None:
            scale = float(self._badge_scale_factor)
        else:
            scale = 1.0
        px = max(8, int(round(13 * scale)))
        return {"scale": scale, "px": px}

    # ----------------------------------------------------
    # Canvas Event Handlers
    # ----------------------------------------------------
    def on_canvas_resize(self, event):
        self.draw_canvas()
        
    def on_canvas_press(self, event):
        if not self.original_pil_image:
            return
            
        if getattr(self, 'active_tool_mode', 'select') == 'pan' or self.is_pan_mode:
            self.on_pan_press(event)
            return

        # Layout Mode: check if clicked on a badge to initiate drag
        if getattr(self, 'active_workspace_mode', 'tagging') == 'layout':
            items = list(self.canvas.find_overlapping(event.x - 14, event.y - 14, event.x + 14, event.y + 14))
            for item in items:
                tags = self.canvas.gettags(item)
                for t in tags:
                    if t.startswith("badge_") and not t == "badge_element":
                        try:
                            b_idx = int(t.split("_")[1])
                            self.dragging_badge_idx = b_idx
                            self.select_face(b_idx)
                            return
                        except Exception:
                            pass
            return
            
        # Check if clicked on a resize handle first
        if hasattr(self, 'hovered_resize_handle') and self.hovered_resize_handle is not None:
            self.resizing = True
            self.resize_handle = self.hovered_resize_handle
            self.resize_start_x = event.x
            self.resize_start_y = event.y
            self.resize_face_init = self.faces[self.selected_face_idx].copy()
            return
            
        # Get coordinates in normalized form
        nx, ny = self.canvas_to_normalized(event.x, event.y)
        
        if nx is not None and ny is not None:
            # Check if clicked on an existing face box
            clicked_idx = self.get_face_at_coords(nx, ny)
            
            if clicked_idx is not None:
                # Select the face and focus the corresponding entry widget
                self.select_face(clicked_idx)
                if clicked_idx < len(self.face_entries):
                    self.face_entries[clicked_idx].focus_set()
            else:
                # Start drawing a manual bounding box
                self.drawing = True
                self.draw_start_x = event.x
                self.draw_start_y = event.y
                self.draw_current_x = event.x
                self.draw_current_y = event.y
                
                # Deselect face without heavy sidebar rebuild during drag initialization
                if self.selected_face_idx is not None:
                    self.selected_face_idx = None
                    self.draw_canvas()
                
                # Delete any old drag rect items and create high-contrast live manual drag cadre
                self.canvas.delete("manual_drag_rect")
                self.drag_rect_bg = self.canvas.create_rectangle(
                    event.x, event.y, event.x, event.y,
                    outline="#000000", width=4, tags="manual_drag_rect"
                )
                self.drag_rect_fg = self.canvas.create_rectangle(
                    event.x, event.y, event.x, event.y,
                    outline="#38bdf8", width=2, tags="manual_drag_rect"
                )
                self.canvas.tag_raise("manual_drag_rect")
                
    def on_canvas_drag(self, event):
        if not self.original_pil_image:
            return
            
        if getattr(self, 'active_tool_mode', 'select') == 'pan' or self.is_pan_mode:
            self.on_pan_drag(event)
            return

        # Layout Mode: drag badge and update bx, by
        if getattr(self, 'active_workspace_mode', 'tagging') == 'layout':
            if getattr(self, 'dragging_badge_idx', None) is not None and self.dragging_badge_idx < len(self.faces):
                nx, ny = self.canvas_to_normalized(event.x, event.y)
                if nx is not None and ny is not None:
                    nx = max(0.01, min(0.99, nx))
                    ny = max(0.01, min(0.99, ny))
                    self.faces[self.dragging_badge_idx]['bx'] = nx
                    self.faces[self.dragging_badge_idx]['by'] = ny
                    self.set_modified(True, project=True, metadata=False)
                    self.draw_canvas()
                return
            
        if hasattr(self, 'resizing') and self.resizing:
            self.handle_resize_drag(event)
            return
            
        if not self.drawing:
            return
            
        # Constrain dragging coordinates to the canvas image bounds
        canvas_w = max(50, self.canvas.winfo_width())
        canvas_h = max(50, self.canvas.winfo_height())
        orig_w, orig_h = self.original_pil_image.size
        base_scale = min(canvas_w / orig_w, canvas_h / orig_h)
        scale = base_scale * self.zoom_factor
        display_w = int(orig_w * scale) if orig_w * scale < canvas_w else canvas_w
        display_h = int(orig_h * scale) if orig_h * scale < canvas_h else canvas_h
        
        self.draw_current_x = max(self.pad_x, min(self.pad_x + display_w, event.x))
        self.draw_current_y = max(self.pad_y, min(self.pad_y + display_h, event.y))
        
        # Ensure manual drag rect items exist and update coordinates smoothly without lag
        if not hasattr(self, 'drag_rect_fg') or self.drag_rect_fg is None or not self.canvas.find_withtag("manual_drag_rect"):
            self.drag_rect_bg = self.canvas.create_rectangle(
                self.draw_start_x, self.draw_start_y, self.draw_current_x, self.draw_current_y,
                outline="#000000", width=4, tags="manual_drag_rect"
            )
            self.drag_rect_fg = self.canvas.create_rectangle(
                self.draw_start_x, self.draw_start_y, self.draw_current_x, self.draw_current_y,
                outline="#38bdf8", width=2, tags="manual_drag_rect"
            )
        else:
            self.canvas.coords(self.drag_rect_bg, self.draw_start_x, self.draw_start_y, self.draw_current_x, self.draw_current_y)
            self.canvas.coords(self.drag_rect_fg, self.draw_start_x, self.draw_start_y, self.draw_current_x, self.draw_current_y)
            
        self.canvas.tag_raise("manual_drag_rect")
        
    def on_canvas_release(self, event):
        if getattr(self, 'active_tool_mode', 'select') == 'pan' or self.is_pan_mode:
            self.on_pan_release(event)
            return

        if getattr(self, 'active_workspace_mode', 'tagging') == 'layout':
            if getattr(self, 'dragging_badge_idx', None) is not None:
                self.dragging_badge_idx = None
                return
        if hasattr(self, 'resizing') and self.resizing:
            self.resizing = False
            self.rebuild_sidebar()
            self.draw_canvas()
            return
            
        if not self.drawing:
            return
            
        self.drawing = False
        
        # Delete temporary manual drag cadre
        self.canvas.delete("manual_drag_rect")
        self.drag_rect_bg = None
        self.drag_rect_fg = None
            
        # Calculate width and height in pixels
        w_px = abs(self.draw_current_x - self.draw_start_x)
        h_px = abs(self.draw_current_y - self.draw_start_y)
        
        # Only create a box if it is reasonably sized (e.g. at least 15 pixels)
        if w_px > 15 and h_px > 15:
            # Map start/end pixels to normalized coords
            nx1, ny1 = self.canvas_to_normalized(self.draw_start_x, self.draw_start_y)
            nx2, ny2 = self.canvas_to_normalized(self.draw_current_x, self.draw_current_y)
            
            if nx1 is not None and nx2 is not None:
                # Compute normalized center coordinates
                cx = (nx1 + nx2) / 2.0
                cy = (ny1 + ny2) / 2.0
                nw = abs(nx2 - nx1)
                nh = abs(ny2 - ny1)
                
                # Add to faces list
                new_face = {
                    'name': '',
                    'x': cx,
                    'y': cy,
                    'w': nw,
                    'h': nh
                }
                self.faces.append(new_face)
                self.sort_faces()
                self.set_modified(True)
                
                # Auto-select the newly created face
                self.selected_face_idx = len(self.faces) - 1
                self.rebuild_sidebar()
                self.draw_canvas()
                
                # Focus on the newly created name entry
                if self.selected_face_idx < len(self.face_entries):
                    self.face_entries[self.selected_face_idx].focus_set()
        else:
            # Clear selection if it was a tiny/invalid drag
            self.selected_face_idx = None
            self.rebuild_sidebar()
            self.draw_canvas()
            
    def on_canvas_motion(self, event):
        if not self.original_pil_image or self.drawing:
            return
            
        if hasattr(self, 'resizing') and self.resizing:
            return
            
        self.mouse_in_canvas = True
        self.mouse_x = event.x
        self.mouse_y = event.y
        
        # Check resizing hover handles first if a face is selected
        handle = self.get_resize_handle(event.x, event.y)
        if handle:
            cursor_map = {
                "nw": "size_nw_se",
                "se": "size_nw_se",
                "ne": "size_ne_sw",
                "sw": "size_ne_sw",
                "n": "size_ns",
                "s": "size_ns",
                "w": "size_we",
                "e": "size_we"
            }
            self.canvas.configure(cursor=cursor_map[handle])
            self.hovered_resize_handle = handle
            
            # Reset hovered face selection so tooltips don't draw while preparing to resize
            if self.hovered_face_idx is not None:
                self.hovered_face_idx = None
                self.draw_canvas()
            return
        else:
            self.canvas.configure(cursor="hand2" if self.is_pan_mode else "")
            self.hovered_resize_handle = None
            
        # Calculate position in normalized coordinates
        nx, ny = self.canvas_to_normalized(event.x, event.y)
        
        prev_hovered = self.hovered_face_idx
        if nx is not None and ny is not None:
            self.hovered_face_idx = self.get_face_at_coords(nx, ny)
        else:
            self.hovered_face_idx = None
        
        # Redraw if hover target changed, or if there is an active hovered face
        # (so the tooltip follows the mouse), or if description is present
        if self.hovered_face_idx is not None or self.hovered_face_idx != prev_hovered or self.description:
            self.draw_canvas()

    # ----------------------------------------------------
    # Zooming & Panning Handlers
    # ----------------------------------------------------
    def zoom_in(self):
        if not self.original_pil_image:
            return
        self.zoom_factor = min(10.0, self.zoom_factor + 0.2)
        self.lbl_zoom_level.configure(text=f"Zoom: {int(self.zoom_factor * 100)}%")
        self.draw_canvas()

    def zoom_out(self):
        if not self.original_pil_image:
            return
        self.zoom_factor = max(1.0, self.zoom_factor - 0.2)
        self.lbl_zoom_level.configure(text=f"Zoom: {int(self.zoom_factor * 100)}%")
        self.draw_canvas()

    def zoom_reset(self):
        if not self.original_pil_image:
            return
        self.zoom_factor = 1.0
        self.view_center_x = 0.5
        self.view_center_y = 0.5
        self.lbl_zoom_level.configure(text="Zoom: 100%")
        self.draw_canvas()

    def on_mouse_zoom(self, event):
        if not self.original_pil_image:
            return
            
        # Get coordinates in normalized form before changing zoom
        canvas_w = max(50, self.canvas.winfo_width())
        canvas_h = max(50, self.canvas.winfo_height())
        orig_w, orig_h = self.original_pil_image.size
        
        nx, ny = self.canvas_to_normalized(event.x, event.y)
        if nx is None or ny is None:
            return
            
        # Change zoom factor
        old_zoom = self.zoom_factor
        if event.delta > 0:
            self.zoom_factor = min(10.0, self.zoom_factor + 0.2)
        else:
            self.zoom_factor = max(1.0, self.zoom_factor - 0.2)
            
        if self.zoom_factor == old_zoom:
            return
            
        # Reposition viewport center around mouse coordinates
        base_scale = min(canvas_w / orig_w, canvas_h / orig_h)
        scale_new = base_scale * self.zoom_factor
        crop_w_new = min(orig_w, canvas_w / scale_new)
        crop_h_new = min(orig_h, canvas_h / scale_new)
        
        if scale_new * orig_w >= canvas_w:
            crop_left_new = nx * orig_w - event.x / scale_new
            self.view_center_x = (crop_left_new + crop_w_new / 2.0) / orig_w
        else:
            self.view_center_x = 0.5
            
        if scale_new * orig_h >= canvas_h:
            crop_top_new = ny * orig_h - event.y / scale_new
            self.view_center_y = (crop_top_new + crop_h_new / 2.0) / orig_h
        else:
            self.view_center_y = 0.5
            
        # Clamp view center so crop box stays inside image
        half_visible_w_norm = (crop_w_new / 2.0) / orig_w
        self.view_center_x = max(half_visible_w_norm, min(1.0 - half_visible_w_norm, self.view_center_x))
        
        half_visible_h_norm = (crop_h_new / 2.0) / orig_h
        self.view_center_y = max(half_visible_h_norm, min(1.0 - half_visible_h_norm, self.view_center_y))
        
        self.lbl_zoom_level.configure(text=f"Zoom: {int(self.zoom_factor * 100)}%")
        self.draw_canvas()

    def on_mouse_zoom_linux(self, event, scroll_up):
        # Mock delta for Linux scrolling
        event.delta = 120 if scroll_up else -120
        self.on_mouse_zoom(event)

    def toggle_pan_mode(self):
        self.is_pan_mode = not self.is_pan_mode
        if self.is_pan_mode:
            self.btn_pan_mode.configure(fg_color="#0284c7", hover_color="#0369a1", text_color="#ffffff", text="🖐️ Pan Active")
            self.canvas.configure(cursor="fleur")
            self.set_status("Pan Tool active: Left-Click & drag to pan photo, or click ◀▲▼▶ arrows.")
        else:
            self.btn_pan_mode.configure(fg_color="#313244", hover_color="#45475a", text_color="#cdd6f4", text="🖐️ Pan Tool")
            self.canvas.configure(cursor="hand2" if self.is_pan_mode else "")
            self.set_status("Tagging Tool active: Click & drag on photo to tag faces.")

    def pan_step(self, direction):
        if not self.original_pil_image:
            return
        step = 0.08 / max(1.0, float(self.zoom_factor))
        if direction == "left":
            self.view_center_x -= step
        elif direction == "right":
            self.view_center_x += step
        elif direction == "up":
            self.view_center_y -= step
        elif direction == "down":
            self.view_center_y += step
            
        # Clamp view center so crop box stays inside image
        canvas_w = max(50, self.canvas.winfo_width())
        canvas_h = max(50, self.canvas.winfo_height())
        orig_w, orig_h = self.original_pil_image.size
        base_scale = min(canvas_w / orig_w, canvas_h / orig_h)
        scale = base_scale * self.zoom_factor
        
        crop_w = min(orig_w, canvas_w / scale)
        crop_h = min(orig_h, canvas_h / scale)
        
        half_visible_w_norm = (crop_w / 2.0) / orig_w
        self.view_center_x = max(half_visible_w_norm, min(1.0 - half_visible_w_norm, self.view_center_x))
        
        half_visible_h_norm = (crop_h / 2.0) / orig_h
        self.view_center_y = max(half_visible_h_norm, min(1.0 - half_visible_h_norm, self.view_center_y))
        
        self.draw_canvas()

    def on_pan_press(self, event):
        if not self.original_pil_image:
            return
        self.pan_start_x = event.x
        self.pan_start_y = event.y
        self.canvas.configure(cursor="fleur")

    def on_pan_drag(self, event):
        if not self.original_pil_image:
            return
            
        canvas_w = max(50, self.canvas.winfo_width())
        canvas_h = max(50, self.canvas.winfo_height())
        orig_w, orig_h = self.original_pil_image.size
        base_scale = min(canvas_w / orig_w, canvas_h / orig_h)
        scale = base_scale * self.zoom_factor
        
        dx = event.x - self.pan_start_x
        dy = event.y - self.pan_start_y
        
        self.view_center_x -= (dx / scale) / orig_w
        self.view_center_y -= (dy / scale) / orig_h
        
        crop_w = min(orig_w, canvas_w / scale)
        crop_h = min(orig_h, canvas_h / scale)
        
        half_visible_w_norm = (crop_w / 2.0) / orig_w
        self.view_center_x = max(half_visible_w_norm, min(1.0 - half_visible_w_norm, self.view_center_x))
        
        half_visible_h_norm = (crop_h / 2.0) / orig_h
        self.view_center_y = max(half_visible_h_norm, min(1.0 - half_visible_h_norm, self.view_center_y))
        
        self.pan_start_x = event.x
        self.pan_start_y = event.y
        
        self.draw_canvas()

    def on_pan_release(self, event):
        self.canvas.configure(cursor="hand2" if self.is_pan_mode else "")
            
    def on_canvas_leave(self, event):
        self.mouse_in_canvas = False
        self.hovered_resize_handle = None
        self.canvas.configure(cursor="hand2" if self.is_pan_mode else "")
        if self.hovered_face_idx is not None:
            self.hovered_face_idx = None
            self.draw_canvas()
            
    def get_face_at_coords(self, nx, ny):
        """
        Returns the index of the face box containing coordinates (nx, ny).
        Checks smaller boxes first for precision in nested coordinates.
        """
        matched_faces = []
        for idx, face in enumerate(self.faces):
            left = face['x'] - face['w'] / 2.0
            right = face['x'] + face['w'] / 2.0
            top = face['y'] - face['h'] / 2.0
            bottom = face['y'] + face['h'] / 2.0
            
            if (left <= nx <= right) and (top <= ny <= bottom):
                # Save index and size of box for sorting
                matched_faces.append((idx, face['w'] * face['h']))
                
        if matched_faces:
            # Sort by area ascending so smaller boxes (tighter faces) take priority
            matched_faces.sort(key=lambda x: x[1])
            return matched_faces[0][0]
            
        return None
        
    # ----------------------------------------------------
    # State Modifying Handlers
    # ----------------------------------------------------
    def select_face(self, idx):
        if self.selected_face_idx == idx:
            return
            
        self.selected_face_idx = idx
        
        # Highlight card in sidebar by rebuilding/updating colors
        for i, widget in enumerate(self.faces_scroll.winfo_children()):
            if i == idx:
                widget.configure(fg_color="#374151")
            else:
                widget.configure(fg_color="#1f2937")
                
        self.draw_canvas()
        
    def delete_face(self, idx):
        if 0 <= idx < len(self.faces):
            self.faces.pop(idx)
            self.set_modified(True)
            
            if self.selected_face_idx == idx:
                self.selected_face_idx = None
            elif self.selected_face_idx is not None and self.selected_face_idx > idx:
                self.selected_face_idx -= 1
                
            self.hovered_face_idx = None
            self.rebuild_sidebar()
            self.draw_canvas()
            self.set_status("Face tag deleted.")
            
    def on_name_changed(self, idx, var):
        if 0 <= idx < len(self.faces):
            new_name = var.get()
            if self.faces[idx]['name'] != new_name:
                self.faces[idx]['name'] = new_name
                self.set_modified(True)
                
                # Redraw canvas to update floating names above boxes
                # Debounce/avoid redraw loops on single canvas items
                # Redraw canvas to update floating names above boxes
                # Debounce/avoid redraw loops on single canvas items
                if hasattr(self, 'redraw_debounce_id') and self.redraw_debounce_id is not None:
                    try:
                        self.canvas.after_cancel(self.redraw_debounce_id)
                    except Exception:
                        pass
                self.redraw_debounce_id = self.canvas.after(200, self.draw_canvas)
                
    def on_description_changed(self, event):
        new_desc = self.desc_textbox.get("1.0", "end-1c").strip()
        if self.description != new_desc:
            self.description = new_desc
            self.set_modified(True)
            self.set_status("Description modified.")
            
    def clear_all_tags(self):
        if not self.faces and not self.description:
            return
            
        if messagebox.askyesno("Clear All", "Are you sure you want to clear all face tags and the description for this image?"):
            self.faces = []
            self.description = ""
            self.set_modified(True)
            self.selected_face_idx = None
            self.hovered_face_idx = None
            self.desc_textbox.delete("1.0", "end")
            self.rebuild_sidebar()
            self.draw_canvas()
            self.set_status("Cleared tags.")
            
    def sort_faces(self):
        """
        Sorts tags in natural row order (Top-to-Bottom, Left-to-Right).
        Preserves selected/hovered face references across sorting.
        """
        if not self.faces:
            return
            
        selected_face = self.faces[self.selected_face_idx] if (self.selected_face_idx is not None and 0 <= self.selected_face_idx < len(self.faces)) else None
        hovered_face = self.faces[self.hovered_face_idx] if (self.hovered_face_idx is not None and 0 <= self.hovered_face_idx < len(self.faces)) else None
        
        self.faces = sort_faces_spatial(self.faces)
        
        if selected_face and selected_face in self.faces:
            self.selected_face_idx = self.faces.index(selected_face)
        if hovered_face and hovered_face in self.faces:
            self.hovered_face_idx = self.faces.index(hovered_face)

    def redetect_faces(self):
        if not self.current_image_path:
            return
            
        if messagebox.askyesno("Re-detect Faces", "This will clear current face tags and run the automatic detector. Proceed?"):
            self.set_status("Running face detection...")
            self.faces = detect_faces(self.current_image_path)
            self.sort_faces()
            self.set_modified(True)
            self.selected_face_idx = None
            self.hovered_face_idx = None
            self.rebuild_sidebar()
            self.draw_canvas()
            self.set_status(f"Auto-detected {len(self.faces)} face(s).")
            
    # ----------------------------------------------------
    # Save & File Navigation Functions
    # ----------------------------------------------------
    def save_current(self):
        if not getattr(self, 'current_image_path', None):
            return False
            
        self.set_status("Saving tags and updating metadata...")
        if hasattr(self, 'sort_faces') and callable(self.sort_faces):
            self.sort_faces()
        
        desc_text = getattr(self, 'description', '')
        if hasattr(self, 'desc_textbox') and not getattr(self, '_hydrating', False):
            try:
                desc_text = self.desc_textbox.get("1.0", "end-1c").strip()
                self.description = desc_text
            except Exception:
                pass
        
        selected_fmt = self.get_export_format() if hasattr(self, 'get_export_format') else (self.combo_format.get() if hasattr(self, 'combo_format') else "Original")
        if isinstance(selected_fmt, str):
            selected_fmt = selected_fmt.replace("Format: ", "").strip()
        original_ext = os.path.splitext(self.current_image_path)[1].lower()
        
        target_path = self.current_image_path
        is_conversion = False
        
        if selected_fmt != "Original":
            fmt_ext_map = {
                "JPEG": ".jpg",
                "PNG": ".png",
                "WebP": ".webp"
            }
            target_ext = fmt_ext_map.get(selected_fmt)
            if target_ext and target_ext != original_ext:
                target_path = os.path.splitext(self.current_image_path)[0] + target_ext
                is_conversion = True
                
        target_sidecar = get_project_sidecar_path(target_path)
        
        # Safe Scope Reduction (Review 6): Refuse format conversion when destination image or sidecar exists
        if is_conversion:
            if os.path.exists(target_path) or os.path.exists(target_sidecar):
                msg = (
                    f"Destination already exists on disk:\n{os.path.basename(target_path)}\n\n"
                    "In this preview version, overwriting existing files during format conversion "
                    "is disabled for data safety. Please choose another filename, location, or format."
                )
                if hasattr(self, 'winfo_exists'):
                    try:
                        messagebox.showwarning("Conversion Blocked (Safe Preview)", msg)
                    except Exception:
                        pass
                self.set_status("Conversion blocked: destination already exists. Choose another filename/location.")
                return False
                
        # Ensure authoritative document exists for source
        if not getattr(self, 'current_doc', None):
            w, h = (0, 0)
            if getattr(self, 'original_pil_image', None):
                w, h = self.original_pil_image.size
            self.current_doc = ProjectDocument(image_path=self.current_image_path, image_width=w, image_height=h)

        # C1: Centralized blocked sidecars guard
        blocked = getattr(self, 'blocked_sidecars', set())
        if target_sidecar in blocked or target_path in blocked:
            try:
                save_project_document(self.current_doc, is_draft=False, blocked_sidecars=blocked)
            except Exception:
                pass
            if hasattr(self, 'winfo_exists'):
                try:
                    messagebox.showerror("Save Blocked", f"Cannot overwrite protected/corrupt sidecar for '{os.path.basename(target_path)}'.")
                except Exception:
                    pass
            self.set_status("Save blocked: sidecar is protected.")
            return False

        color_val = self.combo_style_color.get() if hasattr(self, 'combo_style_color') else "Teal"
        size_val = self.combo_style_font_size.get() if hasattr(self, 'combo_style_font_size') else "Auto (1.0x)"

        # -------------------------------------------------------------
        # BRANCH A: FORMAT CONVERSION (Transactional Staging & Rollback)
        # -------------------------------------------------------------
        if is_conversion:
            import copy
            import shutil
            import uuid
            
            candidate_doc = copy.deepcopy(self.current_doc)
            candidate_doc.image_path = target_path
            candidate_doc.image_filename = os.path.basename(target_path)
            candidate_doc.sync_from_app_state(
                faces_dicts=getattr(self, 'faces', []),
                description=desc_text,
                color_theme=color_val,
                font_size_preset=size_val,
                pil_image=getattr(self, 'original_pil_image', None),
                preset_name=getattr(self, 'current_preset', 'Classic'),
                badge_shape=_resolve_app_badge_shape(self),
                font_family=_resolve_app_tag_font(self)
            )

            # Preserve pre-existing destination files for rollback on failure
            conv_id = uuid.uuid4().hex[:12]
            bak_img = f"{target_path}.conv_bak_{conv_id}"
            bak_sidecar = f"{target_sidecar}.conv_bak_{conv_id}"
            had_target_image = os.path.exists(target_path)
            had_target_sidecar = os.path.exists(target_sidecar)

            # Before any destination mutation: require all safety backups to succeed
            backup_failed = False
            backup_error = ""
            if had_target_image:
                try:
                    shutil.copy2(target_path, bak_img)
                    if not os.path.exists(bak_img):
                        raise IOError("Failed to verify image safety backup")
                except Exception as e:
                    backup_failed = True
                    backup_error = f"failed to create image backup: {e}"

            if not backup_failed and had_target_sidecar:
                try:
                    shutil.copy2(target_sidecar, bak_sidecar)
                    if not os.path.exists(bak_sidecar):
                        raise IOError("Failed to verify sidecar safety backup")
                except Exception as e:
                    backup_failed = True
                    backup_error = f"failed to create sidecar backup: {e}"

            if backup_failed:
                # Clean up any partial backup before aborting
                if os.path.exists(bak_img):
                    try:
                        os.remove(bak_img)
                    except Exception:
                        pass
                if hasattr(self, 'winfo_exists'):
                    try:
                        messagebox.showerror("Backup Failed", f"Cannot proceed with format conversion: {backup_error}.\nDestination files have not been modified.")
                    except Exception:
                        pass
                self.set_status(f"Conversion cancelled: {backup_error}. Destination preserved.")
                return False

            conversion_failed = False
            fail_reason = ""

            # Step 1: Write converted photo with embedded metadata
            try:
                metadata_success = write_photo_metadata(
                    target_path,
                    self.faces,
                    self.description,
                    original_path=self.current_image_path
                )
                if not metadata_success:
                    conversion_failed = True
                    fail_reason = "image metadata write failed"
            except Exception as e:
                print(f"Error converting photo metadata: {e}")
                conversion_failed = True
                fail_reason = str(e)

            # Step 2: Compute exact content fingerprint from converted image
            if not conversion_failed:
                try:
                    with Image.open(target_path) as written_img:
                        candidate_doc.content_fingerprint = compute_content_fingerprint(written_img)
                    if not candidate_doc.content_fingerprint:
                        conversion_failed = True
                        fail_reason = "empty content fingerprint on converted image"
                except Exception as e:
                    print(f"Error reading converted image for fingerprint: {e}")
                    conversion_failed = True
                    fail_reason = f"fingerprint decode failed: {e}"

            # Step 3: Write canonical project sidecar for converted target
            if not conversion_failed:
                try:
                    project_saved = save_project_document(candidate_doc, is_draft=False, blocked_sidecars=blocked)
                    if not project_saved:
                        conversion_failed = True
                        fail_reason = "project sidecar write failed"
                except Exception as e:
                    print(f"Error saving converted project sidecar: {e}")
                    conversion_failed = True
                    fail_reason = str(e)

            # ROLLBACK on any failure
            if conversion_failed:
                image_restored = False
                sidecar_restored = False

                # Restore target image
                if had_target_image and os.path.exists(bak_img):
                    try:
                        os.replace(bak_img, target_path)
                        image_restored = True
                    except Exception as e:
                        print(f"Error restoring target image from backup: {e}")
                elif not had_target_image:
                    if os.path.exists(target_path):
                        try:
                            os.remove(target_path)
                        except Exception:
                            pass
                    image_restored = True

                # Restore target sidecar
                if had_target_sidecar and os.path.exists(bak_sidecar):
                    try:
                        os.replace(bak_sidecar, target_sidecar)
                        sidecar_restored = True
                    except Exception as e:
                        print(f"Error restoring target sidecar from backup: {e}")
                elif not had_target_sidecar:
                    if os.path.exists(target_sidecar):
                        try:
                            os.remove(target_sidecar)
                        except Exception:
                            pass
                    sidecar_restored = True

                # CRITICAL SAFETY RULE: NEVER delete a backup if its restoration failed!
                if had_target_image and not image_restored:
                    # Backup must be preserved for user recovery!
                    pass
                elif os.path.exists(bak_img):
                    try:
                        os.remove(bak_img)
                    except Exception:
                        pass

                if had_target_sidecar and not sidecar_restored:
                    # Backup must be preserved for user recovery!
                    pass
                elif os.path.exists(bak_sidecar):
                    try:
                        os.remove(bak_sidecar)
                    except Exception:
                        pass

                all_restored = (not had_target_image or image_restored) and (not had_target_sidecar or sidecar_restored)
                if all_restored:
                    if hasattr(self, 'winfo_exists'):
                        try:
                            messagebox.showerror("Conversion Failed", f"Failed to complete format conversion: {fail_reason}.\nExisting destination files have been preserved.")
                        except Exception:
                            pass
                    self.set_status(f"Conversion failed: {fail_reason}. Destination preserved.")
                else:
                    retained = []
                    if had_target_image and not image_restored and os.path.exists(bak_img):
                        retained.append(os.path.basename(bak_img))
                    if had_target_sidecar and not sidecar_restored and os.path.exists(bak_sidecar):
                        retained.append(os.path.basename(bak_sidecar))
                    retained_str = ", ".join(retained)
                    if hasattr(self, 'winfo_exists'):
                        try:
                            messagebox.showerror("Critical Rollback Error", f"Conversion failed ({fail_reason}), and destination restoration encountered an error.\n\nOriginal files are preserved in backup:\n{retained_str}")
                        except Exception:
                            pass
                    self.set_status(f"Conversion rollback failed: could not restore destination. Recovery backup retained: {retained_str}")
                return False

            # SUCCESS: Clean up safety backups
            if os.path.exists(bak_img):
                try:
                    os.remove(bak_img)
                except Exception:
                    pass
            if os.path.exists(bak_sidecar):
                try:
                    os.remove(bak_sidecar)
                except Exception:
                    pass

            # Step 4: Commit state transition
            old_path = self.current_image_path
            delete_orig = False
            if hasattr(self, 'winfo_exists'):
                try:
                    delete_orig = messagebox.askyesno(
                        "Convert Format",
                        f"Successfully converted and saved to {os.path.basename(target_path)}.\n\nDo you want to delete the original file ({os.path.basename(old_path)})?"
                    )
                except Exception:
                    pass

            if delete_orig:
                try:
                    os.remove(old_path)
                    discard_draft(old_path)
                except Exception as e:
                    print(f"Error deleting original file: {e}")

            self.current_image_path = target_path
            self.current_doc = candidate_doc
            if self.image_list and 0 <= self.current_image_idx < len(self.image_list):
                self.image_list[self.current_image_idx] = target_path

            try:
                self.original_pil_image = Image.open(target_path)
                self.original_pil_image.load()
            except Exception:
                pass

            self.set_modified(False)
            discard_draft(target_path)
            self.set_status(f"Converted & saved to {os.path.basename(target_path)} successfully.")
            return True

        # -------------------------------------------------------------
        # BRANCH B: IN-PLACE SAVE (Current photo)
        # -------------------------------------------------------------
        self.current_doc.sync_from_app_state(
            faces_dicts=getattr(self, 'faces', []),
            description=desc_text,
            color_theme=color_val,
            font_size_preset=size_val,
            pil_image=getattr(self, 'original_pil_image', None),
            preset_name=getattr(self, 'current_preset', 'Classic'),
            badge_shape=_resolve_app_badge_shape(self),
            font_family=_resolve_app_tag_font(self)
        )

        # Step 1: Write embedded photo metadata
        try:
            metadata_success = write_photo_metadata(target_path, self.faces, self.description)
        except Exception as e:
            print(f"Error writing photo metadata: {e}")
            metadata_success = False

        if not metadata_success:
            if hasattr(self, 'winfo_exists'):
                try:
                    messagebox.showerror("Metadata Save Error", "Failed to write photo metadata.")
                except Exception:
                    pass
            self.set_status("Save error: metadata write failed.")
            return False

        # Metadata write succeeded!
        self.is_metadata_dirty = False

        # Step 2: Establish exact output content fingerprint from written file
        try:
            with Image.open(target_path) as written_img:
                self.current_doc.content_fingerprint = compute_content_fingerprint(written_img)
        except Exception as e:
            print(f"Warning: Could not read written image for fingerprint: {e}")

        # Step 3: Write canonical project sidecar
        try:
            project_saved = save_project_document(self.current_doc, is_draft=False, blocked_sidecars=blocked)
        except Exception as e:
            print(f"Error saving project sidecar: {e}")
            project_saved = False

        if not project_saved:
            self.is_project_dirty = True
            self.is_modified = True
            self._sync_modified_status()
            if hasattr(self, 'winfo_exists'):
                try:
                    messagebox.showerror("Project Save Error", "Photo metadata was saved, but project sidecar could not be written.")
                except Exception:
                    pass
            self.set_status("Warning: metadata saved, but project sidecar failed.")
            return False

        # Step 4: Both succeeded!
        self.set_modified(False)
        discard_draft(target_path)
        self.set_status("Metadata & Project successfully saved!")
        if hasattr(self, 'rebuild_sidebar') and callable(self.rebuild_sidebar):
            self.rebuild_sidebar()
        if hasattr(self, 'draw_canvas') and callable(self.draw_canvas):
            self.draw_canvas()
        if hasattr(self, 'update_navigation_controls') and callable(self.update_navigation_controls):
            self.update_navigation_controls()
        return True

    def export_annotated(self):
        if not self.current_image_path:
            self.set_status("No image loaded to export.")
            messagebox.showwarning("No Image", "Please load an image before exporting rendered versions.")
            return
            
        self.set_status("Generating annotated images...")
        self.sort_faces()
        
        # Make sure description and tags are synchronized (read from textbox if modified)
        self.description = self.desc_textbox.get("1.0", "end-1c").strip()
        
        selected_fmt = self.get_export_format() if hasattr(self, 'get_export_format') else (self.combo_format.get() if hasattr(self, 'combo_format') else "Original")
        if isinstance(selected_fmt, str):
            selected_fmt = selected_fmt.replace("Format: ", "").strip()
        original_ext = os.path.splitext(self.current_image_path)[1].lower()
        
        target_ext = original_ext
        if selected_fmt != "Original":
            fmt_ext_map = {
                "JPEG": ".jpg",
                "PNG": ".png",
                "WebP": ".webp"
            }
            target_ext = fmt_ext_map.get(selected_fmt, original_ext)
            
        base_path = os.path.splitext(self.current_image_path)[0]
        numbered_path = f"{base_path}_numbered{target_ext}"
        tagged_path = f"{base_path}_tagged{target_ext}"
        html_path = f"{base_path}_interactive.html"
        svg_path = f"{base_path}_interactive.svg"
        
        # Fetch style settings
        color_style = self.get_selected_color_style()
        font_size_style = self.get_selected_font_size_style()
        
        active_preset = getattr(self, 'current_preset', 'Classic')
        selected_shape = self.get_selected_badge_shape()
        selected_tag_font = self.get_selected_tag_font()
        
        export_source = self.original_pil_image if getattr(self, '_image_rotated', False) and self.original_pil_image is not None else self.current_image_path
        
        # 1. Export Output 2-a Numbered (draw_names = False)
        success_num = draw_annotations_on_image(export_source, self.faces, numbered_path, draw_names=False, color_style=color_style, font_size_style=font_size_style, description=self.description, style_preset=active_preset, badge_shape=selected_shape, font_family=selected_tag_font)
        
        # 2. Export Output 2-b Tagged (draw_names = True)
        success_tag = draw_annotations_on_image(export_source, self.faces, tagged_path, draw_names=True, color_style=color_style, font_size_style=font_size_style, description=self.description, style_preset=active_preset, badge_shape=selected_shape, font_family=selected_tag_font)
        
        # 3. Export Output 1-a (Interactive HTML) & Output 1-b (Interactive SVG)
        rot_pil = self.original_pil_image if getattr(self, '_image_rotated', False) else None
        success_html = write_interactive_html(self.current_image_path, self.faces, self.description, color_style=color_style, font_size_style=font_size_style, font_family=selected_tag_font, source_image=rot_pil)
        success_svg = write_interactive_svg(self.current_image_path, self.faces, self.description, color_style=color_style, font_size_style=font_size_style, font_family=selected_tag_font, source_image=rot_pil)
        
        results = [
            ("Output 1-a (Interactive HTML)", os.path.basename(html_path), bool(success_html)),
            ("Output 1-b (Interactive SVG)", os.path.basename(svg_path), bool(success_svg)),
            ("Output 2-a (Numbered Image)", os.path.basename(numbered_path), bool(success_num)),
            ("Output 2-b (Tagged Image)", os.path.basename(tagged_path), bool(success_tag)),
        ]
        succeeded = [f"• {label}: {fname}" for label, fname, ok in results if ok]
        failed = [f"• {label}: {fname}" for label, fname, ok in results if not ok]

        if not failed:
            self.set_status("Annotated images & HTML/SVG exported successfully!")
            messagebox.showinfo(
                "Export Success", 
                "Successfully exported all 4 outputs with selected color & font size:\n\n" +
                "\n".join(succeeded)
            )
        elif succeeded:
            self.set_status(f"Export completed with {len(failed)} failure(s).")
            messagebox.showwarning(
                "Export Partial Success",
                f"Export completed with {len(failed)} failure(s):\n\n"
                f"Succeeded ({len(succeeded)}):\n" + "\n".join(succeeded) + "\n\n"
                f"Failed ({len(failed)}):\n" + "\n".join(failed)
            )
        else:
            self.set_status("Error exporting annotated files.")
            messagebox.showerror(
                "Export Error",
                "Failed to export files:\n\n" + "\n".join(failed)
            )
            
    def open_file(self):
        file_path = filedialog.askopenfilename(
            title="Open Image",
            filetypes=[
                ("Supported Images", "*.jpg;*.jpeg;*.png;*.webp"),
                ("JPEG files", "*.jpg;*.jpeg"),
                ("PNG files", "*.png"),
                ("WebP files", "*.webp"),
                ("All files", "*.*")
            ]
        )
        if not file_path:
            return
        photos = list(self.image_list)
        current = self.current_image_path
        if current and not photos:
            photos.append(current)
        selected = os.path.normcase(os.path.abspath(file_path))
        for idx, path in enumerate(photos):
            if selected == os.path.normcase(os.path.abspath(path)):
                if path != current and not self.load_image(path):
                    return
                self.image_list, self.current_image_idx = photos, idx
                self.update_navigation_controls()
                if self.is_filmstrip_expanded:
                    self.populate_filmstrip()
                return

        add = False
        if current:
            add = messagebox.askyesnocancel(
                "Open another photo",
                "Add the new photo to the filmstrip?\n\n"
                "Yes keeps the open photos. No opens only the new photo. "
                "Cancel leaves the filmstrip as it is.",
                parent=self,
            )
            if add is None:
                return
        if not self.load_image(file_path):
            return

        if add:
            idx = len(photos)
            photos.append(file_path)
        else:
            photos, idx = [file_path], 0
        self.image_list, self.current_image_idx = photos, idx
        self.update_navigation_controls()
        if add and not self.is_filmstrip_expanded:
            self.toggle_filmstrip()
        elif self.is_filmstrip_expanded:
            self.populate_filmstrip()

    def open_folder(self):
        folder_path = filedialog.askdirectory(title="Open Photo Folder")
        if not folder_path:
            return

        excluded_suffixes = (
            "_numbered.jpg", "_numbered.jpeg", "_numbered.png", "_numbered.webp",
            "_tagged.jpg", "_tagged.jpeg", "_tagged.png", "_tagged.webp",
            "_tags.html", "_tags.svg"
        )
        candidate_list = []
        for root, _, files in os.walk(folder_path):
            for f in files:
                fl = f.lower()
                if fl.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    if not any(fl.endswith(sfx) for sfx in excluded_suffixes):
                        candidate_list.append(os.path.join(root, f))
            # Only search top-level folder
            break

        candidate_list.sort()
        if not candidate_list:
            messagebox.showinfo("No images found", "No supported image files found in selected directory.")
            return

        # Commit new collection only after successful load. If user cancels unsaved-edits
        # prompt or first image is unreadable, previous image_list, controls, and filmstrip
        # remain completely untouched.
        if self.load_image(candidate_list[0]):
            self.image_list = candidate_list
            self.current_image_idx = 0
            if hasattr(self, 'update_navigation_controls') and callable(self.update_navigation_controls):
                self.update_navigation_controls()
            if hasattr(self, 'populate_filmstrip') and callable(self.populate_filmstrip):
                self.populate_filmstrip()
                
    def prev_image(self):
        if self.current_image_idx > 0:
            prev_path = self.image_list[self.current_image_idx - 1]
            if self.load_image(prev_path):
                self.current_image_idx -= 1
                self.update_navigation_controls()
            
    def next_image(self):
        if self.current_image_idx < len(self.image_list) - 1:
            next_path = self.image_list[self.current_image_idx + 1]
            if self.load_image(next_path):
                self.current_image_idx += 1
                self.update_navigation_controls()
            
    def update_navigation_controls(self):
        # Update buttons enabled state
        if len(self.image_list) <= 1:
            self.btn_prev.configure(state="disabled")
            self.btn_next.configure(state="disabled")
            self.lbl_counter.configure(text="1 of 1 Photo" if getattr(self, 'current_image_path', None) else "No Photos Loaded")
        else:
            self.btn_prev.configure(state="normal" if self.current_image_idx > 0 else "disabled")
            self.btn_next.configure(state="normal" if self.current_image_idx < len(self.image_list) - 1 else "disabled")
            self.lbl_counter.configure(text=f"{self.current_image_idx + 1} of {len(self.image_list)} Photos")
        if hasattr(self, 'btn_toggle_filmstrip'):
            count = len(self.image_list)
            self.btn_toggle_filmstrip.configure(text=f"Filmstrip ({count})")
            
    def set_status(self, text):
        self.lbl_status.configure(text=text)
        if hasattr(self, 'lbl_status_icon'):
            if "Error" in text or "Failed" in text:
                self.lbl_status_icon.configure(text="●", text_color="#ef4444")
            elif "Saving" in text or "Running" in text or "Exporting" in text:
                self.lbl_status_icon.configure(text="●", text_color="#f59e0b")
            else:
                self.lbl_status_icon.configure(text="●", text_color="#10b981")
        self.update_idletasks()
        
    def open_editor_2b(self):
        if not self.current_image_path or not self.faces:
            messagebox.showinfo("No Photo Loaded", "Please open a photo with face tags first.")
            return
        Output2bEditorWindow(self)

class Output2bEditorWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title(f"Fine-Tune Layout (Photo Tagger v{APP_VERSION})")
        self.geometry("1200x900")
        
        self.zoom_factor = 1.0
        self.view_center_x = 0.5
        self.view_center_y = 0.5
        self.dragging_idx = None
        self.is_panning = False
        self.pan_start_x = 0
        self.pan_start_y = 0
        self.drag_start_x = 0
        self.drag_start_y = 0
        
        self.grid_rowconfigure(0, weight=0) # Top Control Bar
        self.grid_rowconfigure(1, weight=1) # Interactive Canvas
        self.grid_rowconfigure(2, weight=0) # Bottom Bar
        self.grid_columnconfigure(0, weight=1)
        
        # 1. Top Control Bar
        self.ctrl_frame = ctk.CTkFrame(self, height=55, corner_radius=0)
        self.ctrl_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        
        # Color Selector
        lbl_color = ctk.CTkLabel(self.ctrl_frame, text="Tag Color:", font=("Segoe UI", 11, "bold"))
        lbl_color.pack(side="left", padx=(15, 3), pady=10)
        
        self.combo_color = ctk.CTkComboBox(
            self.ctrl_frame, 
            values=["Teal", "Blue", "Purple", "Green", "Orange/Red", "Yellow", "White", "Black"], 
            width=110, 
            font=("Segoe UI", 11),
            command=self.on_editor_color_changed
        )
        self.combo_color.pack(side="left", padx=(0, 15), pady=10)
        self.combo_color.set(self.parent.combo_style_color.get())
        
        # Size Selector
        lbl_size = ctk.CTkLabel(self.ctrl_frame, text="Tag Size:", font=("Segoe UI", 11, "bold"))
        lbl_size.pack(side="left", padx=(0, 3), pady=10)
        
        self.combo_size = ctk.CTkComboBox(
            self.ctrl_frame, 
            values=["Micro (0.5x)", "Small (0.7x)", "Auto (1.0x)", "Medium (1.2x)", "Large (1.5x)", "X-Large (2.0x)"], 
            width=120, 
            font=("Segoe UI", 11),
            command=self.on_editor_size_changed
        )
        self.combo_size.pack(side="left", padx=(0, 15), pady=10)
        self.combo_size.set(self.parent.combo_style_font_size.get())

        # Zoom Controls
        self.btn_zoom_out = ctk.CTkButton(self.ctrl_frame, text="➖", command=self.zoom_out, width=32, height=28, font=("Segoe UI", 12, "bold"))
        self.btn_zoom_out.pack(side="left", padx=3, pady=10)
        
        self.lbl_zoom = ctk.CTkLabel(self.ctrl_frame, text="Zoom: 100%", font=("Segoe UI", 11, "bold"), width=80)
        self.lbl_zoom.pack(side="left", padx=3, pady=10)
        
        self.btn_zoom_in = ctk.CTkButton(self.ctrl_frame, text="➕", command=self.zoom_in, width=32, height=28, font=("Segoe UI", 12, "bold"))
        self.btn_zoom_in.pack(side="left", padx=3, pady=10)
        
        self.btn_zoom_reset = ctk.CTkButton(self.ctrl_frame, text="🔄 100%", command=self.zoom_reset, width=65, height=28, font=("Segoe UI", 10, "bold"), fg_color="#4b5563", hover_color="#374151")
        self.btn_zoom_reset.pack(side="left", padx=(3, 15), pady=10)

        # Reset Positions Button
        btn_reset = ctk.CTkButton(
            self.ctrl_frame, 
            text="🔄 Reset Layout", 
            command=self.reset_positions, 
            width=120, 
            fg_color="#4b5563", 
            hover_color="#374151", 
            font=("Segoe UI", 11, "bold")
        )
        btn_reset.pack(side="right", padx=15, pady=10)
        
        # 2. Main Canvas Container
        self.canvas_container = ctk.CTkFrame(self, fg_color="#0f172a")
        self.canvas_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self.canvas_container.grid_rowconfigure(0, weight=1)
        self.canvas_container.grid_columnconfigure(0, weight=1)
        
        self.canvas = tk.Canvas(self.canvas_container, bg="#0f172a", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        
        # Canvas Mouse Events (Left-Click Drag Badges)
        self.canvas.bind("<Configure>", self.render_editor_canvas)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        
        # Panning (Right Click Drag)
        self.canvas.bind("<ButtonPress-3>", self.on_pan_press)
        self.canvas.bind("<B3-Motion>", self.on_pan_drag)
        self.canvas.bind("<ButtonRelease-3>", self.on_pan_release)
        
        # Mouse Wheel Zoom
        self.canvas.bind("<MouseWheel>", self.on_mouse_zoom)
        self.canvas.bind("<Button-4>", lambda e: self.on_mouse_zoom_linux(e, True))
        self.canvas.bind("<Button-5>", lambda e: self.on_mouse_zoom_linux(e, False))
        
        # 3. Bottom Action Bar (Agency-Grade Design Layout)
        self.bottom_frame = ctk.CTkFrame(self, height=54, corner_radius=0, fg_color="#090d16", border_width=1, border_color="#1e293b")
        self.bottom_frame.grid(row=2, column=0, sticky="ew", padx=0, pady=0)
        
        # Left Section: Instructions & Hint Card
        self.hint_card = ctk.CTkFrame(self.bottom_frame, fg_color="#111827", corner_radius=8, border_width=1, border_color="#1f2937")
        self.hint_card.pack(side="left", padx=12, pady=7)
        
        lbl_hint = ctk.CTkLabel(
            self.hint_card, 
            text="💡 Scroll MouseWheel to Zoom • Right-Click Drag to Pan • Left-Click Drag any badge to fine-tune position", 
            font=("Segoe UI", 10.5, "italic"), 
            text_color="#cbd5e1"
        )
        lbl_hint.pack(side="left", padx=10, pady=4)
        
        # Right Section: Action Buttons Card
        self.actions_card = ctk.CTkFrame(self.bottom_frame, fg_color="#111827", corner_radius=8, border_width=1, border_color="#1f2937")
        self.actions_card.pack(side="right", padx=12, pady=7)
        
        btn_close = ctk.CTkButton(
            self.actions_card, 
            text="Cancel", 
            command=self.destroy, 
            width=85, 
            height=28,
            fg_color="#ef4444", 
            hover_color="#dc2626", 
            font=("Segoe UI", 11, "bold"),
            corner_radius=6
        )
        btn_close.pack(side="right", padx=4, pady=4)
        
        btn_export = ctk.CTkButton(
            self.actions_card, 
            text="💾 Save & Export Output 2-b", 
            command=self.save_and_export, 
            width=185, 
            height=28,
            fg_color="#10b981", 
            hover_color="#059669", 
            font=("Segoe UI", 11, "bold"),
            corner_radius=6
        )
        btn_export.pack(side="right", padx=4, pady=4)

        btn_save_layout = ctk.CTkButton(
            self.actions_card, 
            text="💾 Save Layout", 
            command=self.save_layout, 
            width=115, 
            height=28,
            fg_color="#3b82f6", 
            hover_color="#2563eb", 
            font=("Segoe UI", 11, "bold"),
            corner_radius=6
        )
        btn_save_layout.pack(side="right", padx=4, pady=4)
        
        self.tk_preview = None
        self.scale = 1.0
        self.pad_x = 0
        self.pad_y = 0
        self.orig_w = 800
        self.orig_h = 600
        self.crop_left = 0
        self.crop_top = 0
        
        self.after(200, self.render_editor_canvas)

    def get_color_style(self):
        color_map = {
            "Teal": {"rgb": (20, 184, 166), "hex": "#14b8a6"},
            "Blue": {"rgb": (59, 130, 246), "hex": "#3b82f6"},
            "Purple": {"rgb": (168, 85, 247), "hex": "#a855f7"},
            "Green": {"rgb": (34, 197, 94), "hex": "#22c55e"},
            "Orange/Red": {"rgb": (249, 115, 22), "hex": "#f97316"},
            "Yellow": {"rgb": (234, 179, 8), "hex": "#eab308"},
            "White": {"rgb": (255, 255, 255), "hex": "#ffffff"},
            "Black": {"rgb": (30, 41, 59), "hex": "#1e293b"}
        }
        val = self.combo_color.get()
        return color_map.get(val, color_map["Teal"])

    def get_font_style(self):
        size_map = {
            "Micro (0.5x)": {"scale": 0.5},
            "Small (0.7x)": {"scale": 0.7},
            "Auto (1.0x)": {"scale": 1.0},
            "Medium (1.2x)": {"scale": 1.2},
            "Large (1.5x)": {"scale": 1.5},
            "X-Large (2.0x)": {"scale": 2.0}
        }
        val = self.combo_size.get()
        return size_map.get(val, size_map["Auto (1.0x)"])

    def zoom_in(self):
        self.zoom_factor = min(8.0, self.zoom_factor * 1.25)
        txt = f"{int(self.zoom_factor * 100)}%"
        if hasattr(self, 'lbl_zoom_level'):
            self.lbl_zoom_level.configure(text=txt)
        if hasattr(self, 'c_lbl_zoom'):
            self.c_lbl_zoom.configure(text=txt)
        self.render_editor_canvas()

    def zoom_out(self):
        self.zoom_factor = max(1.0, self.zoom_factor / 1.25)
        if self.zoom_factor == 1.0:
            self.view_center_x = 0.5
            self.view_center_y = 0.5
        txt = f"{int(self.zoom_factor * 100)}%"
        if hasattr(self, 'lbl_zoom_level'):
            self.lbl_zoom_level.configure(text=txt)
        if hasattr(self, 'c_lbl_zoom'):
            self.c_lbl_zoom.configure(text=txt)
        self.render_editor_canvas()

    def zoom_reset(self):
        self.zoom_factor = 1.0
        self.view_center_x = 0.5
        self.view_center_y = 0.5
        if hasattr(self, 'lbl_zoom_level'):
            self.lbl_zoom_level.configure(text="100%")
        if hasattr(self, 'c_lbl_zoom'):
            self.c_lbl_zoom.configure(text="100%")
        self.render_editor_canvas()

    def on_mouse_zoom(self, event):
        if event.delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    def on_mouse_zoom_linux(self, event, is_in):
        if is_in:
            self.zoom_in()
        else:
            self.zoom_out()

    def on_pan_press(self, event):
        self.is_panning = True
        self.pan_start_x = event.x
        self.pan_start_y = event.y

    def on_pan_drag(self, event):
        if not self.is_panning or self.zoom_factor <= 1.0:
            return
        dx = event.x - self.pan_start_x
        dy = event.y - self.pan_start_y
        self.pan_start_x = event.x
        self.pan_start_y = event.y
        
        canvas_w = max(50, self.canvas.winfo_width())
        canvas_h = max(50, self.canvas.winfo_height())
        
        self.view_center_x -= (dx / float(canvas_w * self.zoom_factor))
        self.view_center_y -= (dy / float(canvas_h * self.zoom_factor))
        self.render_editor_canvas()

    def on_pan_release(self, event):
        self.is_panning = False

    def reset_positions(self):
        for f in self.parent.faces:
            f['bx'] = None
            f['by'] = None
        self.parent.set_modified(True, project=True, metadata=False)
        self.render_editor_canvas()

    def on_editor_color_changed(self, val):
        if hasattr(self.parent, 'combo_style_color'):
            self.parent.combo_style_color.set(val)
        self.parent.set_modified(True, project=True, metadata=False)
        self.render_editor_canvas()

    def on_editor_size_changed(self, val):
        if hasattr(self.parent, 'combo_style_font_size'):
            self.parent.combo_style_font_size.set(val)
        self.parent.set_modified(True, project=True, metadata=False)
        self.render_editor_canvas()

        
    def render_editor_canvas(self, event=None):
        if not self.parent.current_image_path or not self.parent.faces:
            return
            
        color_style = self.get_color_style()
        font_style = self.get_font_style()
        color_hex = color_style["hex"]
        
        # Sync main app dropdowns so saved files match
        self.parent.combo_style_color.set(self.combo_color.get())
        self.parent.combo_style_font_size.set(self.combo_size.get())
        
        import tempfile
        temp_dir = tempfile.gettempdir()
        temp_out = os.path.join(temp_dir, "temp_preview_2b.jpg")
        
        selected_shape = _resolve_app_badge_shape(self.parent)
        selected_font = _resolve_app_tag_font(self.parent)
        
        # Generate base image with footer legend (for_editor=True skips baking badges into PIL image)
        img_src = self.parent.original_pil_image if getattr(self.parent, '_image_rotated', False) and self.parent.original_pil_image is not None else self.parent.current_image_path
        draw_annotations_on_image(
            img_src, 
            self.parent.faces, 
            temp_out, 
            draw_names=True, 
            color_style=color_style, 
            font_size_style=font_style, 
            description=self.parent.description,
            for_editor=True,
            badge_shape=selected_shape,
            font_family=selected_font
        )
        
        if os.path.exists(temp_out):
            with Image.open(temp_out) as img:
                canvas_w = max(50, self.canvas.winfo_width())
                canvas_h = max(50, self.canvas.winfo_height())
                
                orig_w, orig_h = img.size
                photo_w, photo_h = self.parent.original_pil_image.size
                
                base_scale = min(canvas_w / orig_w, canvas_h / orig_h)
                scale = base_scale * self.zoom_factor
                
                crop_w = min(orig_w, canvas_w / scale)
                crop_h = min(orig_h, canvas_h / scale)
                
                half_w_norm = (crop_w / 2.0) / orig_w
                half_h_norm = (crop_h / 2.0) / orig_h
                self.view_center_x = max(half_w_norm, min(1.0 - half_w_norm, self.view_center_x))
                self.view_center_y = max(half_h_norm, min(1.0 - half_h_norm, self.view_center_y))
                
                crop_left = self.view_center_x * orig_w - crop_w / 2.0
                crop_right = self.view_center_x * orig_w + crop_w / 2.0
                crop_top = self.view_center_y * orig_h - crop_h / 2.0
                crop_bottom = self.view_center_y * orig_h + crop_h / 2.0
                
                display_w = int(orig_w * scale) if orig_w * scale < canvas_w else canvas_w
                display_h = int(orig_h * scale) if orig_h * scale < canvas_h else canvas_h
                
                self.pad_x = (canvas_w - display_w) // 2
                self.pad_y = (canvas_h - display_h) // 2
                self.scale = scale
                self.crop_left = crop_left
                self.crop_top = crop_top
                self.orig_w = orig_w
                self.orig_h = orig_h
                self.photo_w = photo_w
                self.photo_h = photo_h
                
                cropped = img.crop((crop_left, crop_top, crop_right, crop_bottom))
                resized = cropped.resize((display_w, display_h), Image.Resampling.LANCZOS)
                self.tk_preview = ImageTk.PhotoImage(resized)
                
                self.canvas.delete("all")
                self.canvas.create_image(canvas_w // 2, canvas_h // 2, image=self.tk_preview, anchor="center")
                
                # Render native Tkinter interactive canvas items for all face badges (photo bounds only)
                base_font_size = max(16, int(min(photo_w, photo_h) / 45))
                scale_factor = font_style.get("scale", 1.0)
                uniform_badge_r = max(14, int(base_font_size * 0.95 * scale_factor))
                badge_r_canvas = max(11, int(uniform_badge_r * scale))
                font_size_canvas = max(9, int(badge_r_canvas * 0.72))
                
                for idx, f in enumerate(self.parent.faces):
                    bx_norm = f.get('bx') if f.get('bx') is not None else f['x']
                    by_norm = f.get('by') if f.get('by') is not None else (f['y'] - f['h']/2.0 - 0.03)
                    
                    bx_orig = bx_norm * photo_w
                    by_orig = by_norm * photo_h
                    
                    cx_canvas = self.pad_x + (bx_orig - crop_left) * scale
                    cy_canvas = self.pad_y + (by_orig - crop_top) * scale
                    num_str = str(idx + 1)
                    
                    draw_canvas_badge(
                        self.canvas,
                        cx_canvas,
                        cy_canvas,
                        num_str,
                        badge_r_canvas,
                        color_hex,
                        text_color="#ffffff",
                        badge_shape=selected_shape,
                        tags=("badge_element", f"tag_{idx}"),
                        font_family=selected_font,
                        style_preset=getattr(self.parent, 'current_preset', 'Classic')
                    )
                    
                # Bind mouse drag events natively to all badge items
                self.canvas.tag_bind("badge_element", "<ButtonPress-1>", self.on_press)
                self.canvas.tag_bind("badge_element", "<B1-Motion>", self.on_drag)
                self.canvas.tag_bind("badge_element", "<ButtonRelease-1>", self.on_release)
                
    def on_press(self, event):
        if not hasattr(self, 'scale') or not self.parent.faces:
            return
            
        # 1. Try item directly under cursor
        items = list(self.canvas.find_withtag("current"))
        
        # 2. Try items in an 8px box around cursor
        if not items or any(t == "bg_image" for i in items for t in self.canvas.gettags(i)):
            items = list(self.canvas.find_overlapping(event.x - 8, event.y - 8, event.x + 8, event.y + 8))
            
        # 3. Fallback: closest item within 30px
        if not items or all(any(t == "bg_image" for t in self.canvas.gettags(i)) for i in items):
            closest = self.canvas.find_closest(event.x, event.y, halo=30)
            if closest:
                items = list(closest)
                
        for item in reversed(items):
            tags = self.canvas.gettags(item)
            for t in tags:
                if t.startswith("tag_"):
                    self.dragging_idx = int(t.split("_")[1])
                    self.drag_start_x = event.x
                    self.drag_start_y = event.y
                    return
            
    def on_drag(self, event):
        if self.dragging_idx is None:
            return
            
        # Native Tkinter canvas item move (0.0ms delay - 120 FPS smooth)
        dx = event.x - self.drag_start_x
        dy = event.y - self.drag_start_y
        self.drag_start_x = event.x
        self.drag_start_y = event.y
        
        self.canvas.move(f"tag_{self.dragging_idx}", dx, dy)
        
    def on_release(self, event):
        if self.dragging_idx is not None:
            # Update face's normalized badge position relative strictly to photo_h
            coords = self.canvas.coords(f"tag_{self.dragging_idx}")
            if coords and len(coords) >= 4:
                cx_canvas = (coords[0] + coords[2]) / 2.0
                cy_canvas = (coords[1] + coords[3]) / 2.0
                
                bx_orig = self.crop_left + (cx_canvas - self.pad_x) / float(self.scale)
                by_orig = self.crop_top + (cy_canvas - self.pad_y) / float(self.scale)
                
                bx_norm = max(0.0, min(1.0, bx_orig / float(self.photo_w)))
                by_norm = max(0.0, min(1.0, by_orig / float(self.photo_h)))
                
                self.parent.faces[self.dragging_idx]['bx'] = bx_norm
                self.parent.faces[self.dragging_idx]['by'] = by_norm
                self.parent.set_modified(True, project=True, metadata=False)
                
            self.dragging_idx = None

    def save_layout(self):
        if self.parent.save_project_only():
            messagebox.showinfo("Layout Saved", "Layout saved to project sidecar successfully!\nOriginal photo file was not modified.")
        else:
            messagebox.showerror("Save Failed", "Could not save layout sidecar.")

    def save_and_export(self):
        if not self.parent.save_project_only():
            messagebox.showerror("Export Aborted", "Could not save layout. Export cancelled to prevent losing layout.")
            return
        self.destroy()
        self.parent.export_annotated()

def _run_packaged_journey_mode():
    """Automated verification mode for packaged preview executable interactions."""
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    if hasattr(sys.stderr, 'reconfigure'):
        try:
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

    print("=" * 80)
    print(f"PHOTO TAGGER PACKAGED EXECUTABLE JOURNEY (v{APP_VERSION})")
    print("=" * 80)
    messagebox.askyesnocancel = lambda *a, **k: False
    messagebox.askyesno = lambda *a, **k: True
    messagebox.showwarning = lambda *a, **k: None
    messagebox.showinfo = lambda *a, **k: None
    messagebox.showerror = lambda *a, **k: None

    app = PhotoTaggerApp()
    app.update_idletasks()
    app.update()

    print(f"[PACKAGED STEP 1] Executable Title: '{app.title()}'")
    assert f"Photo Tagger v{APP_VERSION}" in app.title(), "Title mismatch!"
    print(f"[PACKAGED STEP 2] Geometry: {app.geometry()} (Logical)")
    
    tb_w = app.toolbar_frame.winfo_width()
    id_w = app.identity_frame.winfo_width()
    tool_w = app.tool_zoom_frame.winfo_width()
    margin = tb_w - (id_w + tool_w)
    print(f"[PACKAGED STEP 3] Toolbar clearance: {margin}px")
    assert tb_w >= (id_w + tool_w), "Toolbar clipping detected in packaged binary!"

    # Resolve photo argument
    photo_args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    photo_path = photo_args[0] if photo_args and os.path.exists(photo_args[0]) else None
    if photo_path:
        app.load_image(photo_path)
        app.update_idletasks()
        app.update()
        print(f"[PACKAGED STEP 4] Photo loaded: {os.path.basename(photo_path)}")
        if not app.faces:
            app.faces = [{"name": "Packaged Test User", "x": 0.5, "y": 0.45, "w": 0.25, "h": 0.25, "id": "t1"}]
        
        for shape_ui, canon in [("Auto Pill/Circle", "auto"), ("Rounded Square", "rounded_square"), ("Square", "square")]:
            app.combo_badge_shape.set(shape_ui)
            app.on_shape_changed(shape_ui)
            app.update_idletasks()
            app.update()
            assert app.get_selected_badge_shape() == canon
            print(f"[PACKAGED STEP 5] Badge shape changed to: '{canon}'")

        for mode in ["Layout", "Preview", "Tagging"]:
            app.mode_switcher.set(mode)
            app.on_workspace_mode_changed(mode)
            app.update_idletasks()
            app.update()
            print(f"[PACKAGED STEP 6] Switched workspace mode to: '{mode}'")

        app.event_generate("<Control-Key-0>")
        app.update_idletasks()
        app.update()
        print("[PACKAGED STEP 7] Keyboard event (Ctrl+0) handled")

        saved = app.save_project_only()
        print(f"[PACKAGED STEP 8] Project sidecar saved: {saved}")
        assert saved is True

    print("\n" + "=" * 80)
    print("PACKAGED_JOURNEY_SUCCESS")
    print("=" * 80)
    app.destroy()
    sys.exit(0)

if __name__ == "__main__":
    if "--sample-journey" in sys.argv or os.environ.get("PHOTOTAGGER_SAMPLE_JOURNEY") == "1":
        _run_packaged_journey_mode()
    app = PhotoTaggerApp()
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        app.after(100, lambda: app.load_image(sys.argv[1]))
    app.mainloop()
