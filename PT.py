import os
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image, ImageTk

# Import our custom modules
from metadata import (
    read_photo_metadata, 
    write_photo_metadata, 
    write_interactive_html, 
    write_interactive_svg,
    draw_annotations_on_image,
    sort_faces_spatial
)
from detector import detect_faces

# Configure customtkinter appearance
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class PhotoTaggerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Window setup
        self.title("Photo Tagger (v.2.4)")
        self.geometry("1300x850")
        self.minsize(1000, 700)
        
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
        
        # References for face thumbnails to prevent garbage collection
        self.face_images = []
        self.face_entries = []
        
        # Load brand logo assets
        self.app_logo_img = None
        self.app_logo_small = None
        logo_path = os.path.join(os.path.dirname(__file__), "app_logo.png")
        if os.path.exists(logo_path):
            try:
                pil_logo = Image.open(logo_path)
                self.app_logo_img = ctk.CTkImage(light_image=pil_logo, dark_image=pil_logo, size=(24, 24))
                self.app_logo_small = ctk.CTkImage(light_image=pil_logo, dark_image=pil_logo, size=(16, 16))
            except Exception as e:
                print("Error loading app logo:", e)
        
        # Build UI layout
        self.create_layout()
        
        # Bind window closing protocol
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def create_layout(self):
        # Configure grid row/col weights
        self.grid_rowconfigure(0, weight=0)  # Top Bar
        self.grid_rowconfigure(1, weight=1)  # Main Area (Canvas + Sidebar)
        self.grid_rowconfigure(2, weight=0)  # Bottom Navigation / Status
        self.grid_columnconfigure(0, weight=1)
        
        # ----------------------------------------------------
        # 1. Top Action Header
        # ----------------------------------------------------
        self.header_frame = ctk.CTkFrame(self, height=60, corner_radius=0)
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        
        # Left header section: Brand Logo & File actions
        if hasattr(self, 'app_logo_img') and self.app_logo_img:
            self.lbl_brand_logo = ctk.CTkLabel(self.header_frame, image=self.app_logo_img, text="")
            self.lbl_brand_logo.pack(side="left", padx=(15, 6), pady=12)
            
        self.lbl_brand_title = ctk.CTkLabel(self.header_frame, text="Photo Tagger", font=("Segoe UI", 13, "bold"), text_color="#f8fafc")
        self.lbl_brand_title.pack(side="left", padx=(0, 4), pady=12)
        
        self.lbl_brand_version = ctk.CTkLabel(
            self.header_frame, 
            text="v.2.4", 
            font=("Segoe UI", 9, "bold"), 
            text_color="#ffffff", 
            fg_color="#0ea5e9", 
            corner_radius=6, 
            width=36, 
            height=18
        )
        self.lbl_brand_version.pack(side="left", padx=(0, 15), pady=12)
        
        self.btn_open_file = ctk.CTkButton(self.header_frame, text="📁 Open Photo", command=self.open_file, width=115, font=("Segoe UI", 12, "bold"))
        self.btn_open_file.pack(side="left", padx=5, pady=12)
        
        self.btn_open_folder = ctk.CTkButton(self.header_frame, text="📂 Open Folder", command=self.open_folder, width=115, font=("Segoe UI", 12, "bold"))
        self.btn_open_folder.pack(side="left", padx=5, pady=12)
        
        self.btn_save = ctk.CTkButton(self.header_frame, text="💾 Save Tags", command=self.save_current, width=115, fg_color="#10b981", hover_color="#059669", font=("Segoe UI", 12, "bold"))
        self.btn_save.pack(side="left", padx=10, pady=12)
        
        # Output Format Selector
        self.lbl_format = ctk.CTkLabel(self.header_frame, text="Output Format:", font=("Segoe UI", 11, "bold"))
        self.lbl_format.pack(side="left", padx=(10, 5), pady=12)
        
        self.combo_format = ctk.CTkComboBox(self.header_frame, values=["Original", "JPEG", "PNG", "WebP"], width=100, font=("Segoe UI", 11))
        self.combo_format.pack(side="left", padx=(0, 15), pady=12)
        
        # Export Files Button (Generates Output 1a, 1b, 2a, 2b)
        self.btn_export_annotated = ctk.CTkButton(
            self.header_frame, 
            text="🎨 Export Files", 
            command=self.export_annotated, 
            width=135, 
            fg_color="#a855f7", 
            hover_color="#9333ea", 
            font=("Segoe UI", 12, "bold")
        )
        self.btn_export_annotated.pack(side="left", padx=(15, 5), pady=12)
        
        # Fine-Tune Output 2b Button
        self.btn_finetune_2b = ctk.CTkButton(
            self.header_frame, 
            text="✏️ Fine-Tune", 
            command=self.open_editor_2b, 
            width=130, 
            fg_color="#0284c7", 
            hover_color="#0369a1", 
            font=("Segoe UI", 12, "bold")
        )
        self.btn_finetune_2b.pack(side="left", padx=5, pady=12)
        
        # Right header section: Tag editing helpers
        self.btn_clear_tags = ctk.CTkButton(self.header_frame, text="❌ Clear All", command=self.clear_all_tags, width=100, fg_color="#ef4444", hover_color="#dc2626", font=("Segoe UI", 11, "bold"))
        self.btn_clear_tags.pack(side="right", padx=15, pady=12)
        
        self.btn_redetect = ctk.CTkButton(self.header_frame, text="🔄 Re-Detect Faces", command=self.redetect_faces, width=120, fg_color="#3b82f6", hover_color="#2563eb", font=("Segoe UI", 11, "bold"))
        self.btn_redetect.pack(side="right", padx=5, pady=12)
        
        # ----------------------------------------------------
        # 2. Main Area (Split: Left Canvas, Right Sidebar)
        # ----------------------------------------------------
        self.main_split = ctk.CTkFrame(self, fg_color="transparent")
        self.main_split.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self.main_split.grid_columnconfigure(0, weight=3) # Canvas
        self.main_split.grid_columnconfigure(1, weight=1) # Sidebar
        self.main_split.grid_rowconfigure(0, weight=1)
        
        # Left Panel: Canvas Container
        self.canvas_container = ctk.CTkFrame(self.main_split, corner_radius=10, fg_color="#111827")
        self.canvas_container.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=0)
        self.canvas_container.grid_rowconfigure(0, weight=1)
        self.canvas_container.grid_columnconfigure(0, weight=1)
        
        # The Bounding Box Canvas
        self.canvas = tk.Canvas(self.canvas_container, bg="#111827", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        # Canvas mouse event bindings
        self.canvas.bind("<Configure>", self.on_canvas_resize)
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<Motion>", self.on_canvas_motion)
        self.canvas.bind("<Leave>", self.on_canvas_leave)
        
        # Panning bindings (Right Click Drag)
        self.canvas.bind("<ButtonPress-3>", self.on_pan_press)
        self.canvas.bind("<B3-Motion>", self.on_pan_drag)
        self.canvas.bind("<ButtonRelease-3>", self.on_pan_release)
        
        # Zoom bindings (Mouse Wheel)
        self.canvas.bind("<MouseWheel>", self.on_mouse_zoom)
        self.canvas.bind("<Button-4>", lambda event: self.on_mouse_zoom_linux(event, True))
        self.canvas.bind("<Button-5>", lambda event: self.on_mouse_zoom_linux(event, False))
        
        # Right Panel: Sidebar Controls
        self.sidebar_frame = ctk.CTkFrame(self.main_split, corner_radius=10, width=320)
        self.sidebar_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=0)
        self.sidebar_frame.grid_propagate(False)
        
        # Sidebar grid configuration
        self.sidebar_frame.grid_rowconfigure(0, weight=0) # Instructions Card
        self.sidebar_frame.grid_rowconfigure(1, weight=0) # Description header
        self.sidebar_frame.grid_rowconfigure(2, weight=0) # Description textbox
        self.sidebar_frame.grid_rowconfigure(3, weight=0) # Style Settings Frame
        self.sidebar_frame.grid_rowconfigure(4, weight=0) # Faces header
        self.sidebar_frame.grid_rowconfigure(5, weight=1) # Faces scrollframe
        self.sidebar_frame.grid_rowconfigure(6, weight=0) # Credit label
        self.sidebar_frame.grid_columnconfigure(0, weight=1)
        
        # Sidebar: Quick Instructions Card
        self.instr_card = ctk.CTkFrame(self.sidebar_frame, fg_color="#1e293b", corner_radius=8, border_width=1, border_color="#334155")
        self.instr_card.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 10))
        
        self.instr_title = ctk.CTkLabel(self.instr_card, text="ℹ️ Quick Instructions", font=("Segoe UI", 12, "bold"), text_color="#38bdf8", anchor="w")
        self.instr_title.pack(fill="x", padx=10, pady=(8, 2))
        
        instr_text = (
            "1. Open a photo or an entire folder.\n"
            "2. Faces are automatically detected.\n"
            "3. Remove false detections by clicking ✕.\n"
            "4. Type names next to face crops on the right.\n"
            "5. Click & drag on image to manually add boxes.\n"
            "6. Enter a general photo description if desired.\n"
            "7. Click 'Save Tags' to write EXIF/XMP metadata to photo.\n"
            "8. Click 'Export Files' to generate HTML/SVG/Rendered outputs.\n"
            "9. Click 'Fine-Tune' to adjust Output 2-b badges.\n\n"
            "💡 Pro-Tips:\n"
            "• Zoom: Scroll MouseWheel over image.\n"
            "• Pan: Right-Click and drag zoomed image.\n"
            "• Fine-Tune: Zoom, pan & drag badge circles.\n"
            "• Resize: Click a box & drag corner handles."
        )
        self.instr_desc = ctk.CTkLabel(self.instr_card, text=instr_text, font=("Segoe UI", 10.5), justify="left", text_color="#cbd5e1", anchor="w")
        self.instr_desc.pack(fill="x", padx=10, pady=(0, 8))
        
        # Sidebar: General Description Header
        self.desc_label = ctk.CTkLabel(self.sidebar_frame, text="General Photo Description", font=("Segoe UI", 13, "bold"), anchor="w")
        self.desc_label.grid(row=1, column=0, sticky="ew", padx=15, pady=(5, 5))
        
        # Sidebar: Description text input
        self.desc_textbox = ctk.CTkTextbox(self.sidebar_frame, height=70, corner_radius=6, border_width=1, border_color="#374151")
        self.desc_textbox.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 15))
        self.desc_textbox.bind("<KeyRelease>", self.on_description_changed)
        
        # Sidebar: Style Settings Card (v2.2)
        self.style_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.style_frame.grid(row=3, column=0, sticky="ew", padx=15, pady=(0, 15))
        self.style_frame.grid_columnconfigure(0, weight=1)
        self.style_frame.grid_columnconfigure(1, weight=1)
        
        self.lbl_style_color = ctk.CTkLabel(self.style_frame, text="Tag Color:", font=("Segoe UI", 11, "bold"), anchor="w")
        self.lbl_style_color.grid(row=0, column=0, sticky="w", padx=(0, 5), pady=(0, 2))
        
        self.combo_style_color = ctk.CTkComboBox(
            self.style_frame, 
            values=["Teal", "Blue", "Purple", "Green", "Orange/Red"], 
            width=135, 
            font=("Segoe UI", 11),
            command=lambda val: self.draw_canvas()
        )
        self.combo_style_color.grid(row=1, column=0, sticky="ew", padx=(0, 5))
        self.combo_style_color.set("Teal")
        
        self.lbl_style_font_size = ctk.CTkLabel(self.style_frame, text="Font Size:", font=("Segoe UI", 11, "bold"), anchor="w")
        self.lbl_style_font_size.grid(row=0, column=1, sticky="w", padx=(5, 0), pady=(0, 2))
        
        self.combo_style_font_size = ctk.CTkComboBox(
            self.style_frame, 
            values=["Micro (0.5x)", "Small (0.7x)", "Auto (1.0x)", "Medium (1.2x)", "Large (1.5x)", "X-Large (2.0x)"], 
            width=135, 
            font=("Segoe UI", 11),
            command=lambda val: self.draw_canvas()
        )
        self.combo_style_font_size.grid(row=1, column=1, sticky="ew", padx=(5, 0))
        self.combo_style_font_size.set("Auto (1.0x)")
        
        # Sidebar: Faces Header
        self.faces_header = ctk.CTkLabel(self.sidebar_frame, text="People in Photo", font=("Segoe UI", 13, "bold"), anchor="w")
        self.faces_header.grid(row=4, column=0, sticky="ew", padx=15, pady=(0, 5))
        
        # Sidebar: Scrollable Faces container
        self.faces_scroll = ctk.CTkScrollableFrame(self.sidebar_frame, fg_color="transparent")
        self.faces_scroll.grid(row=5, column=0, sticky="nsew", padx=5, pady=(0, 5))
        
        # Sidebar Credit Card with logo
        self.credit_card = ctk.CTkFrame(self.sidebar_frame, fg_color="#1e293b", corner_radius=8, border_width=1, border_color="#334155")
        self.credit_card.grid(row=6, column=0, sticky="ew", padx=15, pady=(5, 12))
        
        if hasattr(self, 'app_logo_small') and self.app_logo_small:
            self.lbl_credit_icon = ctk.CTkLabel(self.credit_card, image=self.app_logo_small, text="")
            self.lbl_credit_icon.pack(side="left", padx=(8, 4), pady=6)
            
        self.credit_label = ctk.CTkLabel(
            self.credit_card, 
            text="Created by Alireza Mostaghasi (2026) | v.2.4", 
            font=("Segoe UI", 10, "bold"), 
            text_color="#94a3b8"
        )
        self.credit_label.pack(side="left", padx=(0, 8), pady=6)
        
        # ----------------------------------------------------
        # 3. Bottom Control & Navigation Bar (Agency-Grade Design Layout)
        # ----------------------------------------------------
        self.bottom_frame = ctk.CTkFrame(self, height=54, corner_radius=0, fg_color="#090d16", border_width=1, border_color="#1e293b")
        self.bottom_frame.grid(row=2, column=0, sticky="ew", padx=0, pady=0)
        
        # Left Section: Photo Navigation Card
        self.nav_card = ctk.CTkFrame(self.bottom_frame, fg_color="#111827", corner_radius=8, border_width=1, border_color="#1f2937")
        self.nav_card.pack(side="left", padx=12, pady=7)
        
        self.btn_prev = ctk.CTkButton(self.nav_card, text="◀ Prev", command=self.prev_image, width=68, height=28, font=("Segoe UI", 11, "bold"), fg_color="#1f2937", hover_color="#374151", text_color="#f3f4f6", corner_radius=6)
        self.btn_prev.pack(side="left", padx=4, pady=4)
        
        self.counter_frame = ctk.CTkFrame(self.nav_card, fg_color="#0f172a", corner_radius=6, border_width=1, border_color="#1e293b")
        self.counter_frame.pack(side="left", padx=4, pady=4)
        
        self.lbl_counter = ctk.CTkLabel(self.counter_frame, text="No Photos Loaded", font=("Segoe UI", 11, "bold"), text_color="#e2e8f0", width=120)
        self.lbl_counter.pack(padx=8, pady=2)
        
        self.btn_next = ctk.CTkButton(self.nav_card, text="Next ▶", command=self.next_image, width=68, height=28, font=("Segoe UI", 11, "bold"), fg_color="#1f2937", hover_color="#374151", text_color="#f3f4f6", corner_radius=6)
        self.btn_next.pack(side="left", padx=4, pady=4)
        
        # Center Section: Viewport Controls Toolbar Card (Zoom & Pan)
        self.zoom_frame = ctk.CTkFrame(self.bottom_frame, fg_color="#111827", corner_radius=8, border_width=1, border_color="#1f2937")
        self.zoom_frame.pack(side="left", expand=True, anchor="center", pady=7)
        
        # Zoom controls
        self.btn_zoom_out = ctk.CTkButton(self.zoom_frame, text="➖", command=self.zoom_out, width=28, height=28, font=("Segoe UI", 11, "bold"), fg_color="#1f2937", hover_color="#374151", text_color="#38bdf8", corner_radius=6)
        self.btn_zoom_out.pack(side="left", padx=(5, 2), pady=4)
        
        self.zoom_pill = ctk.CTkFrame(self.zoom_frame, fg_color="#0f172a", corner_radius=6, border_width=1, border_color="#1e293b")
        self.zoom_pill.pack(side="left", padx=2, pady=4)
        
        self.lbl_zoom_level = ctk.CTkLabel(self.zoom_pill, text="Zoom: 100%", font=("Segoe UI", 11, "bold"), text_color="#38bdf8", width=75)
        self.lbl_zoom_level.pack(padx=4, pady=2)
        
        self.btn_zoom_in = ctk.CTkButton(self.zoom_frame, text="➕", command=self.zoom_in, width=28, height=28, font=("Segoe UI", 11, "bold"), fg_color="#1f2937", hover_color="#374151", text_color="#38bdf8", corner_radius=6)
        self.btn_zoom_in.pack(side="left", padx=2, pady=4)
        
        self.btn_zoom_reset = ctk.CTkButton(self.zoom_frame, text="🔄 100%", command=self.zoom_reset, width=58, height=28, font=("Segoe UI", 9.5, "bold"), fg_color="#374151", hover_color="#4b5563", text_color="#e2e8f0", corner_radius=6)
        self.btn_zoom_reset.pack(side="left", padx=(4, 8), pady=4)
        
        # Vertical Separator
        self.lbl_sep = ctk.CTkLabel(self.zoom_frame, text="│", font=("Segoe UI", 12), text_color="#374151")
        self.lbl_sep.pack(side="left", padx=2, pady=4)
        
        # Pan controls
        self.btn_pan_mode = ctk.CTkButton(
            self.zoom_frame, 
            text="🖐️ Pan Tool", 
            command=self.toggle_pan_mode, 
            width=88, 
            height=28, 
            font=("Segoe UI", 10, "bold"), 
            fg_color="#374151", 
            hover_color="#4b5563",
            text_color="#e5e7eb",
            corner_radius=6
        )
        self.btn_pan_mode.pack(side="left", padx=4, pady=4)
        
        self.btn_pan_left = ctk.CTkButton(self.zoom_frame, text="◄", command=lambda: self.pan_step("left"), width=28, height=28, font=("Segoe UI", 10, "bold"), fg_color="#1f2937", hover_color="#374151", text_color="#38bdf8", corner_radius=6)
        self.btn_pan_left.pack(side="left", padx=1, pady=4)
        
        self.btn_pan_up = ctk.CTkButton(self.zoom_frame, text="▲", command=lambda: self.pan_step("up"), width=28, height=28, font=("Segoe UI", 10, "bold"), fg_color="#1f2937", hover_color="#374151", text_color="#38bdf8", corner_radius=6)
        self.btn_pan_up.pack(side="left", padx=1, pady=4)
        
        self.btn_pan_down = ctk.CTkButton(self.zoom_frame, text="▼", command=lambda: self.pan_step("down"), width=28, height=28, font=("Segoe UI", 10, "bold"), fg_color="#1f2937", hover_color="#374151", text_color="#38bdf8", corner_radius=6)
        self.btn_pan_down.pack(side="left", padx=1, pady=4)
        
        self.btn_pan_right = ctk.CTkButton(self.zoom_frame, text="►", command=lambda: self.pan_step("right"), width=28, height=28, font=("Segoe UI", 10, "bold"), fg_color="#1f2937", hover_color="#374151", text_color="#38bdf8", corner_radius=6)
        self.btn_pan_right.pack(side="left", padx=(1, 5), pady=4)
        
        # Right Section: Status Indicator Card
        self.status_card = ctk.CTkFrame(self.bottom_frame, fg_color="#111827", corner_radius=8, border_width=1, border_color="#1f2937")
        self.status_card.pack(side="right", padx=12, pady=7)
        
        self.lbl_status_icon = ctk.CTkLabel(self.status_card, text="🟢", font=("Segoe UI", 9))
        self.lbl_status_icon.pack(side="left", padx=(8, 2), pady=4)
        
        self.lbl_status = ctk.CTkLabel(self.status_card, text="Please open a photo or folder to begin.", font=("Segoe UI", 10.5, "italic"), text_color="#cbd5e1")
        self.lbl_status.pack(side="left", padx=(2, 10), pady=4)
        
    # ----------------------------------------------------
    # Core Image Loading and UI Redrawing
    # ----------------------------------------------------
    def load_image(self, path):
        if not path:
            return
            
        # Check for unsaved changes in current photo
        if self.is_modified:
            if messagebox.askyesno("Unsaved Changes", "Save changes to current photo before moving?"):
                self.save_current()
                
        self.current_image_path = path
        self.set_status(f"Loading {os.path.basename(path)}...")
        
        try:
            # 1. Reset selection states and zoom parameters
            self.selected_face_idx = None
            self.hovered_face_idx = None
            self.drawing = False
            self.faces = []
            self.zoom_factor = 1.0
            self.view_center_x = 0.5
            self.view_center_y = 0.5
            if hasattr(self, 'lbl_zoom_level'):
                self.lbl_zoom_level.configure(text="Zoom: 100%")
            if hasattr(self, 'combo_format'):
                self.combo_format.set("Original")
            
            # 2. Open image in PIL using BytesIO to release the file lock on Windows
            import io
            with open(path, "rb") as f:
                img_data = f.read()
            self.original_pil_image = Image.open(io.BytesIO(img_data))
            self.original_pil_image.load()
            
            # 3. Read tags & description
            data = read_photo_metadata(path)
            self.faces = data['tags']
            self.description = data['description']
            
            # 4. If no tags, trigger auto face detection
            if not self.faces:
                self.set_status("Detecting faces in background...")
                self.faces = detect_faces(path)
                if self.faces:
                    self.set_status(f"Auto-detected {len(self.faces)} face(s).")
                else:
                    self.set_status("No faces auto-detected. Click & drag on canvas to manually tag a face.")
            else:
                self.set_status(f"Loaded {len(self.faces)} tags from metadata.")
                
            self.sort_faces()
            self.is_modified = False
            
            # 5. Populate Description text box
            self.desc_textbox.delete("1.0", "end")
            if self.description:
                self.desc_textbox.insert("1.0", self.description)
                
            # 6. Rebuild layout
            self.rebuild_sidebar()
            self.draw_canvas()
            self.update_navigation_controls()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load image {path}: {e}")
            self.set_status("Error loading image.")
            
    def draw_canvas(self):
        if not self.original_pil_image:
            return
            
        # Get canvas dimensions
        canvas_w = max(50, self.canvas.winfo_width())
        canvas_h = max(50, self.canvas.winfo_height())
        
        # Clear previous overlay elements (background is cached and tagged bg_image)
        self.canvas.delete("overlay")
        
        # Caching check for background image
        current_key = (self.current_image_path, canvas_w, canvas_h, self.zoom_factor, self.view_center_x, self.view_center_y)
        if not hasattr(self, 'last_bg_key') or self.last_bg_key != current_key:
            self.last_bg_key = current_key
            self.canvas.delete("bg_image")
            
            # Original dimensions
            orig_w, orig_h = self.original_pil_image.size
            
            # Compute scaling factor to fit image in canvas
            base_scale = min(canvas_w / orig_w, canvas_h / orig_h)
            scale = base_scale * self.zoom_factor
            
            # Visible original image dimensions
            crop_w = min(orig_w, canvas_w / scale)
            crop_h = min(orig_h, canvas_h / scale)
            
            # Clamp view center so crop box stays inside image bounds
            half_visible_w_norm = (crop_w / 2.0) / orig_w
            self.view_center_x = max(half_visible_w_norm, min(1.0 - half_visible_w_norm, self.view_center_x))
            
            half_visible_h_norm = (crop_h / 2.0) / orig_h
            self.view_center_y = max(half_visible_h_norm, min(1.0 - half_visible_h_norm, self.view_center_y))
            
            # Crop boundaries in original pixels
            crop_left = self.view_center_x * orig_w - crop_w / 2.0
            crop_right = self.view_center_x * orig_w + crop_w / 2.0
            crop_top = self.view_center_y * orig_h - crop_h / 2.0
            crop_bottom = self.view_center_y * orig_h + crop_h / 2.0
            
            # Display dimensions on canvas
            display_w = int(orig_w * scale) if orig_w * scale < canvas_w else canvas_w
            display_h = int(orig_h * scale) if orig_h * scale < canvas_h else canvas_h
            
            self.pad_x = (canvas_w - display_w) // 2
            self.pad_y = (canvas_h - display_h) // 2
            
            # Crop and resize display portion
            cropped = self.original_pil_image.crop((crop_left, crop_top, crop_right, crop_bottom))
            resized_pil = cropped.resize((display_w, display_h), Image.Resampling.LANCZOS)
            self.tk_image = ImageTk.PhotoImage(resized_pil)
            
            # Draw image centered
            self.canvas.create_image(canvas_w // 2, canvas_h // 2, image=self.tk_image, anchor="center", tags="bg_image")
            self.canvas.tag_lower("bg_image")
            
        # Draw face bounding boxes
        color_style = self.get_selected_color_style()
        selected_color = "#a855f7"  # Purple for selection
        default_color = color_style["hex"]
        hover_color = "#f59e0b" # Warm Amber/Orange for hover
        
        font_style = self.get_selected_font_size_style()
        font_multiplier = font_style["scale"]
        base_font_size = max(8, int(9 * font_multiplier))
        label_font = ("Segoe UI", base_font_size, "bold")
        
        for idx, face in enumerate(self.faces):
            # Calculate top-left and size on canvas
            cx, cy = self.normalized_to_canvas(face['x'] - face['w']/2.0, face['y'] - face['h']/2.0)
            w_px, h_px = self.normalized_size_to_canvas(face['w'], face['h'])
            
            # Formatting variables based on hover/selection state
            if idx == self.selected_face_idx:
                outline_color = selected_color
                box_width = 3
            elif idx == self.hovered_face_idx:
                outline_color = hover_color
                box_width = 3
            else:
                outline_color = default_color
                box_width = 2
                
            # Draw bounding box
            self.canvas.create_rectangle(cx, cy, cx + w_px, cy + h_px, outline=outline_color, width=box_width, tags="overlay")
            
            # If selected, draw resize handles at the 4 corners
            if idx == self.selected_face_idx:
                handle_size = 6
                corners = [
                    (cx, cy),                  # Top-Left
                    (cx + w_px, cy),           # Top-Right
                    (cx, cy + h_px),           # Bottom-Left
                    (cx + w_px, cy + h_px)     # Bottom-Right
                ]
                for hx, hy in corners:
                    self.canvas.create_rectangle(
                        hx - handle_size/2, hy - handle_size/2,
                        hx + handle_size/2, hy + handle_size/2,
                        fill=selected_color, outline="white", width=1, tags="overlay"
                    )
            
            # Draw label background and text above box
            name = face['name'].strip() if face['name'] else f"{idx + 1}"
            
            # Reposition text if near the top boundary
            label_y = cy - 15 if cy - 15 > 0 else cy + 5
            label_text_id = self.canvas.create_text(cx + 2, label_y, text=name, fill="white", font=label_font, anchor="nw", tags="overlay")
            lbl_bbox = self.canvas.bbox(label_text_id)
            if lbl_bbox:
                # Add background for visibility
                lbl_bg = self.canvas.create_rectangle(lbl_bbox[0]-4, lbl_bbox[1]-1, lbl_bbox[2]+4, lbl_bbox[3]+1, fill="#111827", outline=outline_color, width=1, tags="overlay")
                self.canvas.tag_lower(lbl_bg, label_text_id)
            
        # Draw description overlay at the bottom if mouse in background and description is set
        if self.mouse_in_canvas and self.hovered_face_idx is None and self.description:
            overlay_h = 35
            # Draw solid background bar
            self.canvas.create_rectangle(0, canvas_h - overlay_h, canvas_w, canvas_h, fill="#1f2937", outline="", tags="overlay")
            # Draw description text
            self.canvas.create_text(canvas_w // 2, canvas_h - (overlay_h // 2), 
                                    text=f"Description: {self.description}", 
                                    fill="#f3f4f6", font=("Segoe UI", 11, "italic"), anchor="center", tags="overlay")
            
        # Draw hover face tag tooltip near mouse cursor if hovering over a face
        if self.mouse_in_canvas and self.hovered_face_idx is not None:
            x = self.mouse_x
            y = self.mouse_y
            
            face = self.faces[self.hovered_face_idx]
            name = face['name'].strip() if face['name'] else f"{self.hovered_face_idx + 1}"
            
            tooltip_txt = self.canvas.create_text(x + 15, y + 15, text=name, fill="white", font=("Segoe UI", 10, "bold"), anchor="nw", tags="overlay")
            tt_bbox = self.canvas.bbox(tooltip_txt)
            if tt_bbox:
                tt_bg = self.canvas.create_rectangle(tt_bbox[0]-6, tt_bbox[1]-3, tt_bbox[2]+6, tt_bbox[3]+3, fill="#2563eb", outline="#3b82f6", width=1, tags="overlay")
                self.canvas.tag_lower(tt_bg, tooltip_txt)

    def rebuild_sidebar(self):
        # 1. Clear existing face items
        for widget in self.faces_scroll.winfo_children():
            widget.destroy()
            
        self.face_images = []
        self.face_entries = []
        
        if not self.original_pil_image:
            return
            
        orig_w, orig_h = self.original_pil_image.size
        
        # 2. Build entries for each face
        for idx, face in enumerate(self.faces):
            # Face card frame
            card_frame = ctk.CTkFrame(self.faces_scroll, fg_color="#1f2937" if idx != self.selected_face_idx else "#374151", corner_radius=8)
            card_frame.pack(fill="x", padx=5, pady=4)
            card_frame.grid_columnconfigure(0, weight=0) # Number label
            card_frame.grid_columnconfigure(1, weight=0) # Thumbnail
            card_frame.grid_columnconfigure(2, weight=1) # Entry field
            card_frame.grid_columnconfigure(3, weight=0) # Delete button
            
            # Number Label
            lbl_num = ctk.CTkLabel(card_frame, text=f"{idx + 1}", font=("Segoe UI", 12, "bold"), width=25, text_color="#14b8a6")
            lbl_num.grid(row=0, column=0, padx=(8, 2), pady=8)
            lbl_num.bind("<Button-1>", lambda event, i=idx: self.select_face(i))
            
            # Crop face thumbnail from original PIL image
            left = int((face['x'] - face['w'] / 2.0) * orig_w)
            top = int((face['y'] - face['h'] / 2.0) * orig_h)
            right = int((face['x'] + face['w'] / 2.0) * orig_w)
            bottom = int((face['y'] + face['h'] / 2.0) * orig_h)
            
            # Clamp crop bounds to image limits
            left = max(0, min(orig_w, left))
            top = max(0, min(orig_h, top))
            right = max(0, min(orig_w, right))
            bottom = max(0, min(orig_h, bottom))
            
            # Build and display thumbnail
            thumbnail_label = None
            if right > left and bottom > top:
                try:
                    cropped = self.original_pil_image.crop((left, top, right, bottom))
                    # Resize to 50x50 crop
                    cropped = cropped.resize((50, 50), Image.Resampling.LANCZOS)
                    ctk_thumb = ctk.CTkImage(light_image=cropped, dark_image=cropped, size=(50, 50))
                    
                    # Prevent garbage collection
                    self.face_images.append(ctk_thumb)
                    
                    thumbnail_label = ctk.CTkLabel(card_frame, image=ctk_thumb, text="")
                    thumbnail_label.grid(row=0, column=1, padx=8, pady=8)
                except Exception as e:
                    print("Error cropping thumbnail:", e)
                    
            if not thumbnail_label:
                # Fallback empty placeholder
                thumbnail_label = ctk.CTkLabel(card_frame, text="👤", font=("Segoe UI", 24))
                thumbnail_label.grid(row=0, column=1, padx=8, pady=8)
                
            # Bind thumbnail click to select face
            thumbnail_label.bind("<Button-1>", lambda event, i=idx: self.select_face(i))
            
            # Name input field
            var = tk.StringVar(value=face['name'])
            # We trace modifications to mark file as dirty
            var.trace_add("write", lambda *args, i=idx, v=var: self.on_name_changed(i, v))
            
            entry = ctk.CTkEntry(card_frame, textvariable=var, placeholder_text="Enter name...", font=("Segoe UI", 12))
            entry.grid(row=0, column=2, sticky="ew", padx=(0, 5), pady=8)
            entry.bind("<FocusIn>", lambda event, i=idx: self.select_face(i))
            self.face_entries.append(entry)
            
            # Delete button
            btn_delete = ctk.CTkButton(card_frame, text="✕", width=26, height=26, fg_color="#374151", hover_color="#ef4444", text_color="gray", font=("Segoe UI", 10, "bold"), command=lambda i=idx: self.delete_face(i))
            btn_delete.grid(row=0, column=3, padx=8, pady=8)
            
    # ----------------------------------------------------
    # Coordinate Mapping Helpers for Zoom & Pan
    # ----------------------------------------------------
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
            self.is_modified = True
            
            self.draw_canvas()

    def get_selected_color_style(self):
        color_map = {
            "Teal": {"hex": "#14b8a6", "rgb": (20, 184, 166), "hover": "rgba(20, 184, 166, 0.15)"},
            "Blue": {"hex": "#3b82f6", "rgb": (59, 130, 246), "hover": "rgba(59, 130, 246, 0.15)"},
            "Purple": {"hex": "#a855f7", "rgb": (168, 85, 247), "hover": "rgba(168, 85, 247, 0.15)"},
            "Green": {"hex": "#10b981", "rgb": (16, 185, 129), "hover": "rgba(16, 185, 129, 0.15)"},
            "Orange/Red": {"hex": "#f97316", "rgb": (249, 115, 22), "hover": "rgba(249, 115, 22, 0.15)"}
        }
        val = self.combo_style_color.get()
        return color_map.get(val, color_map["Teal"])

    def get_selected_font_size_style(self):
        font_size_map = {
            "Micro (0.5x)": {"scale": 0.5, "px": 8},
            "Small (0.7x)": {"scale": 0.7, "px": 10},
            "Auto (1.0x)": {"scale": 1.0, "px": 13},
            "Medium (1.2x)": {"scale": 1.2, "px": 16},
            "Large (1.5x)": {"scale": 1.5, "px": 20},
            "X-Large (2.0x)": {"scale": 2.0, "px": 26}
        }
        val = self.combo_style_font_size.get()
        return font_size_map.get(val, font_size_map["Auto (1.0x)"])

    # ----------------------------------------------------
    # Canvas Event Handlers
    # ----------------------------------------------------
    def on_canvas_resize(self, event):
        self.draw_canvas()
        
    def on_canvas_press(self, event):
        if not self.original_pil_image:
            return
            
        if self.is_pan_mode:
            self.on_pan_press(event)
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
            
        if self.is_pan_mode:
            self.on_pan_drag(event)
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
        if self.is_pan_mode:
            self.on_pan_release(event)
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
                self.is_modified = True
                
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
            self.canvas.configure(cursor="")
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
            self.btn_pan_mode.configure(fg_color="#0284c7", hover_color="#0369a1", text="🖐️ Pan Active")
            self.canvas.configure(cursor="fleur")
            self.set_status("Pan Tool active: Left-Click & drag to pan photo, or click ⬅️⬆️⬇️➡️ arrows.")
        else:
            self.btn_pan_mode.configure(fg_color="#4b5563", hover_color="#374151", text="🖐️ Pan Tool")
            self.canvas.configure(cursor="")
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
        self.canvas.configure(cursor="")
            
    def on_canvas_leave(self, event):
        self.mouse_in_canvas = False
        self.hovered_resize_handle = None
        self.canvas.configure(cursor="")
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
            self.is_modified = True
            
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
                self.is_modified = True
                
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
            self.is_modified = True
            self.set_status("Description modified.")
            
    def clear_all_tags(self):
        if not self.faces and not self.description:
            return
            
        if messagebox.askyesno("Clear All", "Are you sure you want to clear all face tags and the description for this image?"):
            self.faces = []
            self.description = ""
            self.is_modified = True
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
            self.is_modified = True
            self.selected_face_idx = None
            self.hovered_face_idx = None
            self.rebuild_sidebar()
            self.draw_canvas()
            self.set_status(f"Auto-detected {len(self.faces)} face(s).")
            
    # ----------------------------------------------------
    # Save & File Navigation Functions
    # ----------------------------------------------------
    def save_current(self):
        if not self.current_image_path:
            return
            
        self.set_status("Saving tags and updating metadata...")
        self.sort_faces()
        
        # Read textbox to make sure we get the final edited description
        self.description = self.desc_textbox.get("1.0", "end-1c").strip()
        
        # Determine target path and format
        selected_fmt = self.combo_format.get()
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
                
        # Call the metadata writer
        if is_conversion:
            success = write_photo_metadata(target_path, self.faces, self.description, original_path=self.current_image_path)
        else:
            success = write_photo_metadata(target_path, self.faces, self.description)
            
        if success:
            old_path = self.current_image_path
            
            if is_conversion:
                # Ask user if they wish to delete original file
                if messagebox.askyesno("Convert Format", f"Successfully converted and saved to {os.path.basename(target_path)}.\n\nDo you want to delete the original file ({os.path.basename(old_path)})?"):
                    try:
                        os.remove(old_path)
                    except Exception as e:
                        print(f"Error deleting original file: {e}")
                        
                # Update current image path and navigation list
                self.current_image_path = target_path
                if self.image_list and 0 <= self.current_image_idx < len(self.image_list):
                    self.image_list[self.current_image_idx] = target_path
            
            self.is_modified = False
            self.set_status("Metadata successfully saved to image!")
            messagebox.showinfo("Saved", f"Metadata successfully saved to {os.path.basename(target_path)}!")
            
            # Rebuild sidebar and reload displays
            self.rebuild_sidebar()
            self.draw_canvas()
            self.update_navigation_controls()
        else:
            messagebox.showerror("Error", "Failed to write tags to file metadata.")
            self.set_status("Error saving metadata.")
            
    def export_annotated(self):
        if not self.current_image_path:
            self.set_status("No image loaded to export.")
            messagebox.showwarning("No Image", "Please load an image before exporting rendered versions.")
            return
            
        self.set_status("Generating annotated images...")
        self.sort_faces()
        
        # Make sure description and tags are synchronized (read from textbox if modified)
        self.description = self.desc_textbox.get("1.0", "end-1c").strip()
        
        selected_fmt = self.combo_format.get()
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
        
        # Fetch style settings
        color_style = self.get_selected_color_style()
        font_size_style = self.get_selected_font_size_style()
        
        # 1. Export Output 2-a Numbered (draw_names = False)
        success_num = draw_annotations_on_image(self.current_image_path, self.faces, numbered_path, draw_names=False, color_style=color_style, font_size_style=font_size_style, description=self.description)
        
        # 2. Export Output 2-b Tagged (draw_names = True)
        success_tag = draw_annotations_on_image(self.current_image_path, self.faces, tagged_path, draw_names=True, color_style=color_style, font_size_style=font_size_style, description=self.description)
        
        # 3. Export Output 1-a (Interactive HTML) & Output 1-b (Interactive SVG)
        success_html = write_interactive_html(self.current_image_path, self.faces, self.description, color_style=color_style, font_size_style=font_size_style)
        success_svg = write_interactive_svg(self.current_image_path, self.faces, self.description, color_style=color_style, font_size_style=font_size_style)
        
        if success_num and success_tag:
            self.set_status("Annotated images & HTML/SVG exported successfully!")
            messagebox.showinfo("Export Success", 
                                f"Successfully exported all outputs with selected color & font size:\n\n"
                                f"• Output 1-a (Interactive HTML): {os.path.basename(os.path.splitext(self.current_image_path)[0] + '_interactive.html')}\n"
                                f"• Output 1-b (Interactive SVG): {os.path.basename(os.path.splitext(self.current_image_path)[0] + '_interactive.svg')}\n"
                                f"• Output 2-a (Numbered Image): {os.path.basename(numbered_path)}\n"
                                f"• Output 2-b (Tagged Image): {os.path.basename(tagged_path)}")
        else:
            self.set_status("Error exporting annotated files.")
            messagebox.showerror("Export Error", "Failed to export one or more files.")
            
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
        if file_path:
            # Single file mode clears image list
            self.image_list = [file_path]
            self.current_image_idx = 0
            self.load_image(file_path)
            
    def open_folder(self):
        folder_path = filedialog.askdirectory(title="Open Photo Folder")
        if folder_path:
            # Gather all supported images
            self.image_list = []
            for root, _, files in os.walk(folder_path):
                for f in files:
                    if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                        self.image_list.append(os.path.join(root, f))
                # Only search top-level folder
                break
                
            self.image_list.sort()
            
            if self.image_list:
                self.current_image_idx = 0
                self.load_image(self.image_list[0])
            else:
                messagebox.showinfo("No images found", "No supported image files found in selected directory.")
                
    def prev_image(self):
        if self.current_image_idx > 0:
            self.current_image_idx -= 1
            self.load_image(self.image_list[self.current_image_idx])
            
    def next_image(self):
        if self.current_image_idx < len(self.image_list) - 1:
            self.current_image_idx += 1
            self.load_image(self.image_list[self.current_image_idx])
            
    def update_navigation_controls(self):
        # Update buttons enabled state
        if len(self.image_list) <= 1:
            self.btn_prev.configure(state="disabled")
            self.btn_next.configure(state="disabled")
            self.lbl_counter.configure(text="1 of 1 Photo")
        else:
            self.btn_prev.configure(state="normal" if self.current_image_idx > 0 else "disabled")
            self.btn_next.configure(state="normal" if self.current_image_idx < len(self.image_list) - 1 else "disabled")
            self.lbl_counter.configure(text=f"Photo {self.current_image_idx + 1} of {len(self.image_list)}")
            
    def set_status(self, text):
        self.lbl_status.configure(text=text)
        if hasattr(self, 'lbl_status_icon'):
            if "Error" in text or "Failed" in text:
                self.lbl_status_icon.configure(text="🔴")
            elif "Saving" in text or "Running" in text or "Exporting" in text:
                self.lbl_status_icon.configure(text="🟡")
            else:
                self.lbl_status_icon.configure(text="🟢")
        self.update_idletasks()
        
    def open_editor_2b(self):
        if not self.current_image_path or not self.faces:
            messagebox.showinfo("No Photo Loaded", "Please open a photo with face tags first.")
            return
        Output2bEditorWindow(self)

    def on_closing(self):
        if self.is_modified:
            if messagebox.askyesno("Unsaved Changes", "You have unsaved changes. Do you want to save them before exiting?"):
                self.save_current()
        self.destroy()

class Output2bEditorWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Fine-Tune Output 2-b (Photo Tagger v.2.4)")
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
            command=lambda val: self.render_editor_canvas()
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
            command=lambda val: self.render_editor_canvas()
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
        self.lbl_zoom.configure(text=f"Zoom: {int(self.zoom_factor * 100)}%")
        self.render_editor_canvas()

    def zoom_out(self):
        self.zoom_factor = max(1.0, self.zoom_factor / 1.25)
        if self.zoom_factor == 1.0:
            self.view_center_x = 0.5
            self.view_center_y = 0.5
        self.lbl_zoom.configure(text=f"Zoom: {int(self.zoom_factor * 100)}%")
        self.render_editor_canvas()

    def zoom_reset(self):
        self.zoom_factor = 1.0
        self.view_center_x = 0.5
        self.view_center_y = 0.5
        self.lbl_zoom.configure(text="Zoom: 100%")
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
        
        # Generate base image with footer legend (for_editor=True skips baking badges into PIL image)
        draw_annotations_on_image(
            self.parent.current_image_path, 
            self.parent.faces, 
            temp_out, 
            draw_names=True, 
            color_style=color_style, 
            font_size_style=font_style, 
            description=self.parent.description,
            for_editor=True
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
                    
                    # Create uniform circle badge oval item with tag_ prefix
                    self.canvas.create_oval(
                        cx_canvas - badge_r_canvas, cy_canvas - badge_r_canvas, 
                        cx_canvas + badge_r_canvas, cy_canvas + badge_r_canvas, 
                        fill=color_hex, outline="#ffffff", width=2, 
                        tags=("badge_element", f"tag_{idx}")
                    )
                    
                    num_str = str(idx + 1)
                    
                    # Create centered text item inside badge with uniform font size
                    self.canvas.create_text(
                        cx_canvas, cy_canvas, 
                        text=num_str, fill="#ffffff", 
                        font=("Segoe UI", font_size_canvas, "bold"), 
                        tags=("badge_element", f"tag_{idx}")
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
                
            self.dragging_idx = None

    def save_and_export(self):
        self.destroy()
        self.parent.export_annotated()

if __name__ == "__main__":
    app = PhotoTaggerApp()
    app.mainloop()
