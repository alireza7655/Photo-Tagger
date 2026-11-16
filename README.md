# Photo Tagger 3.0.1

Photo Tagger is a Windows desktop app for tagging people in photos, refining badge positions, and sharing annotated copies. It supports English and Persian labels and opens JPEG, PNG, and WebP files.

**Created by Alireza Mostaghasi**  
**Release date: 2026**

## Install on Windows

Download and extract `PhotoTagger_v3.0.1_source.zip` from the [v3.0.1 release](https://github.com/alireza7655/Photo-Tagger/releases/tag/v3.0.1), then follow **Run from source** below. This version is supplied as a source package for personal use with Python 3.12. Windows Smart App Control may block the unsigned executable supplied with earlier releases.

## Tag and export a photo

1. **Open Photo** or **Open Folder**. If another photo is open, choose whether to add the new photo to the filmstrip or open it by itself. Use the × on a thumbnail to close it.
2. In **Tagging**, detect faces or add a tag manually, then enter names.
3. In **Layout**, drag badges into position. In **Appearance**, choose a preset, accent color, badge geometry, scale, and font. The six presets include Single Outline and Borderless.
4. Click **Save** to save an editable `.phototagger.json` sidecar next to the photo. Keep that file with the photo to restore names, badge positions, and appearance settings later.
5. In **Preview**, check the result and click **Export Files**. Choose Original, JPEG, PNG, or WebP where available. The app creates numbered and tagged raster copies, plus standalone interactive HTML and SVG.

Use the arrow beside **Save** to enable **Also write tags into the photo**. It is off by default and the app remembers your choice. Save always writes the editable project first. When enabled, it also embeds tags in the original photo, independently of the export format. If that second step fails, the app reports the failure and preserves the saved project.

The charcoal workspace includes a scrollable inspector, zoom and fit controls, and photo rotation. Keyboard shortcuts include **Ctrl+O** to open, **Ctrl+S** to save the project, **Ctrl+E** to export, **Ctrl+0** to fit, and **F1** for Help.

## Run from source

From a Windows terminal with Python 3.12 installed:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe PT.py
```

To build the standalone executable, install PyInstaller into the same environment and run `.\.venv\Scripts\python.exe -m PyInstaller --noconfirm PT.spec`. The executable is written to `dist`.
