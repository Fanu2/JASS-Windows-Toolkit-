# JASS Image Viewer Pro

**Version 1.0.0**

A lightweight, polished PySide6 image viewer for fast local image browsing.

## Features

- Open a folder or a single image
- Thumbnail browser
- JPG/JPEG, PNG, BMP, WEBP, GIF, TIFF/TIF and ICO
- Previous/next navigation
- Mouse-wheel scrolling
- `Ctrl + mouse wheel` zoom
- Fit and actual-size viewing
- Zoom in/out
- Rotate left/right
- Horizontal/vertical flip
- Save transformed image as a new file
- Copy displayed image to clipboard
- Configurable slideshow
- Favorites and favorites-only filter
- Sort by name, modification time and file size
- Image information dialog
- Context menu
- Open containing folder
- Fullscreen
- Confirmation before moving an image to Trash
- Keyboard shortcuts
- Offline/local-first
- No AI, cloud service, database, OpenCV or Pillow dependency

## Installation — MX Linux / Debian

```bash
python3 -m pip install PySide6
```

If your system Python is externally managed:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install PySide6
```

Run:

```bash
python3 JASS_Image_Viewer_Pro_v1.0.py
```

## Windows

```powershell
py -m pip install PySide6
py .\JASS_Image_Viewer_Pro_v1.0.py
```

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| Ctrl+O | Open folder |
| Ctrl+Shift+O | Open image |
| Ctrl+S | Save As |
| Ctrl+C | Copy image |
| F | Fit image |
| 1 | Actual size |
| + / - | Zoom |
| L / R | Rotate |
| I | Image information |
| Left / Right | Previous / Next |
| Space | Slideshow |
| F11 | Fullscreen |
| Esc | Exit fullscreen |
| Delete | Move current image to Trash |

## Favorites

Favorites are stored locally in:

```text
~/.jass_image_viewer_favorites.json
```

No information is uploaded.

## Safety

Viewing, zooming, rotating and flipping do not modify the source image.

**Save As** creates a new file.

Delete requires confirmation. On Linux, the current implementation moves the file into the user's desktop Trash directory rather than immediately destroying it.

## Current limitation

Folder browsing lists images directly inside the selected folder. Recursive subfolder browsing is not included in v1.0.

## Future ideas

- Recursive folder scanning
- Drag-and-drop folders
- EXIF metadata
- EXIF orientation
- Animated GIF controls
- Contact sheet generator
- Duplicate-image detection
- Batch resize/conversion
- Crop and basic adjustments
- Histogram
- Search, tags and ratings
- RAW support
- Image comparison
- Recent folders
- Custom thumbnail size

## License

Choose the license appropriate for your repository.
