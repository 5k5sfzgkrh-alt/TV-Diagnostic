from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path("project")
SRC = ROOT / "app/src/main/java/com/tvdiagnostic/hi3751/MainActivity.kt"
GRADLE = ROOT / "app/build.gradle.kts"
MANIFEST = ROOT / "app/src/main/AndroidManifest.xml"
XML_DIR = ROOT / "app/src/main/res/xml"
XML_DIR.mkdir(parents=True, exist_ok=True)

s = SRC.read_text(encoding="utf-8")

# Replace the crowded main screen with the agreed three primary actions and a separate backup area.
old_ui = '''        val buttons = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val refresh = makeButton("Обновить") { refreshReport() }
        val root = makeButton("Проверить Root") { checkRoot() }
        val export = makeButton("Экспорт JSON") { exportReport() }
        val share = makeButton("Поделиться отчётом") { shareReport() }
        buttons.addView(refresh)
        buttons.addView(root)
        buttons.addView(export)
        buttons.addView(share)
        reportView = TextView(this).apply {
            textSize = 16f
            setTextColor(0xFFE8EEF2.toInt())
            setLineSpacing(5f, 1.0f)
            setPadding(0, 16, 0, 24)
            isFocusable = true
        }
        val scroll = ScrollView(this).apply { addView(reportView) }
        outer.addView(title)
        outer.addView(statusView)
        outer.addView(buttons)
        val backupButtons = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        backupButtons.addView(makeButton("Создать бэкап DTBO") { confirmDtboBackup() })
        backupButtons.addView(makeButton("Остановить Wi-Fi") { stopBackupServer() })
        backupButtons.addView(makeButton("Бэкап BOOT + RECOVERY") { confirmSystemBackup() })
        outer.addView(backupButtons)
        val systemBackupButtons = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        systemBackupButtons.addView(makeButton("Бэкап SYSTEM + VENDOR") { confirmSystemVendorBackup() })
        systemBackupButtons.addView(makeButton("Найти бэкап 1.3.0") { findLegacySystemVendorBackups() })
        outer.addView(systemBackupButtons)
        outer.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(outer)
        refresh.requestFocus()
'''
new_ui = '''        val buttons = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val root = makeButton("Проверить Root") { checkRoot() }
        val export = makeButton("Экспорт JSON") { exportReport() }
        val share = makeButton("Поделиться отчётом") { shareReport() }
        buttons.addView(root)
        buttons.addView(export)
        buttons.addView(share)
        reportView = TextView(this).apply {
            textSize = 16f
            setTextColor(0xFFE8EEF2.toInt())
            setLineSpacing(5f, 1.0f)
            setPadding(0, 16, 0, 24)
            isFocusable = true
        }
        val scroll = ScrollView(this).apply { addView(reportView) }
        outer.addView(title)
        outer.addView(statusView)
        outer.addView(buttons)
        val backupTitle = TextView(this).apply {
            text = "РЕЗЕРВНОЕ КОПИРОВАНИЕ"
            textSize = 14f
            setTextColor(0xFF80CBC4.toInt())
            setPadding(0, 14, 0, 6)
        }
        outer.addView(backupTitle)
        val backupButtons = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        backupButtons.addView(makeButton("Бэкап DTBO") { confirmDtboBackup() })
        backupButtons.addView(makeButton("BOOT + RECOVERY") { confirmSystemBackup() })
        outer.addView(backupButtons)
        val systemBackupButtons = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        systemBackupButtons.addView(makeButton("SYSTEM + VENDOR") { confirmSystemVendorBackup() })
        outer.addView(systemBackupButtons)
        outer.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(outer)
        root.requestFocus()
'''
if s.count(old_ui) != 1:
    raise SystemExit(f"Main UI anchor mismatch: {s.count(old_ui)}")
s = s.replace(old_ui, new_ui, 1)

