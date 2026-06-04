## MICO360 Doc Toolkit v5.7.1

**Fix:** on tools that accept many file types (e.g. **Document → Markdown**), the
long "Supported:" list inside the drop zone could push the **Browse files / Browse
folder** buttons past the edge and clip them. The supported-formats list now sits
just **below** the drop zone, and the drop area never shrinks below its content, so
the buttons are always fully visible.

**Smaller download:** the installer is now ~14% lighter (125 MB → **108 MB**) by
dropping bundled components the app never uses (OpenCV's video codec, Qt's
software-OpenGL fallback, the AVIF image codec, and the Pythonwin/MFC runtime) —
OCR, image export and Office conversion are unaffected.

Everything else is unchanged from v5.7.0: the consolidated **PDF → …**,
**Office → PDF**, and **Document → Markdown** converters, the stable tool layout,
and the OCR text improvements.

---
*This release is also the update manifest: the tag is the version, this text is the
release notes, and the attached Setup `.exe` (+ `.sha256`) is what the app installs.*
