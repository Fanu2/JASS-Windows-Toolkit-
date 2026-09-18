# JASS Image Vault Pro

**Version:** 2.0\
**Platform:** Windows / Linux / macOS\
**GUI:** PySide6\
**Encryption:** AES-256-GCM\
**Key Derivation:** scrypt

JASS Image Vault Pro is a local desktop application for encrypting and
decrypting image files with a password.

It was redesigned from the original Tkinter/OpenCV Image Encryption
Decryption application into a modern PySide6 application. The original
program used a NumPy floating-point transformation and saved encrypted
data as JPEG. JASS Image Vault Pro instead encrypts the original file
bytes using authenticated AES-256-GCM and stores the encrypted result in
a dedicated `.jassvault` container.

------------------------------------------------------------------------

## 1. Features

### Modern GUI

-   Clean PySide6 desktop interface
-   Original/source image preview
-   Result preview
-   Image dimensions
-   File-size information
-   Zoom controls
-   Encrypt / Decrypt operation selector
-   Password visibility toggle
-   Password-strength indicator
-   Progress bar
-   Status messages
-   Non-blocking encryption/decryption worker

### Encryption

-   AES-256-GCM authenticated encryption
-   Password-based key derivation with scrypt
-   Random salt for every encrypted file
-   Random nonce for every encryption operation
-   Authentication tag supplied by GCM
-   Original file bytes are encrypted directly
-   Original image is not overwritten
-   Encrypted files use the `.jassvault` extension

### Decryption

-   Password verification through AES-GCM authentication
-   Recovery of the original file bytes
-   Attempts to recover the original filename from the vault metadata
-   Decrypted image preview
-   Authentication failure when the password is wrong or the vault has
    been modified

### Supported source image formats

The application accepts common image formats including:

-   PNG
-   JPG / JPEG
-   BMP
-   WEBP
-   TIFF / TIF

The encrypted output is stored as:

``` text
filename.jassvault
```

------------------------------------------------------------------------

# 2. Requirements

## Python

Python 3.10+ is recommended.

Check your Python version:

``` bash
python3 --version
```

On Windows:

``` powershell
py --version
```

## Required packages

The application requires:

``` text
PySide6
cryptography
```

Install them with:

``` bash
python3 -m pip install PySide6 cryptography
```

On Windows:

``` powershell
py -m pip install PySide6 cryptography
```

If you use a virtual environment, activate it first and then install the
packages.

------------------------------------------------------------------------

# 3. Running the Application

## Linux / MX Linux

From the directory containing the program:

``` bash
python3 JASS_Image_Vault_Pro_v2.0.py
```

If you use a specific Python installation:

``` bash
python3.12 JASS_Image_Vault_Pro_v2.0.py
```

## Windows

Using the Python launcher:

``` powershell
py JASS_Image_Vault_Pro_v2.0.py
```

or:

``` powershell
python JASS_Image_Vault_Pro_v2.0.py
```

## macOS

``` bash
python3 JASS_Image_Vault_Pro_v2.0.py
```

------------------------------------------------------------------------

# 4. Encrypting an Image

1.  Start JASS Image Vault Pro.
2.  Select **Encrypt image**.
3.  Click **Browse...**.
4.  Select the image.
5.  Enter a password.
6.  Check the password-strength indicator.
7.  Click **🔐 Encrypt Image**.
8.  Select the destination for the encrypted vault.

The default suggested filename is:

``` text
original-name.jassvault
```

For example:

``` text
family-photo.jpg
```

becomes:

``` text
family-photo.jassvault
```

The original image remains unchanged.

------------------------------------------------------------------------

# 5. Decrypting a Vault

1.  Start the application.
2.  Select **Decrypt vault**.
3.  Click **Browse...**.
4.  Select the `.jassvault` file.
5.  Enter the password used during encryption.
6.  Click **🔓 Decrypt Vault**.
7.  Choose where to save the recovered image.

If the password is correct and the vault has not been damaged or
modified, the original bytes are recovered.

