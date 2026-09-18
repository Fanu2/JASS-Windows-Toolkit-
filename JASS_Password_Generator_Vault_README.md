# JASS Password Generator Vault v1.0

**JASS Password Generator Vault** is a local-first PySide6 application combining a cryptographically secure password generator with a locally encrypted credential vault.

It is intended for personal/offline use where you want:

- strong random passwords
- memorable offline passphrases
- encrypted credential storage
- simple account organization
- no cloud account
- no browser integration
- no telemetry

---

## Core security design

### Password generation

Passwords are generated using Python's:

```python
secrets
```

rather than a general-purpose random-number generator.

Selected character classes are guaranteed to contribute at least one character.

The final ordering is shuffled using `secrets.randbelow()`.

### Vault encryption

The vault uses:

```text
AES-256-GCM
```

with:

```text
scrypt → 256-bit key
```

A random 128-bit salt is generated for each vault save, and a fresh 96-bit AES-GCM nonce is generated for each save.

The master password is **not stored**.

---

# Features

## 🔐 Secure Password Generator

Configurable:

- Length: 4–256 characters
- Lowercase
- Uppercase
- Digits
- Symbols
- Exclude ambiguous characters
- Custom symbol set

Example ambiguous characters include visually confusing characters such as:

```text
O 0
I l 1
```

---

## 🧠 Passphrase Generator

Offline passphrase generation using a built-in word list.

Options:

- 3–12 words
- Custom separator
- Capitalize words
- Add number
- Add symbol

Example style:

```text
River-Morning-Cedar-Falcon-Garden42!
```

The built-in word list is intentionally local; no external word service is contacted.

---

# Vault

A vault entry supports:

```text
Title
Username
Password
URL
Tags
Notes
Created
Modified
Favorite
```

Passwords remain hidden by default in the entry editor.

---

## Vault operations

- Create vault
- Open vault
- Unlock vault
- Save vault
- Close vault
- Add entry
- Edit entry
- Delete entry
- Favorite entries
- Search entries
- Filter by tags
- Copy username
- Copy password
- Generate password directly into an entry

---

# Encrypted file format

The default file extension is:

```text
.jassvault
```

The outer file is JSON, but the credential database itself is encrypted.

Conceptually:

```text
JASS Vault
   │
   ├── Format
   ├── KDF parameters
   ├── Random salt
   ├── Random nonce
   └── AES-GCM ciphertext
             │
             ▼
       encrypted entries
```

The outer JSON does not contain the plaintext credentials.

---

# Master password

The master password is the key to the vault.

JASS does not store it.

Therefore:

> **If you lose the master password, JASS cannot recover the vault.**

Use a strong, unique master password.

A 12-character minimum is recommended by the application, although the user can choose whether to continue with a shorter password.

---

# Clipboard protection

When you copy a password or generated secret:

1. It is placed in the desktop clipboard.
2. JASS schedules a cleanup after approximately 30 seconds.
3. JASS only clears the clipboard if it still contains the exact secret that JASS copied.

This avoids overwriting a newer clipboard value.

Clipboard managers or other desktop applications may still retain copied secrets outside JASS's control.

---

# Dashboard

The dashboard displays:

- Vault entries
- Favorites
- Entries containing passwords
- Tagged entries
- Entries with URLs
- Vault state
- Open/closed state
- Unsaved changes

---

# Search

The vault search can inspect:

- Title
- Username
- URL
- Tags
- Notes

A separate tag filter is provided.

Passwords themselves are not included in normal search indexing.

---

# Installation on MX Linux / Debian

Install Python and PySide6:

```bash
sudo apt update
sudo apt install python3 python3-pip
```

Install the required Python packages:

```bash
python3 -m pip install PySide6 cryptography
```

Run:

```bash
python3 JASS_Password_Generator_Vault_v1.0.py
```

