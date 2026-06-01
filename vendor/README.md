# Bundled engines (vendor/)

The app works without these (it falls back to a pure-Python PDF compressor and
disables Word→PDF), but for the **best results and a fully offline installer**,
drop portable copies of Ghostscript and LibreOffice here before building.

The app auto-detects binaries in this order: explicit path in Settings → a copy
here under `vendor/` → system PATH / standard install locations.

## Expected layout

```
vendor/
├── ghostscript/
│   └── bin/
│       └── gswin64c.exe        (+ gsdll64.dll and friends)
└── libreoffice/
    └── program/
        └── soffice.exe         (+ the rest of the LibreOffice 'program' + 'share' dirs)
```

## Ghostscript
1. Download the 64-bit Windows installer from https://ghostscript.com/releases/gsdnld.html
   (AGPL edition is fine for internal/AGPL-compatible use).
2. Install it somewhere, then copy its `bin\` and `lib\` folders into
   `vendor\ghostscript\`. At minimum `bin\gswin64c.exe` and `bin\gsdll64.dll`.

## LibreOffice
1. Download LibreOffice (or the portable build) from https://www.libreoffice.org/download
2. Copy the installed `program\` and `share\` folders into `vendor\libreoffice\`.
   Word→PDF uses `soffice.exe --headless --convert-to pdf`.

> LibreOffice is large (~350 MB). If you prefer a smaller installer, leave it out
> and require users to have LibreOffice (or set its path in Settings). The
> installer script (`build/installer.iss`) includes `vendor/` only if it exists.

## Licensing note
Ghostscript is AGPL; LibreOffice is MPL-2.0. If you redistribute them inside a
commercial product, review their license terms (a commercial Ghostscript license
is available from Artifex).