# Keep report data in the app's private Documents folder; verify it before exposing a share URI.
start = s.index("    private fun exportReport() {")
end = s.index("    // First backup milestone: DTBO only.", start)
new_report_methods = r'''
    private fun reportJsonText(): String {
        if (lastReport.length() == 0) {
            throw IllegalStateException("Отчёт ещё не собран. Подожди завершения диагностики и повтори попытку.")
        }
        return lastReport.toString(2)
    }

    private fun writeVerifiedReportFile(): File {
        val dir = getExternalFilesDir(Environment.DIRECTORY_DOCUMENTS) ?: File(filesDir, "Documents")
        if (!dir.exists() && !dir.mkdirs()) {
            throw IllegalStateException("Не удалось создать каталог отчёта: " + dir.absolutePath)
        }
        val target = File(dir, "tv-diagnostic-report-v150.json")
        val temp = File(dir, target.name + ".tmp")
        val json = reportJsonText()
        temp.outputStream().buffered().use { stream ->
            stream.write(json.toByteArray(Charsets.UTF_8))
            stream.flush()
        }
        val check = temp.readText(Charsets.UTF_8)
        JSONObject(check)
        if (!temp.renameTo(target)) {
            temp.copyTo(target, overwrite = true)
            if (!temp.delete()) temp.deleteOnExit()
        }
        val verified = target.readText(Charsets.UTF_8)
        JSONObject(verified)
        if (verified.toByteArray(Charsets.UTF_8).contentEquals(json.toByteArray(Charsets.UTF_8)).not()) {
            throw IllegalStateException("Контрольное чтение JSON не совпало с исходными данными")
        }
        return target
    }

    private fun exportReport() {
        try {
            val intent = android.content.Intent(android.content.Intent.ACTION_CREATE_DOCUMENT).apply {
                addCategory(android.content.Intent.CATEGORY_OPENABLE)
                type = "application/json"
                putExtra(android.content.Intent.EXTRA_TITLE, "tv-diagnostic-report-v150.json")
            }
            startActivityForResult(intent, 4102)
        } catch (e: Exception) {
            try {
                val file = writeVerifiedReportFile()
                statusView.text = "Отчёт сохранён и проверен: " + file.absolutePath
            } catch (saveError: Exception) {
                statusView.text = "Экспорт не выполнен. " + (saveError.message ?: saveError.javaClass.simpleName)
            }
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: android.content.Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != 4102 || resultCode != RESULT_OK) return
        val uri = data?.data
        if (uri == null) {
            statusView.text = "Экспорт отменён: файловый провайдер не вернул URI"
            return
        }
        try {
            val json = reportJsonText()
            contentResolver.openOutputStream(uri, "wt")?.use { output ->
                output.write(json.toByteArray(Charsets.UTF_8))
                output.flush()
            } ?: throw IllegalStateException("Провайдер не открыл поток записи")
            val verified = contentResolver.openInputStream(uri)?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }
                ?: throw IllegalStateException("Не удалось перечитать сохранённый файл")
            JSONObject(verified)
            if (verified != json) throw IllegalStateException("Проверка сохранённого JSON не пройдена")
            statusView.text = "JSON сохранён и проверен: " + uri.toString()
        } catch (e: Exception) {
            statusView.text = "Не удалось завершить экспорт: " + (e.message ?: e.javaClass.simpleName)
        }
    }

    private fun shareReport() {
        try {
            val file = writeVerifiedReportFile()
            val uri = androidx.core.content.FileProvider.getUriForFile(
                this, packageName + ".fileprovider", file
            )
            val intent = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                type = "application/json"
                putExtra(android.content.Intent.EXTRA_SUBJECT, "Отчёт TV Diagnostic 1.5.0")
                putExtra(android.content.Intent.EXTRA_STREAM, uri)
                clipData = android.content.ClipData.newUri(contentResolver, "TV Diagnostic JSON", uri)
                addFlags(android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }
            startActivity(android.content.Intent.createChooser(intent, "Отправить JSON-отчёт"))
            statusView.text = "JSON создан, проверен и передан в системное меню отправки: " + file.absolutePath
        } catch (e: Exception) {
            statusView.text = "Отчёт не потерян. Ошибка отправки: " +
                (e.message ?: e.javaClass.simpleName) +
                ". Используй «Экспорт JSON» для выбора места сохранения."
        }
    }

'''
s = s[:start] + new_report_methods + s[end:]

