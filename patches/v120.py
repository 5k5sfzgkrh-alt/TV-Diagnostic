from pathlib import Path
import os

src = Path(os.environ["SRC"])
gradle = Path(os.environ["GRADLE"])
g = gradle.read_text()
if 'versionName = "1.1.0"' not in g or "versionCode = 110" not in g:
    raise SystemExit("Expected v1.1.0 Gradle config")
g = g.replace("versionCode = 110", "versionCode = 120", 1)
g = g.replace('versionName = "1.1.0"', 'versionName = "1.2.0"', 1)
gradle.write_text(g)

s = src.read_text()
if "Hi3751V553  •  1.1.0" not in s:
    raise SystemExit("Expected v1.1.0 UI version")
s = s.replace("Hi3751V553  •  1.1.0", "Hi3751V553  •  1.2.0", 1)
s = s.replace('"appVersion", "1.1.0"', '"appVersion", "1.2.0"', 1)
s = s.replace("tv-diagnostic-report-v110.json", "tv-diagnostic-report-v120.json")

# Add a read-only hardware/Device Tree inventory to the JSON report.
anchor = 'j.put("appVersion", "1.2.0")'
insert = anchor + '''
        j.put("deviceTreeInfo", collectDeviceTreeInfo())
        j.put("kernelInfo", collectKernelInfo())
        j.put("driverInfo", collectDriverInfo())'''
if 'j.put("deviceTreeInfo", collectDeviceTreeInfo())' not in s:
    if anchor not in s:
        raise SystemExit("JSON appVersion anchor not found")
    s = s.replace(anchor, insert, 1)

methods = r"""
    // v1.2.0: read-only inspection of the running kernel and live Device Tree.
    // No block-device contents are accessed; no files or partitions are modified.
    private fun collectDeviceTreeInfo(): JSONObject = JSONObject().apply {
        val base = File("/sys/firmware/devicetree/base")
        put("available", base.isDirectory)
        put("model", readText("/sys/firmware/devicetree/base/model", 2048).trim())
        put("compatibleRaw", readBinaryAsEscapedText("/sys/firmware/devicetree/base/compatible", 4096))
        put("procModel", readText("/proc/device-tree/model", 2048).trim())
        put("procCompatibleRaw", readBinaryAsEscapedText("/proc/device-tree/compatible", 4096))
        val paths = JSONArray()
        if (base.isDirectory) {
            val queue = java.util.ArrayDeque<Pair<File, Int>>()
            queue.add(Pair(base, 0))
            var visited = 0
            while (queue.isNotEmpty() && visited < 1500) {
                val (dir, depth) = queue.removeFirst()
                val children = try { dir.listFiles()?.sortedBy { it.name } ?: emptyList() }
                    catch (_: Exception) { emptyList() }
                for (child in children) {
                    if (visited >= 1500) break
                    visited++
                    val relative = child.absolutePath.removePrefix(base.absolutePath).trimStart('/')
                    if (child.isDirectory) {
                        paths.put(JSONObject().put("path", relative).put("type", "node"))
                        if (depth < 5) queue.add(Pair(child, depth + 1))
                    } else {
                        val size = try { child.length() } catch (_: Exception) { -1L }
                        val entry = JSONObject().put("path", relative).put("type", "property").put("size", size)
                        if (size in 1..512) {
                            entry.put("value", readBinaryAsEscapedText(child.absolutePath, 512))
                        } else if (size == 0L) {
                            entry.put("value", "")
                        }
                        paths.put(entry)
                    }
                }
            }
            put("truncated", queue.isNotEmpty() || visited >= 1500)
        } else {
            put("truncated", false)
        }
        put("entries", paths)
        put("entryCount", paths.length())
        put("note", "Только публичные узлы live Device Tree; бинарные свойства больше 512 байт не экспортируются.")
    }

    private fun readBinaryAsEscapedText(path: String, limit: Int): String = try {
        val bytes = File(path).inputStream().use { it.readNBytes(limit) }
        bytes.joinToString(" ") { b ->
            val v = b.toInt() and 0xff
            if (v in 32..126) v.toChar().toString() else String.format("\\x%02x", v)
        }
    } catch (_: Exception) { "" }

    private fun collectKernelInfo(): JSONObject = JSONObject().apply {
        put("version", readText("/proc/version", 4096).trim())
        put("cmdline", readText("/proc/cmdline", 12000).trim())
        put("bootconfig", readText("/proc/bootconfig", 12000).trim())
        put("modules", readText("/proc/modules", 24000))
        put("configGzAvailable", File("/proc/config.gz").canRead())
        put("configGzNote", "Конфигурация ядра не копируется автоматически; указывается только доступность.")
        put("kernelRelease", readText("/proc/sys/kernel/osrelease", 512).trim())
        put("kernelTaіnt", readText("/proc/sys/kernel/tainted", 128).trim())
    }

    private fun collectDriverInfo(): JSONObject = JSONObject().apply {
        val drivers = JSONArray()
        val roots = listOf("/sys/bus/platform/drivers", "/sys/bus/usb/drivers",
            "/sys/bus/mmc/drivers", "/sys/bus/i2c/drivers", "/sys/class")
        roots.forEach { root ->
            val dir = File(root)
            val children = try { dir.listFiles()?.sortedBy { it.name } ?: emptyList() }
                catch (_: Exception) { emptyList() }
            children.take(500).forEach { child ->
                drivers.put(JSONObject().put("root", root).put("name", child.name)
                    .put("directory", child.isDirectory))
            }
        }
        put("entries", drivers)
        put("count", drivers.length())
        put("note", "Инвентаризация имён sysfs; модули и драйверы не загружаются и не изменяются.")
    }

"""
anchor_method = "    private fun formatReport(j: JSONObject): String {"
if "private fun collectDeviceTreeInfo()" not in s:
    if anchor_method not in s:
        raise SystemExit("Method insertion anchor not found")
    s = s.replace(anchor_method, methods + anchor_method, 1)

required = [
    'versionName = "1.2.0"', "versionCode = 120",
    '"appVersion", "1.2.0"', "collectDeviceTreeInfo()",
    "collectKernelInfo()", "collectDriverInfo()",
    'tv-diagnostic-report-v120.json'
]
missing = [x for x in required if x not in g + s]
if missing:
    raise SystemExit("v1.2.0 source verification failed: " + ", ".join(missing))
src.write_text(s)
print("v1.2.0 read-only Device Tree/kernel/driver inventory applied and verified")
