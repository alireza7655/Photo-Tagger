# Photo Tagger 3.0

Photo Tagger is a Windows desktop app for tagging people in photos, refining badge positions, and sharing annotated copies. It supports English and Persian labels and opens JPEG, PNG, and WebP files.

**Created by Alireza Mostaghasi**  
**Release date: 2026**

## Install on Windows

Download `PhotoTagger_v3.0.0.exe` from the [v3.0.0 release](https://github.com/alireza7655/Photo-Tagger/releases/tag/v3.0.0). Save it to a permanent folder and double-click it. The standalone build includes Python and its dependencies. To launch it from the desktop, create a shortcut to the executable.

## Tag and export a photo

1. **Open Photo** or **Open Folder**. If another photo is open, choose whether to add the new photo to the filmstrip or open it by itself. Use the × on a thumbnail to close it.
2. In **Tagging**, detect faces or add a tag manually, then enter names.
3. In **Layout**, drag badges into position. In **Appearance**, choose a preset, accent color, badge geometry, scale, and font. The six presets include Single Outline and Borderless.
4. Click **Save Project** to save an editable `.phototagger.json` sidecar next to the photo. Keep that file with the photo to restore names, badge positions, and appearance settings later.
5. In **Preview**, check the result and click **Export Files**. Choose Original, JPEG, PNG, or WebP where available. The app creates numbered and tagged raster copies, plus standalone interactive HTML and SVG.

**Write Tags to Photo** is a separate action that writes embedded metadata to the image. Use **Save Project** to preserve editing state without rewriting the image.

The charcoal workspace includes a scrollable inspector, zoom and fit controls, and photo rotation. Keyboard shortcuts include **Ctrl+O** to open, **Ctrl+S** to save the project, **Ctrl+E** to export, **Ctrl+0** to fit, and **F1** for Help.

## Run from source

From a Windows terminal with Python 3.12 installed:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe PT.py
```

To build the standalone executable, install PyInstaller into the same environment and run `.\.venv\Scripts\python.exe -m PyInstaller --noconfirm PT.spec`. The executable is written to `dist`.
