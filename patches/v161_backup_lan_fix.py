from pathlib import Path
import re
import xml.etree.ElementTree as ET

src = Path("project/app/src/main/java/com/tvdiagnostic/hi3751/MainActivity.kt")
gradle = Path("project/app/build.gradle.kts")
manifest = Path("project/app/src/main/AndroidManifest.xml")

s = src.read_text(encoding="utf-8")

# v1.6.0's LAN index exposed Documents/, while all verified partition
# backups are written to app-private filesDir/backups. Add that exact
# app-private directory to the read-only allowlist.
old = 'val dirs=listOf(root,File(root,"Backup")).filter { it.isDirectory }'
new = 'val dirs=listOf(root,File(root,"Backup"),File(filesDir,"backups")).filter { it.isDirectory }'
if s.count(old) != 1:
    raise SystemExit(f"LAN backup-directory anchor mismatch: {s.count(old)}")
s = s.replace(old, new, 1)

# Update user-facing/report version without changing applicationId,
# so this remains an in-place update of the installed TV Diagnostic app.
n1 = s.count("1.6.0")\ns = s.replace("1.6.0", "1.6.1")
s = s.replace("tv-diagnostic-report-v160.json", "tv-diagnostic-report-v161.json")
if n1 < 1:
    raise SystemExit("No v1.6.0 UI/report version strings found")

g = gradle.read_text(encoding="utf-8")
if g.count("versionCode = 160") != 1 or g.count('versionName = "1.6.0"') != 1:
    raise SystemExit("Unexpected Gradle version metadata")
g = g.replace("versionCode = 160", "versionCode = 161", 1)
g = g.replace('versionName = "1.6.0"', 'versionName = "1.6.1"', 1)
gradle.write_text(g, encoding="utf-8")

ET.register_namespace("android", "http://schemas.android.com/apk/res/android")
tree = ET.parse(manifest)
app = tree.getroot().find("application")
if app is None:
    raise SystemExit("Manifest application element missing")
app.set("{http://schemas.android.com/apk/res/android}label", "TV Diagnostic 1.6.1")
tree.write(manifest, encoding="utf-8", xml_declaration=True)

if 'File(filesDir,"backups")' not in s:
    raise SystemExit("Private backups folder not included in LAN allowlist")
if "private fun lanFiles()" not in s or "MessageDigest.isEqual" not in s:
    raise SystemExit("LAN server security anchors missing")
for forbidden in ("dd of=", "fastboot flash", "flash_image", "erase_partition", "blockdev --setrw"):
    if forbidden in s:
        raise SystemExit("Write-capable operation found: " + forbidden)

src.write_text(s, encoding="utf-8")
print("v1.6.1 fix applied: authenticated read-only LAN transfer now exposes verified filesDir/backups images and archives.")