------------------------------------------------------------------------

# 6. Important: Password Management

The password is critical.

JASS Image Vault Pro does **not** provide a password-recovery mechanism.

If the password is forgotten, the encrypted vault cannot be recovered
through the application.

Use a strong password or passphrase.

A good password should preferably:

-   Be at least 12 characters
-   Use multiple words or a long passphrase
-   Avoid easily guessed personal information
-   Not be reused for important accounts
-   Be stored securely in a password manager if necessary

The password-strength indicator is only a convenience indicator. It does
not mathematically guarantee password strength.

------------------------------------------------------------------------

# 7. Encryption Format

JASS Image Vault Pro v2 uses a custom `.jassvault` container.

The file begins with an application format marker:

``` text
JASSIMG2
```

The vault contains metadata needed for decryption, including:

-   Format version
-   Encryption algorithm
-   KDF information
-   scrypt parameters
-   Original filename
-   Original extension
-   Original file size
-   Random salt
-   Random AES-GCM nonce
-   Encrypted file contents

The encrypted payload is authenticated by AES-GCM.

------------------------------------------------------------------------

# 8. Security Design

The encryption workflow is:

``` text
                    PASSWORD
                       │
                       ▼
                    scrypt
                       │
                       ▼
                  256-bit key
                       │
                       ▼
Original file ──► AES-256-GCM ──► .jassvault
                       ▲
                       │
                 random nonce
                 random salt
```

During decryption:

``` text
.jassvault
    │
    ▼
Read metadata
    │
    ▼
Derive key using password + salt
    │
    ▼
AES-256-GCM authentication
    │
    ├── Failure → reject
    │
    ▼
Recover original bytes
    │
    ▼
Original image
```

A wrong password should result in authentication failure rather than
producing a plausible but corrupted image.

Likewise, modification or corruption of the authenticated encrypted
payload should cause decryption to fail.

------------------------------------------------------------------------

# 9. Why v2 Does Not Use the Original Encryption Method

The original application generated a random floating-point NumPy matrix
and divided grayscale pixel values by that matrix before writing a JPEG
file.

JASS Image Vault Pro v2 does not use that approach.

Instead, it encrypts the original file bytes with AES-256-GCM.

This has two important practical advantages:

1.  The encryption is designed around a standard authenticated
    encryption construction.
2.  The original file can be recovered without JPEG recompression.

Therefore, if an original PNG was encrypted, decrypting it can recover
the original PNG bytes rather than creating a new lossy JPEG
representation.

------------------------------------------------------------------------

# 10. Original Files Are Not Automatically Deleted

Encryption does **not** delete the source image.

For example:

``` text
Before:

Photos/
└── secret.png
```

After encryption:

``` text
Photos/
├── secret.png
└── secret.jassvault
```

The original file remains available.

If you want the original removed after verifying the encrypted vault, do
that manually and only after confirming that the vault can be
successfully decrypted.

The application itself does not perform automatic secure deletion of the
source file.

------------------------------------------------------------------------

# 11. Decryption Safety

When decrypting, choose a separate output filename or directory when
practical.

For example:

``` text
Vault/
└── secret.jassvault

Recovered/
└── secret.png
```

This makes it easier to verify the recovered file before replacing or
removing anything.

------------------------------------------------------------------------

# 12. Troubleshooting

## `ModuleNotFoundError: No module named 'PySide6'`

Install PySide6:

``` bash
python3 -m pip install PySide6
```

Windows:

``` powershell
py -m pip install PySide6
```

------------------------------------------------------------------------

## `ModuleNotFoundError: No module named 'cryptography'`

Install cryptography:

``` bash
python3 -m pip install cryptography
```

Windows:

``` powershell
py -m pip install cryptography
```

------------------------------------------------------------------------

## Application says the vault is invalid

Check that:

-   The selected file is actually a `.jassvault` file.
-   The file was created by JASS Image Vault Pro v2.
-   The file has not been truncated or otherwise damaged.

