# Photo Tagger (v.2.5)

**Photo Tagger** is a modern desktop application built for Windows 11 (with standalone executable `PT.exe` and source script `PT.py`) to easily tag human faces and edit metadata inside photos. The app supports dynamic loading, tagging, and saving across **JPEG**, **PNG**, and **WebP** images, and automatically generates interactive sharing versions (HTML and SVG) as well as rendered output files.

**Created by Alireza Mostaghasi (2026) | v.2.5**

---

## Key Features

1. **Modern Dark Theme & Visual Hierarchy (v2.5)**:
   - Built with a Catppuccin Mocha / Deep Slate dark palette (`#181825` base, `#1e1e2e` header, `#252536` cards, `#313244` subtle borders).
   - Structured button hierarchy: Highlighted primary action (`💾 Save Tags` in Sage Green, `🎨 Export Files` in Lavender), outline ghost utility buttons (`📁 Open Photo`, `📂 Open Folder`, `✏️ Fine-Tune`), and subtle red ghost style for destructive actions (`✕ Clear All`).
   - Embedded custom application brand logo icon and `v.2.5` version badge.

2. **Collapsible Quick Instructions Panel**:
   - Instruction card includes a `▼ Expand` / `▲ Collapse` toggle button.
   - Collapsed by default to maximize vertical scrollable space for the **People in Photo** tag list.

3. **Viewport Zoom & Complete Pan System**:
   - **MouseWheel Zoom**: Scroll over the canvas to zoom in/out (up to 10.0x) centered around the mouse cursor.
   - **Pan Tool Toggle (`🖐️ Pan Tool`)**: Toggle left-click drag panning mode directly on the main canvas.
   - **Directional Arrow Pad**: Uniform 4-way solid triangle buttons (`◀`, `▲`, `▼`, `▶`) for step-by-step viewport panning.
   - **Right-Click Drag Panning**: Native mouse drag panning for power users.

4. **Continuous Unified Footer Bar**:
   - Single continuous footer strip (`fg_color="#181825"`) with photo navigation on the left, viewport controls in the center, and a real-time status card on the right featuring dynamic color status dots (`🟢` Ready, `🟡` Processing, `🔴` Error).

5. **Multi-Format Metadata Tagging**: Full read/write metadata support for **JPEG**, **PNG**, and **WebP** files. 
   - **PNG**: Tags are written to the `iTXt` chunk with the key `"XML:com.adobe.xmp"`.
   - **WebP & JPEG**: Natively accept raw XMP packets via PIL's save parameters.

6. **Selectable Output Format & Conversion**: Convert images between JPEG, PNG, and WebP on save. Transparent images are automatically converted to RGB when saving to JPEG to prevent encoding crashes.

7. **Offline Automatic Face Detection**: Built-in face recognition using OpenCV Haar Cascades (frontal and profile views) to instantly outline faces when an image is loaded. Spatial sorting ensures natural left-to-right, top-to-bottom numbering order.

8. **Zero-Lag Live Drag Cadre**: Click and drag a rectangle over the canvas to manually outline missed faces. The selection cadre (`manual_drag_rect`) draws instantly with zero press latency using dual-layer high-contrast lines.

9. **Resize & Fine-Tune Bounding Boxes**:
   - Rescale selected face boxes on the canvas by dragging any of the 4 corner resize handles.
   - **`✏️ Fine-Tune` Interactive Layout Editor**: Click and drag badge circles live over crowded photos with real-time color and font size adjustments.

10. **Interactive HTML & SVG Exporters**:
    - **Interactive HTML Exporter**: Generates a self-contained `.html` file embedding the image as a Base64 string with hover outline overlays and tooltips.
    - **Interactive SVG Exporter**: Exports an `.svg` vector image with hover outline highlights and native tooltips.

