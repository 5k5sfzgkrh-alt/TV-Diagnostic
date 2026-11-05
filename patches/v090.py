from pathlib import Path
import os

src = Path(os.environ["SRC"])
gradle = Path(os.environ["GRADLE"])

g = gradle.read_text()
if 'versionName = "0.8.0"' not in g or "versionCode = 8" not in g:
    raise SystemExit("Expected v0.8.0 source")
g = g.replace("versionCode = 8", "versionCode = 9", 1)
g = g.replace('versionName = "0.8.0"', 'versionName = "0.9.0"', 1)
gradle.write_text(g)

s = src.read_text()
s = s.replace("Hi3751V553  •  0.8.0", "Hi3751V553  •  0.9.0", 1)
s = s.replace('"appVersion", "0.8.0"', '"appVersion", "0.9.0"', 1)
s = s.replace("tv-diagnostic-report-v080.json", "tv-diagnostic-report-v090.json")

call_anchor = 'j.put("extendedDiagnostics", collectExtendedDiagnostics())'
if 'j.put("rootBlockReadProbe", collectRootBlockReadProbe())' not in s:
    if call_anchor not in s:
        raise SystemExit("v0.8 extended diagnostics report anchor not found")
    s = s.replace(call_anchor, call_anchor + '\n        j.put("rootBlockReadProbe", collectRootBlockReadProbe())', 1)

methods = r"""
    // v0.9.0: bounded read-only block-device access probe.
    // Reads at most 4096 bytes from selected non-identity partitions to /dev/null.
    // Never writes to a block device and never saves partition contents.
    private fun collectRootBlockReadProbe(): JSONObject = JSONObject().apply {
        val result = JSONArray()
        val allowed = setOf("boot", "recovery", "system", "vendor", "atv", "ramdisk", "dtbo", "logo", "cache")
        val info = collectPartitionInfo()
        val entries = info.optJSONArray("byNameEntries") ?: JSONArray()

        var rootOutput = ""
        var rootExit = -1
        var rootTimedOut = false
        var rootError = ""
        try {
            val root = ProcessBuilder("su", "0", "id").redirectErrorStream(true).start()
            if (!root.waitForWithTimeout(2500)) {
                rootTimedOut = true
                root.destroyForcibly()
            } else {
                rootExit = root.exitValue()
                rootOutput = root.inputStream.bufferedReader().use { it.readText().trim().take(1200) }
            }
        } catch (e: Exception) {
            rootError = e.message ?: e.javaClass.simpleName
        }
        val rootConfirmed = rootExit == 0 && Regex("uid=0(?:\\(|\\s|$)").containsMatchIn(rootOutput)
        put("rootProbe", JSONObject().apply {
            put("command", "su 0 id")
            put("output", rootOutput)
            put("exitCode", rootExit)
            put("timedOut", rootTimedOut)
            put("error", rootError)
            put("rootConfirmed", rootConfirmed)
        })

        if (rootConfirmed) {
            val seen = mutableSetOf<String>()
            for (i in 0 until entries.length()) {
                val entry = entries.optJSONObject(i) ?: continue
                val name = entry.optString("name")
                val path = entry.optString("path")
                val target = entry.optString("target")
                if (name !in allowed || path.isBlank() || !seen.add(name)) continue

                var output = ""
                var exitCode = -1
                var timedOut = false
                var error = ""
                try {
                    val p = ProcessBuilder(
                        "su", "0", "dd",
                        "if=$path", "of=/dev/null", "bs=4096", "count=1"
                    ).redirectErrorStream(true).start()
                    if (!p.waitForWithTimeout(2200)) {
                        timedOut = true
                        p.destroyForcibly()
                    } else {
                        exitCode = p.exitValue()
                        output = p.inputStream.bufferedReader().use { it.readText().trim().take(1200) }
                    }
                } catch (e: Exception) {
                    error = e.message ?: e.javaClass.simpleName
                }
                result.put(JSONObject().apply {
                    put("name", name)
                    put("path", path)
                    put("target", target)
                    put("readOnlyProbe", true)
                    put("command", "su 0 dd if=<partition> of=/dev/null bs=4096 count=1")
                    put("exitCode", exitCode)
                    put("timedOut", timedOut)
                    put("output", output)
                    put("error", error)
                    put("readSucceeded", exitCode == 0 && !timedOut)
                    put("bytesRequested", 4096)
                })
            }
        }

        put("partitionResults", result)
        put("partitionsConsidered", JSONArray(allowed.toList().sorted()))
        put("maximumBytesPerPartition", 4096)
        put("rawPartitionContentsSaved", false)
        put("partitionWriteAttempted", false)
        put("firmwareUpdateAttempted", false)
        put("recoveryOrFastbootStarted", false)
        put("excludedSensitivePartitions", JSONArray(listOf(
            "fastboot", "bootargs", "bootargsbak", "slaveboot", "deviceinfo",
            "atf", "trustedcore", "securestore", "panelparam", "tconparam",
            "demura", "versioninfo", "misc", "bootmusic", "bootmusicsec", "userdata"
        )))
        put("safetyNote",
            "Проба ограничена чтением до 4096 байт из выбранных разделов в /dev/null. Файлы дампа не создаются. Разделы с идентификаторами, ключами, калибровками и пользовательскими данными исключены. Никакая запись в блочные устройства не выполняется.")
    }

"""
method_anchor = "    private fun collectMediaCodecs(): JSONArray {"
if "private fun collectRootBlockReadProbe()" not in s:
    if method_anchor not in s:
        raise SystemExit("v0.8 method insertion anchor missing")
    s = s.replace(method_anchor, methods + method_anchor, 1)

required = [
    'versionName = "0.9.0"', '"appVersion", "0.9.0"',
    'j.put("rootBlockReadProbe", collectRootBlockReadProbe())',
    'private fun collectRootBlockReadProbe()', 'rawPartitionContentsSaved',
    'partitionWriteAttempted', 'tv-diagnostic-report-v090.json'
]
missing = [x for x in required if x not in g + s]
if missing:
    raise SystemExit("v0.9.0 verification failed: " + ", ".join(missing))
src.write_text(s)
print("v0.9.0 bounded read-only root block probe patch applied and verified")