A virtual environment is recommended:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install PySide6 cryptography
python3 JASS_Password_Generator_Vault_v1.0.py
```

---

# First-use workflow

### 1. Create a vault

Click:

```text
New Vault
```

Choose:

```text
JASS_Vault.jassvault
```

Enter a strong master password.

### 2. Generate a password

Use the Password Generator tab.

For example:

```text
Length: 24
Lowercase: ✓
Uppercase: ✓
Digits: ✓
Symbols: ✓
Exclude ambiguous: ✓
```

Click:

```text
Generate Secure Password
```

### 3. Create an entry

Click:

```text
Create Vault Entry
```

Fill in the account information.

### 4. Save

Click:

```text
Save Vault
```

### 5. Close

When finished, close the vault.

---

# Security limitations

JASS Password Generator Vault is **not claimed to be a hardened commercial password manager**.

Important limitations include:

### Plaintext exists in memory

While the vault is unlocked, decrypted passwords must exist in application memory.

Python strings do not provide reliable guaranteed memory wiping.

### Clipboard

Copied passwords enter the desktop clipboard.

Other clipboard applications may retain them.

### Compromised computer

This application cannot protect against:

- malware
- keyloggers
- screen capture
- hostile root/admin users
- memory inspection
- compromised operating systems
- malicious desktop applications

### File permissions

JASS encrypts the vault contents, but the operating system still controls access to the vault file.

Use appropriate filesystem permissions.

---

# Backup strategy

Back up the `.jassvault` file.

Because each save produces fresh encryption parameters, keep secure backup copies.

Do not store the master password next to the vault.

A useful arrangement is:

```text
Encrypted vault
        +
Separate secure master-password backup
```

Never put both in the same unprotected folder.

---

# What JASS does NOT do

v1.0 deliberately does not provide:

- Cloud synchronization
- Browser plugins
- Browser password import
- Automatic website login
- Network access
- Password breach checking
- Online password generation
- Password recovery service
- Remote database
- Telemetry
- Analytics
- Automatic password rotation

The design stays **offline-first and simple**.

---

# Roadmap

## v1.1 — Vault Hardening

- Auto-lock timer
- Lock button
- Explicit session timeout
- Better save/backup handling
- File permission warning
- Vault integrity diagnostics
- Password confirmation on sensitive actions

## v1.2 — Organization

- Folders
- Categories
- Custom icons
- Favorite groups
- Stronger tag management
- Sort options
- Entry templates
- Duplicate username detection

## v1.3 — Generator Studio

- Diceware-style passphrases
- Pronounceable passwords
- PIN generator
- Username generator
- Wi-Fi password generator
- API-secret generator
- Batch generation
- Generation history with automatic expiration

## v1.4 — Import / Export

Carefully designed explicit workflows for:

- CSV import
- CSV export
- JSON import
- JSON export
- encrypted backup
- restore validation

Plaintext exports should require explicit confirmation.

## v1.5 — Security Audit

- Weak-password detection
- Reused-password detection
- Duplicate-password detection
- Old-password detection
- Missing-URL detection
- Missing-username detection
- Password age report

## v2.0 — Advanced Local Vault

Potential architecture:

```text
             JASS Password Generator Vault
                         │
        ┌────────────────┼────────────────┐
        │                │                │
   Generator         Vault Engine      Security
        │                │                │
  Passwords        AES-GCM + scrypt   Audit
  Passphrases      Entries            Auto-lock
  PINs             Search             Integrity
  API secrets      Tags               Backups
        │                │                │
        └────────────────┼────────────────┘
                         │
                   Local-only Vault
```

Possible future integration with:

- KeePassXC-compatible workflows
- Password-strength auditing
- secure import/export
- local backup management

Any compatibility feature should preserve the offline/local-first philosophy.

---

# Privacy model

JASS Password Generator Vault does not need an internet connection.

It does not intentionally:

- upload passwords
- contact password databases
- contact websites
- send telemetry
- use cloud AI
- create online accounts

Your vault remains a local file.

---

# Recommended security practices

1. Use a strong unique master password.
2. Do not reuse your master password elsewhere.
3. Keep the vault file on a protected filesystem.
4. Keep encrypted backups.
5. Lock the computer when unattended.
6. Avoid copying passwords unnecessarily.
7. Do not store the master password inside the vault.
8. Do not treat the vault as safe if the operating system is compromised.

---

# License

Choose the license appropriate for your JASS repository, such as MIT, before publishing.
