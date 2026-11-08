from pathlib import Path
import re
import xml.etree.ElementTree as ET

src = Path("project/app/src/main/java/com/tvdiagnostic/hi3751/MainActivity.kt")
gradle = Path("project/app/build.gradle.kts")
manifest = Path("project/app/src/main/AndroidManifest.xml")
s = src.read_text(encoding="utf-8")
g = gradle.read_text(encoding="utf-8")

# v1.6.2: consistent visible version strings.
if "versionCode = 161" not in g or 'versionName = "1.6.1"' not in g:
    raise SystemExit("Expected v1.6.1 Gradle metadata")
g = g.replace("versionCode = 161", "versionCode = 162", 1)
g = g.replace('versionName = "1.6.1"', 'versionName = "1.6.2"', 1)
if "com.google.zxing:core" not in g:
    if g.count("dependencies {") != 1:
        raise SystemExit("Gradle dependencies block anchor mismatch")
    g = g.replace("dependencies {", 'dependencies {\n    implementation("com.google.zxing:core:3.5.3")', 1)

# The LAN index header is also visible on the phone; keep its version aligned.
s = s.replace("TV Diagnostic 1.6.1", "TV Diagnostic 1.6.2")
s = s.replace("1.6.1", "1.6.2")
s = s.replace("tv-diagnostic-report-v161.json", "tv-diagnostic-report-v162.json")

# Locate the LAN server's URL/status UI and append a QR view immediately after it.
start = s.find('statusView.text="Локальный сервер запущен.')
if start < 0:
    raise SystemExit("LAN server status UI anchor not found")
end_marker = 'Останови его после скачивания."'
end = s.find(end_marker, start)
if end < 0:
    raise SystemExit("LAN server status text end anchor not found")
end += len(end_marker)
qr_ui = '''
                val transferUrl = "http://" + lanIp() + ":" + ss.localPort + "/?token=" + token
                try {
                    val matrix = com.google.zxing.MultiFormatWriter().encode(
                        transferUrl, com.google.zxing.BarcodeFormat.QR_CODE, 420, 420
                    )
                    val bitmap = android.graphics.Bitmap.createBitmap(420, 420, android.graphics.Bitmap.Config.ARGB_8888)
                    for (y in 0 until 420) for (x in 0 until 420) {
                        bitmap.setPixel(x, y, if (matrix[x, y]) android.graphics.Color.BLACK else android.graphics.Color.WHITE)
                    }
                    val qr = android.widget.ImageView(this).apply {
                        setImageBitmap(bitmap)
                        adjustViewBounds = true
                        contentDescription = "QR-код локальной ссылки передачи файлов"
                        setPadding(12, 12, 12, 12)
                    }
                    val parent = statusView.parent as? android.view.ViewGroup
                    if (parent != null) {
                        val old = parent.findViewWithTag<android.view.View>("tv_lan_qr")
                        if (old != null) parent.removeView(old)
                        qr.tag = "tv_lan_qr"
                        val idx = parent.indexOfChild(statusView)
                        parent.addView(qr, (idx + 1).coerceAtMost(parent.childCount))
                    }
                } catch (e: Exception) {
                    statusView.append("\\nQR-код не создан: " + (e.message ?: e.javaClass.simpleName))
                }'''
s = s[:end] + qr_ui + s[end:]

# Ensure the displayed app label matches the version.
ET.register_namespace("android", "http://schemas.android.com/apk/res/android")
tree = ET.parse(manifest)
app = tree.getroot().find("application")
if app is None:
    raise SystemExit("Manifest application element missing")
app.set("{http://schemas.android.com/apk/res/android}label", "TV Diagnostic 1.6.2")
tree.write(manifest, encoding="utf-8", xml_declaration=True)

if "MultiFormatWriter" not in s or "BarcodeFormat.QR_CODE" not in s or "tv_lan_qr" not in s:
    raise SystemExit("QR generation verification failed")
if 'versionCode = 162' not in g or 'versionName = "1.6.2"' not in g:
    raise SystemExit("Version metadata verification failed")
for forbidden in ("dd of=", "fastboot flash", "flash_image", "erase_partition", "blockdev --setrw"):
    if forbidden in s:
        raise SystemExit("Write-capable operation found: " + forbidden)

src.write_text(s, encoding="utf-8")
gradle.write_text(g, encoding="utf-8")
print("v1.6.2 patch applied: corrected UI/version metadata and local tokenized QR code; read-only operations only.")
