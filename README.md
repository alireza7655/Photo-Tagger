# PT / Photo Tagger (Rev.1.0)

**PT** is a modern desktop application built for Windows 11 (with file executable `PT.exe` and source script `PT.py`, displaying as **`Photo Tagger (Rev.1.0)`** in the UI/UX) to easily tag human faces and edit descriptions inside JPEG photos. The app writes coordinates and metadata directly to standard JPEG headers (EXIF & XMP) and automatically generates interactive sharing versions (HTML and SVG) with hover name overlays.

**Created by Alireza Mostaghasi (2026) | Rev.1.0**

---

## Key Features

1. **Offline Automatic Face Detection**: Built-in face recognition using OpenCV Haar Cascades (frontal and profile views) to instantly outline faces when an image is loaded.
2. **Interactive Bounding Boxes**: Hover over a bounding box on the canvas to see the person's name in a tooltip; click to instantly select and rename.
3. **Manual Bounding Box Drawing**: Click and drag a box directly on the canvas to manually outline and tag any missed faces.
4. **JPEG Metadata Synchronization**: Saves tags directly to Microsoft Region Info (MPRI) and Metadata Working Group (MWG-RS) namespaces in XMP, and the description to EXIF `ImageDescription` (tag `270`). 
5. **Interactive HTML Exporter**: Generates a self-contained `.html` file embedding the image as a Base64 string. Anyone opening the file on any computer will see the photo and name tags on hover.
6. **Interactive SVG Exporter**: Exports an `.svg` vector image with hover outline highlights and native tooltips. Perfect for sharing as a standard image file that retains mouse hover interactivity.
7. **Batch Navigation**: Quickly step through a folder of JPEGs with Next/Previous navigation and unsaved changes warnings.

---

## How to Run the App

### Option A: Using the Standalone Executable (.exe)
You can find the compiled standalone Windows 11 executable inside the `dist` folder:
`c:\Python_Projects\Photo Tagger\dist\PT.exe`
- Double-click `PT.exe` to launch the app instantly without needing Python or external libraries.

### Option B: Running from Source
If running from source, ensure you have Python 3.10+ installed and run:

1. **Activate Virtual Environment**:
   ```powershell
   & "c:\Python_Projects\Photo Tagger\.venv\Scripts\Activate.ps1"
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
   - Click **📁 Open Photo** to tag a single photo, or **📂 Open Folder** to load all JPEGs inside a directory.
2. **Review Face Detections**:
   - The app will automatically analyze the image and draw teal bounding boxes around detected faces. Bounding box thumbnails will appear in the right sidebar.
3. **Assign Names**:
   - In the sidebar, click the text box next to a face crop and type the person's name. The name will immediately display above the face on the canvas.
   - Alternatively, you can click on any bounding box on the canvas, and the app will automatically select and focus the correct text input in the sidebar for you.
4. **Manually Add Face Boxes**:
   - If the auto-detector misses a face, simply **click and drag** a rectangle over the face area on the canvas. A new card will instantly be added to the sidebar for you to name.
5. **Write Photo Description**:
   - Type a general description of the photo in the **General Photo Description** box at the top of the sidebar.
6. **Delete Incorrect Detections**:
   - Click the **✕** button on any face card in the sidebar to delete false positive detections.
7. **Save Your Work**:
   - Click **💾 Save Tags** (in green). The app will update the JPEG metadata, and write companion HTML and SVG files.

---

## Explanation of Output Files

When you click **Save Tags**, three files are updated or created:

1. **`[PhotoName].JPG` (Original Photo)**:
   - Contains embedded face region coordinates and description headers. When opened in photo managers supporting face tags (like Adobe Lightroom, classic Windows Photo Viewer, or digiKam), the tagged names will appear on hover.
2. **`[PhotoName]_interactive.html` (Interactive Webpage)**:
   - A single, portable file containing the photo and hover styles. Double-click to open it instantly in Edge, Chrome, or Safari. Hovering your mouse over the faces will draw smooth highlight boxes and pop up their names.
3. **`[PhotoName]_interactive.svg` (Interactive Image)**:
   - An XML-based vector image wrapping your photo. When shared with others, opening the `.svg` image in any browser will show the hover highlights and names in native system tooltips. The bounding boxes are completely transparent (hidden) until the mouse cursor enters a face region.
