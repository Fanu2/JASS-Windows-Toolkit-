# JASS Android File Commander v1.0

**Linux ↔ Android • Dual Pane • ADB + KDE Connect**

JASS Android File Commander is a lightweight PySide6 dual-pane file manager for transferring files and folders between a Linux computer and an Android device.

The primary backend is **ADB** because it provides direct filesystem browsing and both-direction file/folder transfers.

## ✨ Features

### 🐧 Linux pane
- Browse local folders
- Up-directory navigation
- File/folder listing
- File size
- Modified time
- Multi-selection
- Open Linux folder

### 📱 Android pane
- Browse `/sdcard`
- Navigate into Android folders
- Up-directory navigation
- File/folder listing
- File size
- Modified time
- Android quick locations:
  - Downloads
  - Pictures
  - DCIM
  - Movies
  - Music
  - Documents
- Multi-selection
- Basic text-file preview

### 🔄 Transfers

**Linux → Android**
- files
- folders
- multiple selections

**Android → Linux**
- files
- folders
- multiple selections
- choose destination folder

Transfers use:

```text
adb push
adb pull
```

### 📁 Android folder creation

Create a folder directly in the current Android directory.

### 🔌 Device discovery

The application detects authorized ADB devices and displays the device/model identifier.

## Installation — MX Linux / Debian

Install ADB:

```bash
sudo apt update
sudo apt install adb
```

Install PySide6:

```bash
python3 -m pip install PySide6
```

Run:

```bash
python3 JASS_Android_File_Commander_v1.0.py
```

## Android setup

On the Android phone:

1. Open **Settings → About phone**.
2. Enable Developer Options if necessary.
3. Enable **USB debugging**.
4. Connect the phone to Linux using USB.
5. Accept the RSA authorization prompt on the phone.

Check:

```bash
adb devices
```

You should see something similar to:

```text
XXXXXXXX    device
```

Then launch JASS Android File Commander.

## Wireless ADB

If your Android device supports wireless debugging, Android can be paired/configured for wireless ADB using the standard Android developer options.

The application itself uses normal `adb` commands and therefore does not require a proprietary cloud service.

## KDE Connect

KDE Connect can remain useful alongside this application for quick sharing.

Install:

```bash
sudo apt install kdeconnect
```

Check:

```bash
kdeconnect-cli -a
```

For whole-folder management, however, this application uses ADB as its primary filesystem backend.

## 🔒 Safety

The application does **not** automatically delete or move files.

Browsing is read-only.

Transfers only happen when you explicitly press:

```text
→ Copy to Android
← Copy to Linux
```

Creating an Android folder is also an explicit action.

## ⚠️ Android storage limitations

Modern Android versions use scoped storage and restrict access to some application-private directories.

The most useful general-purpose location is normally:

```text
/sdcard
```

or:

```text
/storage/emulated/0
```

Access to private application directories may require additional Android permissions/root access and is outside the scope of v1.0.

## Troubleshooting

### `adb: command not found`

Install:

```bash
sudo apt install adb
```

### Device shows `unauthorized`

Run:

```bash
adb devices
```

Then unlock the phone and accept the USB debugging authorization prompt.

### No device appears

Try:

```bash
adb kill-server
adb start-server
adb devices
```

Also check the USB cable and Android USB mode.

### Transfer fails

Check that:
- the Android destination is writable
- the Linux destination has sufficient space
- the selected device is still connected
- the phone is unlocked if Android requires it

## Roadmap — v2.0

- KDE Connect backend for receiving/sending
- Wireless ADB pairing assistant
- Drag-and-drop between panes
- Transfer queue
- Transfer speed
- ETA
- Pause/cancel
- Retry failed transfers
- Overwrite/conflict dialog
- Rename/delete with explicit confirmation
- Create folders on both sides
- File preview
- Image thumbnails
- Android storage statistics
- Device information dashboard
- Battery information
- Photo import wizard
- Automatic camera-photo organization
- Backup profiles
- Saved transfer jobs
- Transfer history
- Checksums
- Compare Linux/Android folders
- Synchronization preview
- Hidden-file option
- Search
- Sort controls
- Dark theme
- Multiple connected devices

## Suggested Repository

```text
JASS-Android-File-Commander/
├── JASS_Android_File_Commander_v1.0.py
├── README.md
└── examples/
```

**JASS Android File Commander**  
*Two panes. One workspace. Linux ↔ Android.*
