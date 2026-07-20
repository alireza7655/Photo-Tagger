# PT / Photo Tagger (Rev.2.1)

**PT** is a modern desktop application built for Windows 11 (with file executable `PT.exe` and source script `PT.py`, displaying as **`Photo Tagger`** in the UI/UX) to easily tag human faces and edit descriptions inside photos. The app supports dynamic loading, tagging, and saving across **JPEG**, **PNG**, and **WebP** images, and automatically generates interactive sharing versions (HTML and SVG) with hover overlays.

**Created by Alireza Mostaghasi (2026) | Rev.2.1**

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
4. **Offline Automatic Face Detection**: Built-in face recognition using OpenCV Haar Cascades (frontal and profile views) to instantly outline faces when an image is loaded.
5. **Interactive Bounding Boxes**: Hover over a bounding box on the canvas to see the person's name in a tooltip; click to instantly select and rename. Unnamed faces display their simple index number (e.g., `1`, `2`) dynamically.
6. **Manual Bounding Box Drawing**: Click and drag a box directly on the canvas to manually outline and tag any missed faces. Coordinates map perfectly under any zoom level.
7. **Interactive HTML Exporter**: Generates a self-contained `.html` file embedding the image as a Base64 string (with the correct dynamic mime-type). Opening the webpage shows the photo and name tags on hover.
8. **Interactive SVG Exporter**: Exports an `.svg` vector image with hover outline highlights and native tooltips. Bounding boxes remain completely invisible until hovered.
9. **Dynamic Index Numbering**: Unnamed faces default to their simple index number (e.g. `1`, `2`) instead of generic labels. Removing or adding faces automatically and dynamically recalculates the numbering.
10. **Numbered Sidebar Crop List**: The sidebar displays the face index number next to each cropped thumbnail, making it easy to identify faces in crowded photos.
11. **Annotated Image Exporter**: Render and burn bounding boxes directly into the image pixels via the `🎨 Export Rendered` button, exporting a numbered-only copy and a named-and-numbered tagged copy. Bounding boxes and labels scale dynamically with image resolution for premium legibility.
12. **Batch Navigation**: Quickly step through a folder of images with Next/Previous navigation and unsaved changes warnings.

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
   - The app will automatically analyze the image and draw teal bounding boxes around detected faces. Bounding box thumbnails will appear in the right sidebar.
4. **Assign Names**:
   - In the sidebar, click the text box next to a face crop (which is labeled with its corresponding face index number) and type the person's name. The name will immediately display above the face on the canvas.
   - Alternatively, you can click on any bounding box on the canvas, and the app will automatically select and focus the correct text input in the sidebar for you.
5. **Manually Add Face Boxes**:
   - If the auto-detector misses a face, simply **click and drag** a rectangle over the face area on the canvas. A new card will instantly be added to the sidebar with an updated dynamic number label.
6. **Write Photo Description**:
   - Type a general description of the photo in the **General Photo Description** box at the top of the sidebar.
7. **Delete Incorrect Detections**:
   - Click the **✕** button on any face card in the sidebar to delete false positive detections. The numbering of all other faces in the sidebar and canvas will dynamically adjust.
8. **Save, Convert, & Export Rendered**:
   - To keep the original format, leave the **Output Format** combobox on `Original`.
   - To convert the file format, select `JPEG`, `PNG`, or `WebP` from the **Output Format** dropdown.
   - Click **💾 Save Tags** (in green) to write the metadata to the photo and generate the interactive sharing HTML and SVG versions.
   - Click **🎨 Export Rendered** (in purple) to export two copies of the image with the bounding boxes and text permanently drawn/burned onto the photo's pixels (numbered version and tagged version).

---

## Explanation of Output Files

When saving or exporting, the following files are updated or created:

1. **Tagged Photo File (e.g. `.jpg`, `.png`, `.webp`)** (created on **Save Tags**):
   - Contains embedded face region coordinates and description headers. When opened in photo managers supporting face tags (like Adobe Lightroom, classic Windows Photo Viewer, or digiKam), the tagged names will appear on hover.
2. **`[PhotoName]_interactive.html` (Interactive Webpage)** (created on **Save Tags**):
   - A single, portable file containing the photo and hover styles. Double-click to open it instantly in Edge, Chrome, or Safari. Hovering your mouse over the faces will draw smooth highlight boxes and pop up their names/numbers.
3. **`[PhotoName]_interactive.svg` (Interactive Image)** (created on **Save Tags**):
   - An XML-based vector image wrapping your photo. Opening the `.svg` image in any browser will show the hover highlights and names in native system tooltips. Bounding boxes are invisible until hovered.
4. **`[PhotoName]_numbered.[ext]` (Rendered Numbered Photo)** (created on **Export Rendered**):
   - A static image copy with the bounding boxes and simple face index numbers permanently drawn onto the photo itself. Perfect for printing or sharing as reference sheets.
5. **`[PhotoName]_tagged.[ext]` (Rendered Tagged Photo)** (created on **Export Rendered**):
   - A static image copy with the bounding boxes and names (falling back to index numbers if unnamed) permanently drawn onto the photo itself.