------------------------------------------------------------------------

## Decryption fails

A decryption failure can occur because:

-   The password is incorrect.
-   The encrypted file has been modified.
-   The encrypted file is incomplete or corrupted.
-   The vault format is unsupported.

Do not repeatedly overwrite the only copy of an encrypted vault while
troubleshooting.

------------------------------------------------------------------------

## Image preview does not appear

The encryption process operates on file bytes and does not require the
source image to be converted.

If an image cannot be previewed by Qt, the file may still be usable if
it is a supported image format and can be opened by another appropriate
image viewer.

------------------------------------------------------------------------

# 13. Recommended Workflow

For important images:

``` text
1. Select original image
          ↓
2. Encrypt
          ↓
3. Confirm .jassvault exists
          ↓
4. Decrypt to a separate test location
          ↓
5. Open and verify recovered image
          ↓
6. Keep a backup of the vault
```

For especially important data, maintain more than one backup of the
encrypted vault.

------------------------------------------------------------------------

# 14. Privacy

The application is designed for local processing.

The image and password are processed by the application on the local
computer. No cloud service or online API is required by the application.

Keep in mind that your operating system, backups, antivirus software,
file-indexing services, or other installed software may independently
access files on your computer.

------------------------------------------------------------------------

# 15. Project Structure

The current version is intentionally simple and can be run as a single
Python file:

``` text
JASS_Image_Vault_Pro_v2.0.py
```

A future modular structure could separate:

``` text
jass_image_vault/
├── main.py
├── crypto/
│   ├── encryption.py
│   └── format.py
├── ui/
│   ├── main_window.py
│   └── preview.py
└── utils/
    └── file_utils.py
```

------------------------------------------------------------------------

# 16. Current Limitations

This version focuses on reliable local image encryption/decryption.

It currently does not provide:

-   Batch encryption
-   Batch decryption
-   Folder encryption
-   Password recovery
-   Key-file support
-   Drag-and-drop workflows
-   Encrypted thumbnails
-   Vault browser
-   File integrity/history database
-   Secure source-file wiping
-   Multi-user key management

These can be added in later versions without changing the basic
encryption model.

------------------------------------------------------------------------

# 17. Suggested Future Features

Possible future JASS Image Vault Pro releases could include:

### v2.1

-   Drag and drop
-   Batch image encryption
-   Batch decryption
-   Recent files
-   Better preview controls
-   Dark/light themes
-   Keyboard shortcuts

### v2.2

-   Folder/batch processing
-   Encryption queue
-   Operation history
-   Verification after encryption
-   SHA-256 fingerprints
-   Detailed operation logs

### v3.0

-   Dedicated vault browser
-   Multiple files in one vault
-   Password/key-file combination
-   Vault metadata viewer
-   Backup/restore tools
-   Optional secure-delete workflow
-   Portable application packaging

------------------------------------------------------------------------

# 18. License

Add your preferred license before publishing the project publicly.

For example:

``` text
MIT License
```

if you want the project to be permissively reusable.

------------------------------------------------------------------------

# 19. Project Safety Notice

JASS Image Vault Pro is intended for legitimate personal and
professional data protection.

Always test encryption/decryption with non-critical files before using
the application for valuable data.

**Never rely on a single copy of an important encrypted file.**

------------------------------------------------------------------------

## Version History

### v2.0

-   Replaced Tkinter interface with PySide6
-   Replaced the original image transformation approach with AES-256-GCM
-   Added scrypt password-based key derivation
-   Added authenticated encryption
-   Added `.jassvault` container format
-   Added image preview
-   Added zoom controls
-   Added password-strength indicator
-   Added background worker
-   Added progress reporting
-   Added original file metadata
-   Added decrypted-image preview
-   Added cross-platform file handling
-   Preserved original file bytes during encryption/decryption

------------------------------------------------------------------------

**JASS Image Vault Pro**\
*Local • Password Protected • Authenticated • Image-focused*
