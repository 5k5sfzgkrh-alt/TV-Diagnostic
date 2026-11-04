from pathlib import Path
import os

src = Path(os.environ["SRC"])
gradle = Path(os.environ["GRADLE"])
g = gradle.read_text()
if 'versionName = "0.6.0"' not in g or "versionCode = 6" not in g:
    raise SystemExit("Expected v0.6.0 source")
g = g.replace("versionCode = 6", "versionCode = 7", 1)
g = g.replace('versionName = "0.6.0"', 'versionName = "0.7.0"', 1)
gradle.write_text(g)

s = src.read_text()
s = s.replace("Hi3751V553  •  0.6.0", "Hi3751V553  •  0.7.0", 1)
s = s.replace('"appVersion", "0.6.0"', '"appVersion", "0.7.0"', 1)
s = s.replace("tv-diagnostic-report-v060.json", "tv-diagnostic-report-v070.json")
s = s.replace('j.put("accessInfo", collectAccessInfo())',
              'j.put("accessInfo", collectAccessInfo())\n        j.put("backupInstallAssessment", collectBackupInstallAssessment())', 1)

start = s.index("    // v0.6.0: bounded, read-only privilege and backup-capability checks.")
end = s.index("    private fun collectMediaCodecs(): JSONArray", start)
replacement = r"""
    // v0.7.0: safe privilege-path and firmware-operation assessment.
    // No exploits, bootloader changes, raw partition reads, block writes or reboot actions.
    private fun collectAccessInfo(): JSONObject = JSONObject().apply {
        val suPaths = listOf("/system/bin/su", "/system/xbin/su", "/vendor/bin/su",
            "/vendor/xbin/su", "/sbin/su", "/debug_ramdisk/su")
        val presentSu = JSONArray()
        suPaths.forEach { path ->
            val f = File(path)
            if (f.exists()) presentSu.put(JSONObject().apply {
                put("path", path); put("readable", f.canRead()); put("executable", f.canExecute())
            })
        }
        put("suBinaries", presentSu)

        val probes = JSONArray()
        val commands = listOf(
            listOf("su", "-c", "id"),
            listOf("su", "0", "id"),
            listOf("su", "root", "id"),
            listOf("su", "-s", "/system/bin/sh", "-c", "id")
        )
        var confirmed = false
        commands.forEach { command ->
            val result = runReadOnlyCommand(command, 3000)
            val isRoot = result.optInt("exitCode", -1) == 0 &&
                Regex("uid=0(?:\\(|\\s|$)").containsMatchIn(result.optString("output"))
            if (isRoot) confirmed = true
            result.put("rootConfirmed", isRoot)
            probes.put(result)
        }
        put("rootProbes", probes)
        put("rootConfirmed", confirmed)
        put("rootStatus", if (confirmed) "root_confirmed" else "not_confirmed")

        val candidatePaths = listOf(
            "/system/bin/magisk", "/sbin/.magisk", "/data/adb/magisk",
            "/data/adb/ksu", "/data/adb/ap", "/system/bin/busybox",
            "/system/bin/toybox", "/system/bin/dd", "/system/bin/fastboot",
            "/system/bin/recovery", "/vendor/bin/update_engine",
            "/system/bin/update_engine", "/system/bin/bootctl"
        )
        val candidates = JSONArray()
        candidatePaths.forEach { path ->
            val f = File(path)
            if (f.exists()) candidates.put(JSONObject().apply {
                put("path", path); put("executable", f.canExecute()); put("directory", f.isDirectory)
            })
        }
        put("rootAndFirmwareTools", candidates)
        put("possibleRootManagers", JSONArray(listOf(
            "com.topjohnwu.magisk", "me.weishu.kernelsu", "me.bmax.apatch",
            "eu.chainfire.supersu"
        )))
        put("rootAcquisitionAssessment",
            if (confirmed) "root_access_confirmed"
            else if (presentSu.length() > 0) "su_present_but_access_not_confirmed"
            else "no_su_binary_found")
        put("rootAcquisitionNote",
            "Проверены безопасные варианты запуска su и наличие известных компонентов. Уязвимости не эксплуатировались; разблокировка загрузчика и установка Root не выполнялись.")
        put("rawPartitionReadAttempted", false)
        put("partitionWriteAttempted", false)
    }

    private fun runReadOnlyCommand(command: List<String>, timeoutMs: Long): JSONObject =
        JSONObject().apply {
            put("command", command.joinToString(" "))
            var process: java.lang.Process? = null
            try {
                val proc = ProcessBuilder(command).redirectErrorStream(true).start()
                val finished = proc.waitForWithTimeout(timeoutMs)
                if (!finished) proc.destroyForcibly()
                val output = try {
                    proc.inputStream.bufferedReader().use { it.readText().take(2000).trim() }
                } catch (_: Exception) { "" }
                put("output", output)
                put("exitCode", if (finished) proc.exitValue() else -1)
                put("timedOut", !finished)
                put("error", "")
            } catch (e: Exception) {
                put("output", "")
                put("exitCode", -1)
                put("timedOut", false)
                put("output", "")
                put("exitCode", -1)
                put("timedOut", false)
                put("error", e.message ?: e.javaClass.simpleName)
            }
        }

    private fun collectBackupInstallAssessment(): JSONObject = JSONObject().apply {
        val pInfo = collectPartitionInfo()
        val entries = pInfo.optJSONArray("byNameEntries") ?: JSONArray()
        val partitions = JSONArray()
        for (i in 0 until entries.length()) {
            val item = entries.optJSONObject(i) ?: continue
            val path = item.optString("path")
            val node = File(path)
            partitions.put(JSONObject().apply {
                put("name", item.optString("name"))
                put("path", path)
                put("exists", node.exists())
                put("readableMetadata", node.canRead())
                put("rawContentsRead", false)
            })
        }
        put("partitionCount", partitions.length())
        put("partitions", partitions)
        put("backupCreated", false)
        put("backupStatus", "not_created_root_and_storage_validation_required")
        put("backupRequirements", JSONArray(listOf(
            "Подтверждённый Root с правом чтения каждого нужного раздела",
            "Внешнее хранилище или отдельный носитель с достаточным свободным местом",
            "Проверка полного размера, контрольных сумм и читаемости каждой копии",
            "Отдельное сохранение критичных загрузочных и калибровочных разделов"
        )))
        put("firmwareInstallMechanisms", JSONArray().apply {
            listOf("/system/bin/update_engine", "/vendor/bin/update_engine",
                "/system/bin/recovery", "/sbin/recovery", "/system/bin/bootctl",
                "/system/bin/fastboot").forEach { path ->
                val f = File(path)
                put(JSONObject().apply {
                    put("path", path); put("exists", f.exists()); put("executable", f.canExecute())
                })
            }
        })
        put("installationAssessment", "not_verified")
        put("installationNote",
            "Проверено только наличие компонентов и метаданных. Recovery, fastboot и update_engine не запускались; образ прошивки не передавался и не устанавливался.")
        put("rawPartitionReadAttempted", false)
        put("partitionWriteAttempted", false)
        put("recoveryOrFastbootStarted", false)
    }

"""
s = s[:start] + replacement + s[end:]