# Extend report with the exact property namespaces and hardware evidence probes relevant to this TV.
anchor = '        j.put("driverInfo", collectDriverInfo())'
if s.count(anchor) != 1:
    raise SystemExit("Basic report insertion point missing or ambiguous")
s = s.replace(anchor, anchor + '''
        j.put("propertyInventory", collectProperties(listOf(
            "ro.product.manufacturer", "ro.product.brand", "ro.product.model", "ro.product.device",
            "ro.product.name", "ro.product.board", "ro.product.vendor.manufacturer",
            "ro.product.vendor.brand", "ro.product.vendor.model", "ro.product.vendor.device",
            "ro.product.vendor.name", "ro.product.vendor.board",
            "ro.build.version.release", "ro.build.version.sdk", "ro.build.id",
            "ro.build.display.id", "ro.build.version.incremental", "ro.build.type",
            "ro.build.tags", "ro.build.fingerprint", "ro.build.version.security_patch",
            "ro.boot.hardware", "ro.boot.bootloader", "ro.boot.slot_suffix", "ro.boot.verifiedbootstate",
            "ro.boot.flash.locked", "ro.boot.avb_version", "ro.hardware", "ro.hardware.chipname",
            "ro.board.platform", "ro.soc.manufacturer", "ro.soc.model",
            "ro.vendor.build.fingerprint", "ro.vendor.build.id", "ro.vendor.build.version",
            "ro.vendor.product.board", "ro.vendor.product.device"
        )))
        j.put("hardwareInventoryV150", collectHardwareInventoryV150())
''', 1)

# Insert read-only hardware probes before the report formatter.
marker = '    private fun formatReport(j: JSONObject): String {'
if s.count(marker) != 1:
    raise SystemExit("Report formatter marker missing or ambiguous")
hardware_method = r'''
    // Read-only hardware inventory. Missing sysfs/device-tree nodes are reported, never guessed.
    private fun probePathV150(path: String, limit: Int = 4096): JSONObject {
        val file = File(path)
        if (!file.exists()) return JSONObject().put("status", "not_found").put("path", path)
        return try {
            val value = file.readBytes().take(limit).toByteArray().toString(Charsets.UTF_8)
            JSONObject().put("status", "confirmed").put("path", path).put("value", value.trim())
        } catch (e: SecurityException) {
            JSONObject().put("status", "permission_denied").put("path", path)
                .put("error", e.message ?: "SecurityException")
        } catch (e: Exception) {
            JSONObject().put("status", "read_error").put("path", path)
                .put("error", e.message ?: e.javaClass.simpleName)
        }
    }

    private fun collectHardwareInventoryV150(): JSONObject = JSONObject().apply {
        put("deviceTree", JSONArray().apply {
            listOf(
                "/proc/device-tree/model",
                "/proc/device-tree/compatible",
                "/sys/firmware/devicetree/base/model",
                "/sys/firmware/devicetree/base/compatible",
                "/sys/firmware/devicetree/base/chosen/bootargs"
            ).forEach { put(probePathV150(it, 8192)) }
        })
        put("soc", JSONArray().apply {
            listOf(
                "/sys/devices/soc0/soc_id", "/sys/devices/soc0/machine",
                "/sys/devices/soc0/family", "/sys/devices/soc0/revision",
                "/sys/devices/system/cpu/present", "/sys/devices/system/cpu/online",
                "/proc/cpuinfo"
            ).forEach { put(probePathV150(it, 12000)) }
        })
        put("emmc", JSONArray().apply {
            listOf(
                "/sys/block/mmcblk0/device/name", "/sys/block/mmcblk0/device/cid",
                "/sys/block/mmcblk0/device/csd", "/sys/block/mmcblk0/device/manfid",
                "/sys/block/mmcblk0/device/oemid", "/sys/block/mmcblk0/device/type",
                "/sys/block/mmcblk0/size", "/sys/block/mmcblk0/queue/logical_block_size",
                "/sys/block/mmcblk0boot0/size", "/sys/block/mmcblk0boot1/size"
            ).forEach { put(probePathV150(it, 4096)) }
        })
        put("displayPanel", JSONArray().apply {
            listOf(
                "/sys/class/graphics/fb0/name", "/sys/class/graphics/fb0/virtual_size",
                "/sys/class/drm/card0-DSI-1/status", "/sys/class/drm/card0-HDMI-A-1/status",
                "/proc/device-tree/display", "/proc/device-tree/panel"
            ).forEach { put(probePathV150(it, 4096)) }
        })
        put("wireless", JSONArray().apply {
            listOf(
                "/proc/modules", "/sys/class/net/wlan0/device/uevent",
                "/sys/class/net/wlan0/uevent", "/sys/class/bluetooth/hci0/uevent",
                "/sys/class/bluetooth/hci0/address"
            ).forEach { put(probePathV150(it, 12000)) }
        })
        put("evidencePolicy", JSONObject()
            .put("missingNodeStatus", "not_found")
            .put("noChipGuessing", true)
            .put("partitionWritesAttempted", false))
    }

'''
s = s.replace(marker, hardware_method + marker, 1)
SRC.write_text(s, encoding="utf-8")

