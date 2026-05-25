import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image, ImageTk

# Import our custom modules
from metadata import read_photo_metadata, write_photo_metadata, write_interactive_html, write_interactive_svg
from detector import detect_faces

# Configure customtkinter appearance
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class PhotoTaggerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Window setup
        self.title("Photo Tagger (Rev.1.0)")
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
        
        # Drawing boxes state
        self.drawing = False
        self.draw_start_x = 0
        self.draw_start_y = 0
        self.draw_current_x = 0
        self.draw_current_y = 0
        
        # References for face thumbnails to prevent garbage collection
        self.face_images = []
        self.face_entries = []
        
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
        
        # Left header section: File actions
        self.btn_open_file = ctk.CTkButton(self.header_frame, text="📁 Open Photo", command=self.open_file, width=120, font=("Segoe UI", 12, "bold"))
        self.btn_open_file.pack(side="left", padx=15, pady=12)
        
        self.btn_open_folder = ctk.CTkButton(self.header_frame, text="📂 Open Folder", command=self.open_folder, width=120, font=("Segoe UI", 12, "bold"))
        self.btn_open_folder.pack(side="left", padx=5, pady=12)
        
        self.btn_save = ctk.CTkButton(self.header_frame, text="💾 Save Tags", command=self.save_current, width=120, fg_color="#10b981", hover_color="#059669", font=("Segoe UI", 12, "bold"))
        self.btn_save.pack(side="left", padx=15, pady=12)
        
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
        
        # Right Panel: Sidebar Controls
        self.sidebar_frame = ctk.CTkFrame(self.main_split, corner_radius=10, width=320)
        self.sidebar_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=0)
        self.sidebar_frame.grid_propagate(False)
        
        # Sidebar grid configuration
        self.sidebar_frame.grid_rowconfigure(0, weight=0) # Instructions Card
        self.sidebar_frame.grid_rowconfigure(1, weight=0) # Description header
        self.sidebar_frame.grid_rowconfigure(2, weight=0) # Description textbox
        self.sidebar_frame.grid_rowconfigure(3, weight=0) # Faces header
        self.sidebar_frame.grid_rowconfigure(4, weight=1) # Faces scrollframe
        self.sidebar_frame.grid_rowconfigure(5, weight=0) # Credit label
        self.sidebar_frame.grid_columnconfigure(0, weight=1)
        
        # Sidebar: Quick Instructions Card
        self.instr_card = ctk.CTkFrame(self.sidebar_frame, fg_color="#1e293b", corner_radius=8, border_width=1, border_color="#334155")
        self.instr_card.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 10))
        
        self.instr_title = ctk.CTkLabel(self.instr_card, text="ℹ️ Quick Instructions", font=("Segoe UI", 12, "bold"), text_color="#38bdf8", anchor="w")
        self.instr_title.pack(fill="x", padx=10, pady=(8, 2))
        
        instr_text = (
            "1. Open a Photo or Folder.\n"
            "2. Let the software auto-detect faces.\n"
            "3. Remove false detections by clicking ✕.\n"
            "4. Type names next to face crops on the right.\n"
            "5. Click & drag on image to manually add boxes.\n"
            "6. Enter a general photo description if desired.\n"
            "7. Click 'Save Tags' to save metadata and export HTML/SVG."
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
        
        # Sidebar: Faces Header
        self.faces_header = ctk.CTkLabel(self.sidebar_frame, text="People in Photo", font=("Segoe UI", 13, "bold"), anchor="w")
        self.faces_header.grid(row=3, column=0, sticky="ew", padx=15, pady=(0, 5))
        
        # Sidebar: Scrollable Faces container
        self.faces_scroll = ctk.CTkScrollableFrame(self.sidebar_frame, fg_color="transparent")
        self.faces_scroll.grid(row=4, column=0, sticky="nsew", padx=5, pady=(0, 5))
        
        # Sidebar: Developer Credit with Rev.1.0
        self.credit_label = ctk.CTkLabel(self.sidebar_frame, text="Created by Alireza Mostaghasi (2026) | Rev.1.0", font=("Segoe UI", 10, "italic"), text_color="#6b7280")
        self.credit_label.grid(row=5, column=0, sticky="ew", padx=15, pady=8)
        
        # ----------------------------------------------------
        # 3. Bottom Control & Navigation
        # ----------------------------------------------------
        self.bottom_frame = ctk.CTkFrame(self, height=45, corner_radius=0)
        self.bottom_frame.grid(row=2, column=0, sticky="ew", padx=0, pady=0)
        
        # Navigation buttons
        self.btn_prev = ctk.CTkButton(self.bottom_frame, text="◀ Previous", command=self.prev_image, width=90, font=("Segoe UI", 11, "bold"))
        self.btn_prev.pack(side="left", padx=15, pady=8)
        
        self.lbl_counter = ctk.CTkLabel(self.bottom_frame, text="No Photos Loaded", font=("Segoe UI", 11, "bold"))
        self.lbl_counter.pack(side="left", padx=10, pady=8)
        
        self.btn_next = ctk.CTkButton(self.bottom_frame, text="Next ▶", command=self.next_image, width=90, font=("Segoe UI", 11, "bold"))
        self.btn_next.pack(side="left", padx=10, pady=8)
        
        # Right aligned Status label
        self.lbl_status = ctk.CTkLabel(self.bottom_frame, text="Please open a photo or folder to begin.", font=("Segoe UI", 11, "italic"), text_color="gray")
        self.lbl_status.pack(side="right", padx=15, pady=8)
        
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
            # 1. Reset selection states
            self.selected_face_idx = None
            self.hovered_face_idx = None
            self.drawing = False
            self.faces = []
            
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
            
        # Clear previous elements
        self.canvas.delete("all")
        
        # Get canvas dimensions
        canvas_w = max(50, self.canvas.winfo_width())
        canvas_h = max(50, self.canvas.winfo_height())
        
        # Original dimensions
        orig_w, orig_h = self.original_pil_image.size
        
        # Compute scaling factor to fit image in canvas
        self.scale = min(canvas_w / orig_w, canvas_h / orig_h)
        self.disp_w = int(orig_w * self.scale)
        self.disp_h = int(orig_h * self.scale)
        
        # Offset to center image
        self.pad_x = (canvas_w - self.disp_w) // 2
        self.pad_y = (canvas_h - self.disp_h) // 2
        
        # Resize image for display
        resized_pil = self.original_pil_image.resize((self.disp_w, self.disp_h), Image.Resampling.LANCZOS)
        self.tk_image = ImageTk.PhotoImage(resized_pil)
        
        # Draw image centered
        self.canvas.create_image(canvas_w // 2, canvas_h // 2, image=self.tk_image, anchor="center")
        
        # Draw face bounding boxes
        for idx, face in enumerate(self.faces):
            # Convert normalized coordinates to canvas coordinates
            left = self.pad_x + (face['x'] - face['w'] / 2.0) * self.disp_w
            top = self.pad_y + (face['y'] - face['h'] / 2.0) * self.disp_h
            w_px = face['w'] * self.disp_w
            h_px = face['h'] * self.disp_h
            
            # Formatting variables based on hover/selection state
            if idx == self.selected_face_idx:
                outline_color = "#a855f7"  # Vibrant purple
                box_width = 3
            elif idx == self.hovered_face_idx:
                outline_color = "#38bdf8"  # Sky blue
                box_width = 3
            else:
                outline_color = "#14b8a6"  # Teal
                box_width = 2
                
            # Draw bounding box
            self.canvas.create_rectangle(left, top, left + w_px, top + h_px, outline=outline_color, width=box_width)
            
            # Draw label background and text above box
            name = face['name'].strip() if face['name'] else f"Person {idx + 1}"
            label_text_id = self.canvas.create_text(left + 2, top - 15, text=name, fill="white", font=("Segoe UI", 9, "bold"), anchor="nw")
            lbl_bbox = self.canvas.bbox(label_text_id)
            if lbl_bbox:
                # Add background for visibility
                lbl_bg = self.canvas.create_rectangle(lbl_bbox[0]-4, lbl_bbox[1]-1, lbl_bbox[2]+4, lbl_bbox[3]+1, fill="#111827", outline=outline_color, width=1)
                self.canvas.tag_lower(lbl_bg, label_text_id)
                
        # Draw manual box drag rectangle if active
        if self.drawing:
            self.canvas.create_rectangle(
                self.draw_start_x, self.draw_start_y,
                self.draw_current_x, self.draw_current_y,
                outline="#f97316", width=2, dash=(4, 4)
            )
            
        # Draw description overlay at the bottom if mouse in background and description is set
        if self.mouse_in_canvas and self.hovered_face_idx is None and self.description:
            overlay_h = 35
            # Draw solid background bar
            self.canvas.create_rectangle(0, canvas_h - overlay_h, canvas_w, canvas_h, fill="#1f2937", outline="")
            # Draw description text
            self.canvas.create_text(canvas_w // 2, canvas_h - (overlay_h // 2), 
                                    text=f"Description: {self.description}", 
                                    fill="#f3f4f6", font=("Segoe UI", 11, "italic"), anchor="center")
            
        # Draw hover face tag tooltip near mouse cursor if hovering over a face
        if self.mouse_in_canvas and self.hovered_face_idx is not None:
            x = self.mouse_x
            y = self.mouse_y
            
            face = self.faces[self.hovered_face_idx]
            name = face['name'].strip() if face['name'] else "Unnamed"
            
            tooltip_txt = self.canvas.create_text(x + 15, y + 15, text=name, fill="white", font=("Segoe UI", 10, "bold"), anchor="nw")
            tt_bbox = self.canvas.bbox(tooltip_txt)
            if tt_bbox:
                tt_bg = self.canvas.create_rectangle(tt_bbox[0]-6, tt_bbox[1]-3, tt_bbox[2]+6, tt_bbox[3]+3, fill="#2563eb", outline="#3b82f6", width=1)
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
            card_frame.grid_columnconfigure(0, weight=0) # Thumbnail
            card_frame.grid_columnconfigure(1, weight=1) # Entry field
            card_frame.grid_columnconfigure(2, weight=0) # Delete button
            
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
                    thumbnail_label.grid(row=0, column=0, padx=8, pady=8)
                except Exception as e:
                    print("Error cropping thumbnail:", e)
                    
            if not thumbnail_label:
                # Fallback empty placeholder
                thumbnail_label = ctk.CTkLabel(card_frame, text="👤", font=("Segoe UI", 24))
                thumbnail_label.grid(row=0, column=0, padx=8, pady=8)
                
            # Bind thumbnail click to select face
            thumbnail_label.bind("<Button-1>", lambda event, i=idx: self.select_face(i))
            
            # Name input field
            var = tk.StringVar(value=face['name'])
            # We trace modifications to mark file as dirty
            var.trace_add("write", lambda *args, i=idx, v=var: self.on_name_changed(i, v))
            
            entry = ctk.CTkEntry(card_frame, textvariable=var, placeholder_text="Enter name...", font=("Segoe UI", 12))
            entry.grid(row=0, column=1, sticky="ew", padx=(0, 5), pady=8)
            entry.bind("<FocusIn>", lambda event, i=idx: self.select_face(i))
            self.face_entries.append(entry)
            
            # Delete button
            btn_delete = ctk.CTkButton(card_frame, text="✕", width=26, height=26, fg_color="#374151", hover_color="#ef4444", text_color="gray", font=("Segoe UI", 10, "bold"), command=lambda i=idx: self.delete_face(i))
            btn_delete.grid(row=0, column=2, padx=8, pady=8)
            
    # ----------------------------------------------------
    # Canvas Event Handlers
    # ----------------------------------------------------
    def on_canvas_resize(self, event):
        self.draw_canvas()
        
    def on_canvas_press(self, event):
        if not self.original_pil_image:
            return
            
        # Check if click is inside the actual scaled image boundary
        if (self.pad_x <= event.x <= self.pad_x + self.disp_w) and (self.pad_y <= event.y <= self.pad_y + self.disp_h):
            # Check if clicked on an existing face box
            # Calculate clicked position in normalized coordinates
            norm_x = (event.x - self.pad_x) / self.disp_w
            norm_y = (event.y - self.pad_y) / self.disp_h
            
            clicked_idx = self.get_face_at_coords(norm_x, norm_y)
            
            if clicked_idx is not None:
                # Select the face and focus the corresponding entry widget
                self.select_face(clicked_idx)
                # Shift focus to the name entry field in the sidebar
                if clicked_idx < len(self.face_entries):
                    self.face_entries[clicked_idx].focus_set()
            else:
                # Start drawing a manual bounding box
                self.drawing = True
                self.draw_start_x = event.x
                self.draw_start_y = event.y
                self.draw_current_x = event.x
                self.draw_current_y = event.y
                self.selected_face_idx = None
                self.rebuild_sidebar()
                self.draw_canvas()
                
    def on_canvas_drag(self, event):
        if not self.drawing:
            return
            
        # Constrain dragging coordinates to the image bounds
        self.draw_current_x = max(self.pad_x, min(self.pad_x + self.disp_w, event.x))
        self.draw_current_y = max(self.pad_y, min(self.pad_y + self.disp_h, event.y))
        
        self.draw_canvas()
        
    def on_canvas_release(self, event):
        if not self.drawing:
            return
            
        self.drawing = False
        
        # Calculate width and height in pixels
        w_px = abs(self.draw_current_x - self.draw_start_x)
        h_px = abs(self.draw_current_y - self.draw_start_y)
        
        # Only create a box if it is reasonably sized (e.g. at least 15 pixels)
        if w_px > 15 and h_px > 15:
            # Map start/end pixels to normalized coords
            x1 = (self.draw_start_x - self.pad_x) / self.disp_w
            y1 = (self.draw_start_y - self.pad_y) / self.disp_h
            x2 = (self.draw_current_x - self.pad_x) / self.disp_w
            y2 = (self.draw_current_y - self.pad_y) / self.disp_h
            
            # Compute normalized center coordinates
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            nw = abs(x2 - x1)
            nh = abs(y2 - y1)
            
            # Add to faces list
            new_face = {
                'name': '',
                'x': cx,
                'y': cy,
                'w': nw,
                'h': nh
            }
            self.faces.append(new_face)
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
            
        self.mouse_in_canvas = True
        self.mouse_x = event.x
        self.mouse_y = event.y
        
        # Calculate position in normalized coordinates
        norm_x = (event.x - self.pad_x) / self.disp_w
        norm_y = (event.y - self.pad_y) / self.disp_h
        
        prev_hovered = self.hovered_face_idx
        self.hovered_face_idx = self.get_face_at_coords(norm_x, norm_y)
        
        # Redraw if hover target changed, or if there is an active hovered face
        # (so the tooltip follows the mouse), or if description is present
        if self.hovered_face_idx is not None or self.hovered_face_idx != prev_hovered or self.description:
            self.draw_canvas()
            
    def on_canvas_leave(self, event):
        self.mouse_in_canvas = False
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
                self.redraw_debounce_id = self.canvas.after_cancel(self.redraw_debounce_id) if hasattr(self, 'redraw_debounce_id') else None
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
            
    def redetect_faces(self):
        if not self.current_image_path:
            return
            
        if messagebox.askyesno("Re-detect Faces", "This will clear current face tags and run the automatic detector. Proceed?"):
            self.set_status("Running face detection...")
            self.faces = detect_faces(self.current_image_path)
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
            
        self.set_status("Saving tags to JPEG metadata...")
        
        # Read textbox to make sure we get the final edited description
        self.description = self.desc_textbox.get("1.0", "end-1c").strip()
        
        success = write_photo_metadata(self.current_image_path, self.faces, self.description)
        if success:
            # Also write the interactive HTML and SVG versions next to it
            write_interactive_html(self.current_image_path, self.faces, self.description)
            write_interactive_svg(self.current_image_path, self.faces, self.description)
            
            self.is_modified = False
            self.set_status("Metadata, HTML and SVG successfully saved!")
            messagebox.showinfo("Saved", "Metadata successfully saved to JPEG file, and interactive HTML/SVG versions created!")
            # Rebuild sidebar to sync thumbnails (in case they shifted slightly)
            self.rebuild_sidebar()
            self.draw_canvas()
        else:
            messagebox.showerror("Error", "Failed to write tags to file metadata.")
            self.set_status("Error saving metadata.")
            
    def open_file(self):
        file_path = filedialog.askopenfilename(
            title="Open JPEG Image",
            filetypes=[("JPEG files", "*.jpg;*.jpeg"), ("All files", "*.*")]
        )
        if file_path:
            # Single file mode clears image list
            self.image_list = [file_path]
            self.current_image_idx = 0
            self.load_image(file_path)
            
    def open_folder(self):
        folder_path = filedialog.askdirectory(title="Open Photo Folder")
        if folder_path:
            # Gather all JPEGs
            self.image_list = []
            for root, dirs, files in os.walk(folder_path):
                for f in files:
                    if f.lower().endswith(('.jpg', '.jpeg')):
                        self.image_list.append(os.path.join(root, f))
                # Only search top-level folder
                break
                
            self.image_list.sort()
            
            if self.image_list:
                self.current_image_idx = 0
                self.load_image(self.image_list[0])
            else:
                messagebox.showinfo("No JPEGs found", "No JPEG files found in selected directory.")
                
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
        self.update_idletasks()
        
    def on_closing(self):
        if self.is_modified:
            if messagebox.askyesno("Unsaved Changes", "You have unsaved changes. Do you want to save them before exiting?"):
                self.save_current()
        self.destroy()

if __name__ == "__main__":
    app = PhotoTaggerApp()
    app.mainloop()
