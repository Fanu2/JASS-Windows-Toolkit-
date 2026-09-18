# 📱 JASS Android Transfer Manager

**JASS Android Transfer Manager** is a local-first PySide6 application for moving files between Android devices and Linux.

It provides a single graphical workspace around two practical Linux/Android transfer mechanisms:

- **KDE Connect** — wireless local-network transfers
- **ADB** — direct USB/Android Debug Bridge transfers

It is designed to make everyday Android ↔ MX Linux file movement easier without introducing a cloud storage layer.

## ✨ Features

### 📤 Linux → Android

Choose a Linux file or folder and send it to the selected Android device.

With KDE Connect, files and folders can be shared through the KDE Connect command-line interface.

With ADB, the destination can be specified, for example:

```text
/sdcard/Download
/sdcard/Pictures
/sdcard/Documents
```

### 📥 Android → Linux

ADB supports direct path-based receiving:

```text
/sdcard/Download/photo.jpg
/sdcard/DCIM
/sdcard/Documents
```

Choose a Linux destination directory and receive the selected item.

For KDE Connect, Android → Linux is handled through the normal KDE Connect Android Share/Send workflow: choose the Linux computer as the recipient.

### 🗂 Android Browser

When an ADB device is connected, browse Android storage from the application.

Example:

```text
/sdcard
/sdcard/Download
/sdcard/DCIM
/sdcard/Pictures
/sdcard/Documents
```

- Directory navigation
- File listing
- Size display
- Android path display
- Receive selected item
- Copy Android path

### ⚡ Quick Destinations

Predefined Android locations:

- Downloads
- Pictures
- DCIM Camera
- Movies
- Music
- Documents

### 🔄 Device Discovery

The application detects:

- KDE Connect devices
- ADB devices

The dashboard displays:

- connection status
- backend
- device name
- transfer status

### 🕘 Session History

Records transfers performed during the current application session.

### ℹ️ Built-in Help

The Help tab explains:

- KDE Connect workflow
- ADB workflow
- Android USB debugging
- common Android paths
- security considerations

## 🔐 Safety

The manager does not automatically:

- delete files
- move files
- rename files
- clean Android storage
- synchronize folders
- upload files to a cloud service

Transfers happen only after you explicitly press a transfer button.

The application does not silently copy Android data.

### ADB warning

ADB is a powerful Android debugging interface. Only authorize computers you trust on your Android device.

### KDE Connect

KDE Connect transfers use the local network rather than a cloud storage service.

## 🚀 Installation

### KDE Connect

If KDE Connect is already installed and paired:

```bash
sudo apt install kdeconnect
```

The application uses:

```bash
kdeconnect-cli
```

Check it with:

```bash
kdeconnect-cli -a
```

### ADB

Install ADB:

```bash
sudo apt update
sudo apt install adb
```

Check:

```bash
adb devices
```

On Android, enable:

1. Developer Options
2. USB debugging
3. Authorize the Linux computer when prompted

## ▶️ Run

```bash
python3 JASS_Android_Transfer_Manager_v1.0.py
```

Install PySide6 if necessary:

```bash
sudo apt install python3-pyside6
```

or:

```bash
python3 -m pip install PySide6
```

## 📡 KDE Connect workflow

For wireless transfers:

1. Connect Android and MX Linux to the same local network.
2. Pair the Android phone with KDE Connect.
3. Confirm:

```bash
kdeconnect-cli -a
```

4. Start JASS Android Transfer Manager.
5. Select the KDE Connect device.
6. Choose a Linux file/folder.
7. Choose a destination.
8. Click **Send to Android**.

For Android → Linux:

1. Open KDE Connect on Android.
2. Use Share/Send.
3. Select the Linux computer.
4. Select files/folders.

## 🔌 ADB workflow

Connect the Android phone by USB.

Then:

```bash
adb devices
```

After accepting the authorization prompt on Android, the device should appear.

In JASS Android Transfer Manager:

1. Select the ADB device.
2. Open **Android Browser**.
3. Enter `/sdcard` or another location.
4. Double-click directories.
5. Select a file/folder.
6. Receive it to Linux.

## 📁 Common Android paths

```text
/sdcard/Download
/sdcard/DCIM
/sdcard/DCIM/Camera
/sdcard/Pictures
/sdcard/Movies
/sdcard/Music
/sdcard/Documents
```

Actual storage layout can differ between Android devices and Android versions.

## 🧠 Why build this?

Android file transfer often becomes fragmented between:

- USB cables
- KDE Connect
- Android file managers
- Linux file managers
- Downloads
- DCIM
- Documents
- individual sharing operations

JASS Android Transfer Manager provides a single control surface for the common workflows.

## 🗺️ Future roadmap

### v1.x

- transfer queue
- multiple simultaneous transfers
- cancel active transfer
- transfer speed
- ETA
- bytes transferred
- retry failed transfers
- persistent history
- drag-and-drop
- folder transfer progress
- overwrite confirmation
- skip/rename conflict options

### KDE Connect integration

- device capabilities
- battery level
- connectivity status
- remote filesystem integration where supported
- receive workflow helpers
- notification integration

### ADB integration

- full directory browser
- create remote folder
- pull multiple selections
- push multiple selections
- remote file metadata
- device storage statistics
- package/application inventory
- screenshot capture
- Android log viewer

### Advanced Android storage

- dual-pane Linux ↔ Android browser
- drag-and-drop transfers
- folder synchronization
- duplicate detection
- photo/video transfer assistant
- automatic camera import
- backup profiles
- scheduled backup

### JASS ecosystem

Potential integration with:

- **JASS Disk Space Observatory**
- **JASS File Organizer Pro**
- **JASS Media Laboratory**
- **JASS Image Viewer Pro**
- **JASS AppImage Manager**

A future version could provide a workflow such as:

**Android Camera → Transfer → Media Laboratory → Image Viewer → Archive**

## 🧭 Philosophy

> **Local transfer first. Explicit action always. No cloud required.**

The manager is intended to complement KDE Connect and ADB, not replace them.

---

**JASS Android Transfer Manager v1.0**  
MX Linux • Android • PySide6 • Local-first • Privacy-conscious