# AndroidX FileProvider is used only for a read-only share URI to the verified app-private report.
g = GRADLE.read_text(encoding="utf-8")
if "androidx.core:core" not in g:
    m = re.search(r"dependencies\s*\{", g)
    if m:
        pos = m.end()
        g = g[:pos] + '\n    implementation("androidx.core:core:1.15.0")' + g[pos:]
    else:
        g = g.rstrip() + '\n\ndependencies {\n    implementation("androidx.core:core:1.15.0")\n}\n'
    GRADLE.write_text(g, encoding="utf-8")

ET.register_namespace("android", "http://schemas.android.com/apk/res/android")
tree = ET.parse(MANIFEST)
root = tree.getroot()
app = root.find("application")
if app is None:
    raise SystemExit("Manifest application element missing")
ns = "{http://schemas.android.com/apk/res/android}"
provider_name = "androidx.core.content.FileProvider"
for provider in list(app.findall("provider")):
    if provider.get(ns + "name") == provider_name:
        app.remove(provider)
provider = ET.SubElement(app, "provider")
provider.set(ns + "name", provider_name)
provider.set(ns + "authorities", "${applicationId}.fileprovider")
provider.set(ns + "exported", "false")
provider.set(ns + "grantUriPermissions", "true")
meta = ET.SubElement(provider, "meta-data")
meta.set(ns + "name", "android.support.FILE_PROVIDER_PATHS")
meta.set(ns + "resource", "@xml/file_paths")
tree.write(MANIFEST, encoding="utf-8", xml_declaration=True)

(XML_DIR / "file_paths.xml").write_text('''<?xml version="1.0" encoding="utf-8"?>
<paths xmlns:android="http://schemas.android.com/apk/res/android">
    <external-files-path name="external_documents" path="Documents/" />
    <files-path name="internal_documents" path="Documents/" />
</paths>
''', encoding="utf-8")

# Guard against accidental mutation-oriented commands in the new diagnostics.
for forbidden in ("dd if=", "dd of=", "flash_image", "fastboot flash", "erase ", "mkfs."):
    if forbidden in hardware_method.lower():
        raise SystemExit("Unexpected write-capable command in hardware collector: " + forbidden)

print("v1.5.0 patch applied: verified JSON persistence/share, SAF export callback, FileProvider, simplified UI, read-only hardware inventory.")
