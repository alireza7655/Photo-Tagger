# PT / Photo Tagger (Rev.2.3)

**PT** is a modern desktop application built for Windows 11 (with file executable `PT.exe` and source script `PT.py`, displaying as **`Photo Tagger`** in the UI/UX) to easily tag human faces and edit descriptions inside photos. The app supports dynamic loading, tagging, and saving across **JPEG**, **PNG**, and **WebP** images, and automatically generates interactive sharing versions (HTML and SVG) with hover overlays.

**Created by Alireza Mostaghasi (2026) | Rev.2.3**

---

## Key Features

1. **Multi-Format Metadata Tagging**: Full read/write metadata support for **JPEG**, **PNG**, and **WebP** files. 
   - **PNG**: Tags are written to the `iTXt` chunk with the key `"XML:com.adobe.xmp"`.
   - **WebP & JPEG**: Natively accept raw XMP packets via PIL's save parameters.
2. **Selectable Output Format & Conversion**: Convert images between JPEG, PNG, and WebP on save. Transparent images are automatically converted to RGB when saving to JPEG to prevent encoding crashes.
3. **Canvas Zoom & Pan**:
   - **Zoom**: Scroll the MouseWheel over the canvas to zoom in/out (up to 10.0x) centered around the mouse cursor.
   - **Pan**: Right-Click and drag zoomed images to pan the viewport.
   - **Toolbar**: Dedicated Zoom In (`➕`), Zoom Out (`➖`), and `Reset` buttons with a dynamic Zoom Level label in the bottom bar.
4. **Offline Automatic Face Detection**: Built-in face recognition using OpenCV Haar Cascades (frontal and profile views) to instantly outline faces when an image is loaded. Spatial sorting ensures natural left-to-right, top-to-bottom numbering order.
5. **Interactive Bounding Boxes**: Hover over a bounding box on the canvas to see the person's name in a tooltip; click to instantly select and rename. Unnamed faces display their simple index number (e.g., `1`, `2`) dynamically.
6. **Lag-Free Manual Bounding Box Drawing**: Click and drag a box directly on the canvas to manually outline and tag any missed faces. Dotted drawing rectangles render instantly without lag by using direct canvas coordinates.
7. **Resize Bounding Boxes**: Rescale selected face boxes dynamically by dragging any of the corner resize handles or outline edges. The editor cursor changes automatically. Sidebar thumbnails update only on release to maintain high performance.
8. **Interactive HTML Exporter**: Generates a self-contained `.html` file embedding the image as a Base64 string. Opening the webpage shows the photo and name tags on hover.
9. **Interactive SVG Exporter**: Exports an `.svg` vector image with hover outline highlights and native tooltips. Bounding boxes remain completely invisible until hovered.
10. **Style Settings & Custom Sizes**: Choose custom tag colors (Teal, Blue, Purple, Green, Orange/Red, Yellow, White, Black) and font/tag size multipliers from **Micro (0.5x)** to **X-Large (2.0x)**.
11. **`✏️ Fine-Tune` Interactive Layout Editor (Rev.2.3)**:
    - **Live Badge Dragging**: Click and drag any number badge directly on the image to fine-tune its position with millimeter precision.
    - **Editor Zoom & Pan**: Scroll MouseWheel to zoom in/out and Right-Click Drag to pan across crowded photos.
    - **Live Color & Size Tuning**: Change badge colors and sizes dynamically in real-time.
    - **`Save and Export Output`**: Saves custom badge coordinates to photo metadata and exports Output 2-b.
12. **Output 2-b Rendered Output with Free Space Footer**:
    - Zero face rectangles (faces remain 100% visible and unmasked).
    - Uniform circular number badges placed on person bodies or adjacent free space.
    - Extended free space footer below the photo displaying **PHOTO DESCRIPTION** and a multi-column **TAGGED PERSONS** legend.
13. **Dynamic 1:1 Number Synchronization**: Strict tag order preservation guarantees 1:1 index matching across the UI sidebar, main canvas, Output 2-a, Output 2-b, and the footer legend.
14. **Batch Navigation**: Quickly step through a folder of images with Next/Previous navigation and unsaved changes warnings.

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
2. **Zoom & Pan (Crowded Photos)**:
   - Scroll the mouse wheel up over the image to zoom in, and scroll down to zoom out.
   - Press and hold the right mouse button and drag to pan around.
   - Use the bottom toolbar buttons (`➕` / `➖` / `Reset`) to control zoom level.
3. **Review Face Detections**:
   - The app will automatically analyze the image and draw bounding boxes around detected faces in spatial order. Bounding box thumbnails will appear in the right sidebar.
4. **Assign Names**:
   - In the sidebar, click the text box next to a face crop (labeled with its face index number) and type the person's name.
5. **Manually Add Face Boxes**:
   - Simply **click and drag** a rectangle over any un-detected face on the canvas to manually add a box.
6. **Write Photo Description**:
   - Type a general description of the photo in the **General Photo Description** box in the sidebar.
7. **Fine-Tune Output 2-b Layout**:
   - Click **`✏️ Fine-Tune`** in the top action toolbar.
   - Scroll MouseWheel to zoom into crowded clusters.
   - Left-click and drag any badge circle to place it in the exact desired position.
   - Adjust Tag Size (Micro 0.5x to X-Large 2.0x) or Tag Color.
   - Click **`💾 Save and Export Output`** to save your fine-tuned image.
8. **Save & Export**:
   - Select your desired format (`Original`, `JPEG`, `PNG`, `WebP`).
   - Click **💾 Save Tags** (green) to write XMP metadata and export interactive HTML/SVG files.
   - Click **🎨 Export Rendered** (purple) to export Output 2-a (`_numbered`) and Output 2-b (`_tagged`).

---

## Explanation of Output Files

When saving or exporting, the following files are updated or created:

1. **Tagged Photo File (e.g. `.jpg`, `.png`, `.webp`)** (created on **Save Tags**):
   - Contains embedded face region coordinates and description headers in XMP metadata.
2. **`[PhotoName]_interactive.html` (Interactive Webpage)** (created on **Save Tags**):
   - Portable standalone HTML file. Opening in any browser shows hover outline overlays and name tooltips.
3. **`[PhotoName]_interactive.svg` (Interactive Image)** (created on **Save Tags**):
   - Vector SVG file wrapping the photo with hover highlights and tooltips.
4. **`[PhotoName]_numbered.[ext]` (Output 2-a: Rendered Numbered Photo)** (created on **Export Rendered**):
   - Rendered photo copy with face bounding box rectangles and numbers drawn over face boxes.
5. **`[PhotoName]_tagged.[ext]` (Output 2-b: Rendered Tagged Photo)** (created on **Export Rendered** / **Fine-Tune**):
   - Rendered photo copy with zero face boxes, uniform number badges placed on person bodies/adjacent space, and an extended free space footer containing the **General Photo Description** and **Tagged Persons** legend.
