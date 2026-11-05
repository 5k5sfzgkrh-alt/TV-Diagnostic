from pathlib import Path
import os

src = Path(os.environ["SRC"])
gradle = Path(os.environ["GRADLE"])

g = gradle.read_text()
if 'versionName = "0.7.0"' not in g or "versionCode = 7" not in g:
    raise SystemExit("Expected v0.7.0 source")
g = g.replace("versionCode = 7", "versionCode = 8", 1)
g = g.replace('versionName = "0.7.0"', 'versionName = "0.8.0"', 1)
gradle.write_text(g)

s = src.read_text()
s = s.replace("Hi3751V553  •  0.7.0", "Hi3751V553  •  0.8.0", 1)
s = s.replace('"appVersion", "0.7.0"', '"appVersion", "0.8.0"', 1)
s = s.replace("tv-diagnostic-report-v070.json", "tv-diagnostic-report-v080.json")
anchor = 'j.put("backupInstallAssessment", collectBackupInstallAssessment())'
if anchor not in s:
    raise SystemExit("v0.7 backup assessment anchor not found")
if 'j.put("extendedDiagnostics", collectExtendedDiagnostics())' not in s:
    s = s.replace(anchor, anchor + '\n        j.put("extendedDiagnostics", collectExtendedDiagnostics())', 1)

