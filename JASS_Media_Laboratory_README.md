# JASS Media Laboratory v1.0

A lightweight, local-first PySide6 application for inspecting and cataloguing image, audio and video collections.

## Features

- Scan a single folder recursively or non-recursively
- Detect common image, audio and video files
- Image preview with dimensions and format
- Rich audio/video metadata through optional `ffprobe`
- Duration, codecs, resolution, frame rate, bit rate, sample rate and channels
- Search by filename/path
- Filter by media type
- Sort by name, size, modified time or type
- Open selected media in the system default application
- Open containing folder
- SHA-256 content hashing
- CSV and JSON report export
- Detailed metadata dialog
- Background scanning and hashing
- Read-only analysis: originals are never modified, moved, renamed or deleted

## Requirements

Python 3.10+ and PySide6:

```bash
python3 -m pip install PySide6
```

For rich audio/video metadata on MX Linux/Debian:

```bash
sudo apt update
sudo apt install ffmpeg
```

`ffprobe` is included with FFmpeg.

## Run

```bash
python3 JASS_Media_Laboratory_v1.0.py
```

Or with a virtual environment:

```bash
source .venv/bin/activate
python JASS_Media_Laboratory_v1.0.py
```

## Supported formats

Images: JPG, JPEG, PNG, BMP, GIF, WEBP, TIFF, TIF, ICO, SVG

Video: MP4, MKV, AVI, MOV, WEBM, M4V, MPEG, MPG, TS, MTS, M2TS, 3GP, FLV

Audio: MP3, WAV, FLAC, OGG, OGA, OPUS, M4A, AAC, WMA, AIFF, AIF

Actual codec support depends on Qt image plugins and FFmpeg/ffprobe.

## Workflow

1. Browse to a media folder.
2. Choose Recursive if subfolders should be included.
3. Click Scan Media.
4. Search, filter or sort the results.
5. Select a file to preview it and see quick metadata.
6. Use Details for the complete metadata view.
7. Use SHA-256 when a content fingerprint is required.
8. Export CSV or JSON for further analysis.

## v1.0 design

This release is intentionally an **inspection and reporting tool**, not a media editor. It does not automatically transcode, delete, move or alter files. Audio/video playback is delegated to the system's default player.

## Future versions

Possible additions:

- video thumbnails/contact sheets
- built-in video/audio playback
- audio waveform
- EXIF/IPTC/XMP inspection
- GPS metadata
- duplicate and perceptual-similarity detection
- corrupted-media checks
- FFmpeg technical reports
- media timeline
- folder comparison
- batch contact sheets
- SQLite catalogue

## License

Choose the license appropriate for your repository.

**JASS Media Laboratory — inspect your media, understand your collection, keep your originals untouched.**