11. **Output 2-b Rendered Output with Free Space Footer**:
    - Zero face rectangles (faces remain 100% visible and unmasked).
    - Uniform circular number badges placed on person bodies or adjacent free space.
    - Dynamic rounded pill badges for 1-to-3 digit numbers (`125`).
    - Extended free space footer below the photo displaying **PHOTO DESCRIPTION** and a multi-column **TAGGED PERSONS** legend with multi-line text wrapping.

12. **Decoupled Button Workflow**:
    - **💾 Save Tags**: Writes EXIF/XMP metadata directly into the image file.
    - **🎨 Export Files**: Generates and exports all 4 outputs (1a HTML, 1b SVG, 2a Numbered, 2b Tagged).

---

## How to Run the App

### Option A: Using the Standalone Executable (.exe)
You can find the compiled standalone Windows 11 executable inside the `dist` folder:
`C:\Coding_Projects\Photo Tagger\dist\PT.exe`
- Double-click `PT.exe` to launch the app instantly without needing Python or external libraries.

### Option B: Running from Source
If running from source, ensure you have Python 3.10+ installed and run:

1. **Activate Virtual Environment**:
   ```powershell
   & "C:\Coding_Projects\Photo Tagger\.venv\Scripts\Activate.ps1"
   ```
2. **Install Dependencies**:
   ```powershell
   pip install -r requirements.txt
   ```
3. **Launch the App**:
   ```powershell
   python "PT.py"
   ```

---

## Detailed Step-by-Step Usage Guide

1. **Open Photos**:
   - Click **📁 Open Photo** to tag a single photo, or **📂 Open Folder** to load all JPEGs, PNGs, and WebPs inside a directory.
2. **Zoom & Pan Controls**:
   - Scroll the mouse wheel to zoom in/out.
   - Click **🖐️ Pan Tool** to drag-pan with left-click, use **◀ ▲ ▼ ▶** arrow buttons, or hold Right-Click and drag.
3. **Review Face Detections & Assign Names**:
   - Review automatically detected face boxes in spatial order.
   - Type names next to face crops in the right sidebar.
4. **Manually Add Face Boxes**:
   - Click and drag a rectangle over any undetected face on the canvas to manually tag it.
5. **Write Photo Description & Style Settings**:
   - Type a general photo description and customize Tag Color / Font Size.
6. **Fine-Tune Output 2-b Layout**:
   - Click **`✏️ Fine-Tune`** in the top action toolbar.
   - Drag badge circles to place them in the exact desired position.
   - Click **`💾 Save & Export Output 2-b`**.
7. **Save & Export**:
   - Select desired format (`Original`, `JPEG`, `PNG`, `WebP`).
   - Click **💾 Save Tags** (Sage Green) to save EXIF/XMP metadata directly into the image file.
   - Click **🎨 Export Files** (Lavender) to export Output 1a (HTML), Output 1b (SVG), Output 2a (Numbered), and Output 2b (Tagged).

---

## Explanation of Output Files

1. **Tagged Photo File (e.g. `.jpg`, `.png`, `.webp`)** (updated on **Save Tags**):
   - Contains embedded face region coordinates and description headers in XMP metadata.
2. **`[PhotoName]_interactive.html` (Interactive Webpage)** (created on **Export Files**):
   - Portable standalone HTML file showing hover outline overlays and name tooltips.
3. **`[PhotoName]_interactive.svg` (Interactive Image)** (created on **Export Files**):
   - Vector SVG file wrapping the photo with hover highlights and tooltips.
4. **`[PhotoName]_numbered.[ext]` (Output 2-a: Rendered Numbered Photo)** (created on **Export Files**):
   - Rendered photo copy with face bounding box rectangles and numbers drawn over face boxes.
5. **`[PhotoName]_tagged.[ext]` (Output 2-b: Rendered Tagged Photo)** (created on **Export Files** / **Fine-Tune**):
   - Rendered photo copy with zero face boxes, uniform number badges placed on person bodies/adjacent space, and an extended free space footer containing the **General Photo Description** and **Tagged Persons** legend.