methods = r"""
    // v0.8.0: expanded read-only diagnostics for panel, ADB/USB, storage and recovery planning.
    // This method deliberately does not read raw block contents or write to flash.
    private fun collectExtendedDiagnostics(): JSONObject = JSONObject().apply {
        put("deviceIdentity", JSONObject().apply {
            put("manufacturer", Build.MANUFACTURER)
            put("brand", Build.BRAND)
            put("model", Build.MODEL)
            put("device", Build.DEVICE)
            put("product", Build.PRODUCT)
            put("board", Build.BOARD)
            put("hardware", Build.HARDWARE)
            put("fingerprint", Build.FINGERPRINT)
            put("display", Build.DISPLAY)
            put("bootloader", Build.BOOTLOADER)
            put("androidRelease", Build.VERSION.RELEASE)
            put("sdk", Build.VERSION.SDK_INT)
            put("supportedAbis", JSONArray(Build.SUPPORTED_ABIS.toList()))
        })

        val propCommands = JSONArray()
        listOf(
            listOf("getprop", "ro.product.manufacturer"),
            listOf("getprop", "ro.product.brand"),
            listOf("getprop", "ro.product.model"),
            listOf("getprop", "ro.product.device"),
            listOf("getprop", "ro.product.name"),
            listOf("getprop", "ro.product.board"),
            listOf("getprop", "ro.hardware"),
            listOf("getprop", "ro.build.fingerprint"),
            listOf("getprop", "ro.build.description"),
            listOf("getprop", "ro.build.version.incremental"),
            listOf("getprop", "ro.build.version.security_patch"),
            listOf("getprop", "ro.bootloader"),
            listOf("getprop", "ro.boot.verifiedbootstate"),
            listOf("getprop", "ro.boot.flash.locked"),
            listOf("getprop", "ro.boot.vbmeta.device_state")
        ).forEach { command ->
            val result = runReadOnlyCommand(command, 2000)
            propCommands.put(JSONObject().apply {
                put("property", command.last())
                put("value", result.optString("output").trim())
                put("exitCode", result.optInt("exitCode", -1))
                put("error", result.optString("error"))
            })
        }
        put("buildProperties", propCommands)

        val panelCandidates = listOf(
            "/sys/class/graphics/fb0/name",
            "/sys/class/graphics/fb0/modes",
            "/sys/class/graphics/fb0/virtual_size",
            "/sys/class/graphics/fb0/bits_per_pixel",
            "/sys/class/display/HDMI/name",
            "/sys/class/display/HDMI/mode",
            "/sys/class/drm/card0-eDP-1/status",
            "/sys/class/drm/card0-HDMI-A-1/status",
            "/proc/device-tree/model",
            "/proc/device-tree/compatible",
            "/sys/firmware/devicetree/base/model",
            "/sys/firmware/devicetree/base/compatible",
            "/sys/class/graphics/fb0/device/modalias",
            "/sys/class/graphics/fb0/device/uevent"
        )
        val panel = JSONArray()
        panelCandidates.forEach { path ->
            val file = File(path)
            if (file.exists()) {
                val value = try {
                    file.readBytes().take(2048).toByteArray().toString(Charsets.UTF_8)
                        .replace("\u0000", " ").trim()
                } catch (e: Exception) { "" }
                panel.put(JSONObject().apply {
                    put("path", path)
                    put("readable", file.canRead())
                    put("value", value)
                    put("error", if (value.isEmpty() && file.canRead()) "empty_or_binary" else "")
                })
            }
        }
        put("panelAndDisplayCandidates", panel)
        put("panelIdentification",
            if (panel.length() == 0) "not_exposed_by_known_sysfs_paths"
            else "candidate_metadata_only_panel_model_not_confirmed")

        val adb = JSONObject()
        try {
            adb.put("settingsGlobalAdbEnabled",
                android.provider.Settings.Global.getInt(contentResolver, "adb_enabled", -1))
        } catch (e: Exception) {
            adb.put("settingsGlobalAdbEnabled", -1)
            adb.put("settingsReadError", e.message ?: e.javaClass.simpleName)
        }
        val usbProps = JSONArray()
        listOf(
            "sys.usb.config", "persist.sys.usb.config", "sys.usb.state",
            "service.adb.tcp.port", "persist.adb.tcp.port",
            "persist.service.adb.enable", "ro.adb.secure", "ro.debuggable"
        ).forEach { key ->
            val result = runReadOnlyCommand(listOf("getprop", key), 2000)
            usbProps.put(JSONObject().apply {
                put("name", key); put("value", result.optString("output").trim())
            })
        }
        adb.put("properties", usbProps)
        val usbPaths = listOf(
            "/sys/class/android_usb/android0/state",
            "/sys/class/android_usb/android0/functions",
            "/sys/class/android_usb/android0/enable",
            "/config/usb_gadget/g1/UDC",
            "/dev/usb-ffs/adb",
            "/dev/bus/usb"
        )
        val usbNodes = JSONArray()
        usbPaths.forEach { path ->
            val f = File(path)
            usbNodes.put(JSONObject().apply {
                put("path", path); put("exists", f.exists())
                put("directory", f.isDirectory); put("readable", f.canRead())
            })
        }
        adb.put("usbNodes", usbNodes)
        put("adbUsb", adb)

        val storage = JSONArray()
        val storagePaths = linkedSetOf<String>()
        storagePaths.add(Environment.getExternalStorageDirectory().absolutePath)
        getExternalFilesDir(null)?.let { storagePaths.add(it.absolutePath) }
        getExternalFilesDirs(null).filterNotNull().forEach { storagePaths.add(it.absolutePath) }
        storagePaths.forEach { path ->
            val f = File(path)
            val item = JSONObject().apply {
                put("path", path)
                put("exists", f.exists())
                put("directory", f.isDirectory)
                put("readable", f.canRead())
                put("writable", f.canWrite())
            }
            if (f.exists()) {
                try {
                    val stat = android.os.StatFs(path)
                    item.put("availableBytes", stat.availableBytes)
                    item.put("totalBytes", stat.totalBytes)
                } catch (e: Exception) {
                    item.put("statError", e.message ?: e.javaClass.simpleName)
                }
            }
            storage.put(item)
        }
        put("backupStorageCandidates", storage)
        put("backupStorageNote",
            "Оценены только доступность каталогов и свободное место. Тестовая запись не выполнялась; доступ к каталогу не гарантирует возможность сохранить полный дамп.")

        val zramPaths = listOf(
            "/sys/block/zram0/disksize",
            "/sys/block/zram0/mm_stat",
            "/sys/block/zram0/comp_algorithm",
            "/sys/block/zram0/backing_dev",
            "/sys/block/zram0/max_comp_streams",
            "/proc/meminfo",
            "/proc/swaps",
            "/proc/pressure/memory"
        )
        val memory = JSONArray()
        zramPaths.forEach { path ->
            val f = File(path)
            if (f.exists()) {
                val value = try { f.readText().take(6000).trim() }
                    catch (e: Exception) { "READ_ERROR: " + (e.message ?: e.javaClass.simpleName) }
                memory.put(JSONObject().apply { put("path", path); put("value", value) })
            }
        }
        put("memoryAndZram", memory)

        val thermal = JSONArray()
        for (i in 0..15) {
            val base = File("/sys/class/thermal/thermal_zone$i")
            if (!base.exists()) continue
            val type = try { File(base, "type").readText().trim() } catch (_: Exception) { "" }
            val temp = try { File(base, "temp").readText().trim() } catch (_: Exception) { "" }
            thermal.put(JSONObject().apply {
                put("zone", i); put("type", type); put("rawTemperature", temp)
            })
        }
        put("thermalZones", thermal)
        put("thermalNote",
            "Значения приведены в исходном виде из sysfs; единицы и масштаб зависят от драйвера и требуют проверки.")

        val blockLinks = JSONArray()
        listOf(
            "/dev/block/by-name",
            "/dev/block/platform/soc/f9830000.emmc/by-name",
            "/dev/block/platform/soc/fe340000.emmc/by-name"
        ).forEach { dir ->
            File(dir).listFiles()?.sortedBy { it.name }?.forEach { node ->
                blockLinks.put(JSONObject().apply {
                    put("name", node.name)
                    put("path", node.absolutePath)
                    put("target", try { node.canonicalPath } catch (_: Exception) { "" })
                    put("exists", node.exists())
                    put("readable", node.canRead())
                    put("writable", node.canWrite())
                    put("directory", node.isDirectory)
                })
            }
        }
        put("blockDeviceLinks", blockLinks)
        put("rawPartitionContentsRead", false)
        put("partitionWriteAttempted", false)
        put("firmwareUpdateAttempted", false)
        put("recoveryOrFastbootStarted", false)
    }

"""
anchor_method = "    private fun collectMediaCodecs(): JSONArray {"
if "private fun collectExtendedDiagnostics()" not in s:
    if anchor_method not in s:
        raise SystemExit("v0.7 method insertion anchor missing")
    s = s.replace(anchor_method, methods + anchor_method, 1)

required = [
    'versionName = "0.8.0"', '"appVersion", "0.8.0"',
    'j.put("extendedDiagnostics", collectExtendedDiagnostics())',
    'private fun collectExtendedDiagnostics()', 'panelAndDisplayCandidates',
    'adbUsb', 'backupStorageCandidates', 'memoryAndZram',
    'tv-diagnostic-report-v080.json'
]
missing = [x for x in required if x not in g + s]
if missing:
    raise SystemExit("v0.8.0 verification failed: " + ", ".join(missing))
src.write_text(s)
print("v0.8.0 extended read-only diagnostics patch applied and verified")