a = s.index("    private fun runRootProbe(): Pair<String, String> {")
b = s.index("\n    private fun exportReport()", a)
new_probe = r"""    private fun runRootProbe(): Pair<String, String> {
        val commands = listOf(
            listOf("su", "-c", "id"),
            listOf("su", "0", "id"),
            listOf("su", "root", "id"),
            listOf("su", "-s", "/system/bin/sh", "-c", "id")
        )
        val details = mutableListOf<String>()
        for (command in commands) {
            val result = runReadOnlyCommand(command, 3000)
            val output = result.optString("output")
            details.add(command.joinToString(" ") + " -> " +
                output.ifBlank { result.optString("error", "нет вывода") })
            val isRoot = result.optInt("exitCode", -1) == 0 &&
                Regex("uid=0(?:\\\\(|\\\\s|$)").containsMatchIn(output)
            if (isRoot) return "root_confirmed" to details.joinToString("\n")
        }
        return "not_confirmed" to details.joinToString("\n")
    }
"""
s = s[:a] + new_probe + s[b:]

required = [
    'versionName = "0.7.0"', '"appVersion", "0.7.0"',
    'collectBackupInstallAssessment()', 'private fun runReadOnlyCommand',
    'rootProbes', 'backupCreated', 'installationAssessment',
    'tv-diagnostic-report-v070.json'
]
missing = [x for x in required if x not in s and x not in g]
if missing:
    raise SystemExit("v0.7.0 source verification failed: " + ", ".join(missing))
src.write_text(s)
print("v0.7.0 safe root/backup/install assessment patch applied")
