from pathlib import Path
import re

src = Path("project/app/src/main/java/com/tvdiagnostic/hi3751/MainActivity.kt")
s = src.read_text(encoding="utf-8")

hook = '        put("eMMCLayout", collectEmmcLayout())'
marker = '    private fun collectBootInfo(): JSONObject = JSONObject().apply {'
if s.count(hook) != 1:
    raise SystemExit(f"Expected one v1.3.5 eMMC report hook, got {s.count(hook)}")
if s.count(marker) != 1:
    raise SystemExit(f"Expected one collectBootInfo marker, got {s.count(marker)}")
if "private fun collectPerformanceDiagnostics()" in s:
    raise SystemExit("Performance collector already exists; refusing duplicate patch")

method = r"""
    // v1.4.0: read-only performance snapshot for Hi3751V553 Android TV.
    // All sysfs/procfs reads are best-effort. No tuning or persistent changes are made.
    private fun collectPerformanceDiagnostics(): JSONObject {
        val report = JSONObject()
        report.put("schemaVersion", "1.4.0")
        report.put("collectionMode", "read_only")
        report.put("deviceHint", "HiSilicon Hi3751V553 / bigfish")
        report.put("uptime", readPerformanceText("/proc/uptime", 256))
        report.put("loadavg", readPerformanceText("/proc/loadavg", 512))
        report.put("cpu", collectCpuPerformance())
        report.put("memory", collectMemoryPerformance())
        report.put("zram", collectZramPerformance())
        report.put("thermal", collectThermalPerformance())
        report.put("gpuDevfreq", collectGpuDevfreq())
        report.put("storageIo", collectStorageIo())
        report.put("processSnapshot", collectProcessSnapshot())
        report.put("readOnlyGuarantees", JSONObject().apply {
            put("sysfsProcfsOnlyForMetrics", true)
            put("settingsChanged", false)
            put("cpuGovernorChanged", false)
            put("cpuFrequencyChanged", false)
            put("zramChanged", false)
            put("servicesStopped", false)
            put("packagesDisabledOrRemoved", false)
            put("partitionContentsRead", false)
            put("partitionWriteAttempted", false)
            put("shellCommandsAreFixedReadOnlyProbes", true)
        })
        report.put("limitations", JSONArray().put("Some vendor sysfs nodes may be hidden or permission-restricted").put("CPU and process snapshots are instantaneous samples, not a long-term benchmark").put("Missing temperature or GPU nodes do not prove that the hardware lacks those sensors"))
        return report
    }

    private fun readPerformanceText(path: String, maxChars: Int = 12000): String {
        return try {
            val file = File(path)
            if (file.isFile && file.canRead()) file.readText().take(maxChars) else ""
        } catch (_: Exception) { "" }
    }

    private fun readPerformanceNumber(path: String): Long? {
        val raw = readPerformanceText(path, 256).trim()
        return raw.toLongOrNull() ?: raw.removeSuffix("MHz").trim().toLongOrNull()
    }

    private fun collectCpuPerformance(): JSONObject {
        val result = JSONObject()
        result.put("cpuinfo", readPerformanceText("/proc/cpuinfo", 9000))
        result.put("statBefore", readPerformanceText("/proc/stat", 2500))
        val before = parseCpuTotals(readPerformanceText("/proc/stat", 2500))
        try { Thread.sleep(600) } catch (_: InterruptedException) { Thread.currentThread().interrupt() }
        val afterText = readPerformanceText("/proc/stat", 2500)
        val after = parseCpuTotals(afterText)
        result.put("statAfter", afterText)
        if (before != null && after != null && after.first > before.first) {
            val totalDelta = after.first - before.first
            val idleDelta = (after.second - before.second).coerceAtLeast(0L)
            val usage = ((totalDelta - idleDelta).toDouble() * 100.0 / totalDelta.toDouble()).coerceIn(0.0, 100.0)
            result.put("sampledTotalUsagePercent", usage)
            result.put("sampleWindowMs", 600)
        } else {
            result.put("sampledTotalUsagePercent", JSONObject.NULL)
            result.put("sampleWindowMs", 600)
        }
        val cores = JSONArray()
        val cpuRoot = File("/sys/devices/system/cpu")
        cpuRoot.listFiles()?.filter { Regex("^cpu[0-9]+$").matches(it.name) }?.sortedBy { it.name.drop(3).toIntOrNull() ?: 999 }?.forEach { cpu ->
            val base = cpu.absolutePath + "/cpufreq/"
            val row = JSONObject().apply {
                put("cpu", cpu.name)
                put("online", readPerformanceText(cpu.absolutePath + "/online", 64).trim())
                put("currentKHz", readPerformanceNumber(base + "scaling_cur_freq") ?: JSONObject.NULL)
                put("minKHz", readPerformanceNumber(base + "scaling_min_freq") ?: JSONObject.NULL)
                put("maxKHz", readPerformanceNumber(base + "scaling_max_freq") ?: JSONObject.NULL)
                put("hardwareMinKHz", readPerformanceNumber(base + "cpuinfo_min_freq") ?: JSONObject.NULL)
                put("hardwareMaxKHz", readPerformanceNumber(base + "cpuinfo_max_freq") ?: JSONObject.NULL)
                put("governor", readPerformanceText(base + "scaling_governor", 256).trim())
                put("availableGovernors", readPerformanceText(base + "scaling_available_governors", 512).trim())
                put("availableFrequenciesKHz", readPerformanceText(base + "scaling_available_frequencies", 1200).trim())
            }
            cores.put(row)
        }
        result.put("cores", cores)
        result.put("coreCount", cores.length())
        result.put("cpuPressure", readPerformanceText("/proc/pressure/cpu", 2000))
        result.put("schedstat", readPerformanceText("/proc/schedstat", 3000))
        return result
    }

    private fun parseCpuTotals(stat: String): Pair<Long, Long>? {
        val line = stat.lineSequence().firstOrNull { it.startsWith("cpu ") } ?: return null
        val values = line.trim().split(Regex("\\s+")).drop(1).mapNotNull { it.toLongOrNull() }
        if (values.size < 4) return null
        val total = values.sum()
        val idle = values[3] + (values.getOrNull(4) ?: 0L)
        return Pair(total, idle)
    }

    private fun collectMemoryPerformance(): JSONObject {
        val result = JSONObject()
        result.put("meminfo", readPerformanceText("/proc/meminfo", 9000))
        result.put("vmstat", readPerformanceText("/proc/vmstat", 10000))
        result.put("memoryPressure", readPerformanceText("/proc/pressure/memory", 3000))
        result.put("zoneinfoSummary", readPerformanceText("/proc/zoneinfo", 5000))
        result.put("processStatus", readPerformanceText("/proc/self/status", 3000))
        result.put("lowMemoryKiller", JSONObject().apply {
            put("minfree", readPerformanceText("/sys/module/lowmemorykiller/parameters/minfree", 1000))
            put("adj", readPerformanceText("/sys/module/lowmemorykiller/parameters/adj", 1000))
            put("psi", readPerformanceText("/proc/pressure/memory", 3000))
        })
        return result
    }

    private fun collectZramPerformance(): JSONArray {
        val result = JSONArray()
        val blockRoot = File("/sys/block")
        blockRoot.listFiles()?.filter { it.name.startsWith("zram") }?.sortedBy { it.name }?.forEach { node ->
            val base = node.absolutePath + "/"
            result.put(JSONObject().apply {
                put("device", node.name)
                put("disksizeBytes", readPerformanceNumber(base + "disksize") ?: JSONObject.NULL)
                put("compAlgorithm", readPerformanceText(base + "comp_algorithm", 1000).trim())
                put("mmStat", readPerformanceText(base + "mm_stat", 2000).trim())
                put("ioStat", readPerformanceText(base + "io_stat", 2000).trim())
                put("bdStat", readPerformanceText(base + "bd_stat", 2000).trim())
                put("stat", readPerformanceText(base + "stat", 2000).trim())
                put("memLimitBytes", readPerformanceNumber(base + "mem_limit") ?: JSONObject.NULL)
                put("memUsedMaxBytes", readPerformanceNumber(base + "mem_used_max") ?: JSONObject.NULL)
                put("backingDevice", readPerformanceText(base + "backing_dev", 500).trim())
                put("maxCompStreams", readPerformanceText(base + "max_comp_streams", 128).trim())
                put("debugStat", readPerformanceText(base + "debug_stat", 2000).trim())
            })
        }
        return result
    }

    private fun collectThermalPerformance(): JSONArray {
        val result = JSONArray()
        val root = File("/sys/class/thermal")
        root.listFiles()?.filter { it.name.startsWith("thermal_zone") }?.sortedBy { it.name }?.forEach { zone ->
            val base = zone.absolutePath + "/"
            val raw = readPerformanceText(base + "temp", 128).trim()
            val numeric = raw.toLongOrNull()
            result.put(JSONObject().apply {
                put("zone", zone.name)
                put("type", readPerformanceText(base + "type", 256).trim())
                put("rawTemperature", raw)
                put("temperatureCelsius", if (numeric != null) {
                    if (numeric > 1000L) numeric.toDouble() / 1000.0 else numeric.toDouble()
                } else JSONObject.NULL)
                put("mode", readPerformanceText(base + "mode", 128).trim())
                put("policy", readPerformanceText(base + "policy", 128).trim())
                put("tripPoints", readPerformanceText(base + "trip_point_0_temp", 128).trim())
            })
        }
        val cooling = JSONArray()
        root.listFiles()?.filter { it.name.startsWith("cooling_device") }?.sortedBy { it.name }?.forEach { dev ->
            cooling.put(JSONObject().apply {
                put("device", dev.name)
                put("type", readPerformanceText(dev.absolutePath + "/type", 256).trim())
                put("curState", readPerformanceText(dev.absolutePath + "/cur_state", 128).trim())
                put("maxState", readPerformanceText(dev.absolutePath + "/max_state", 128).trim())
            })
        }
        return JSONArray().put(JSONObject().put("zones", result).put("coolingDevices", cooling))
    }

    private fun collectGpuDevfreq(): JSONArray {
        val result = JSONArray()
        val roots = listOf("/sys/class/devfreq", "/sys/devices/platform")
        roots.forEach { path ->
            val root = File(path)
            root.listFiles()?.filter { it.name.contains("mali", true) || it.name.contains("gpu", true) }?.forEach { node ->
                val base = node.absolutePath + "/"
                result.put(JSONObject().apply {
                    put("node", node.absolutePath)
                    put("name", readPerformanceText(base + "name", 256).trim())
                    put("curFreq", readPerformanceNumber(base + "cur_freq") ?: JSONObject.NULL)
                    put("minFreq", readPerformanceNumber(base + "min_freq") ?: JSONObject.NULL)
                    put("maxFreq", readPerformanceNumber(base + "max_freq") ?: JSONObject.NULL)
                    put("governor", readPerformanceText(base + "governor", 256).trim())
                    put("availableFrequencies", readPerformanceText(base + "available_frequencies", 1200).trim())
                    put("availableGovernors", readPerformanceText(base + "available_governors", 512).trim())
                })
            }
        }
        return result
    }

    private fun collectStorageIo(): JSONObject {
        return JSONObject().apply {
            put("diskstats", readPerformanceText("/proc/diskstats", 8000))
            put("mmcQueue", JSONObject().apply {
                put("scheduler", readPerformanceText("/sys/block/mmcblk0/queue/scheduler", 512).trim())
                put("readAheadKb", readPerformanceText("/sys/block/mmcblk0/queue/read_ahead_kb", 128).trim())
                put("nrRequests", readPerformanceText("/sys/block/mmcblk0/queue/nr_requests", 128).trim())
                put("rotational", readPerformanceText("/sys/block/mmcblk0/queue/rotational", 128).trim())
                put("logicalBlockSize", readPerformanceText("/sys/block/mmcblk0/queue/logical_block_size", 128).trim())
                put("physicalBlockSize", readPerformanceText("/sys/block/mmcblk0/queue/physical_block_size", 128).trim())
            })
            put("mounts", readPerformanceText("/proc/mounts", 10000))
            put("filesystemStats", runPerformanceReadOnlyCommand("df -k /data /system /vendor /cache"))
        }
    }

    private fun collectProcessSnapshot(): JSONObject {
        return JSONObject().apply {
            put("cpuInfo", runPerformanceReadOnlyCommand("dumpsys cpuinfo"))
            put("top", runPerformanceReadOnlyCommand("top -b -n 1 -m 15"))
            put("activity", runPerformanceReadOnlyCommand("dumpsys activity activities"))
            put("meminfoSummary", runPerformanceReadOnlyCommand("dumpsys meminfo"))
            put("thirdPartyPackages", runPerformanceReadOnlyCommand("pm list packages -3"))
        }
    }

    // Only fixed, read-only Android diagnostic commands are passed here.
    private fun runPerformanceReadOnlyCommand(command: String): JSONObject {
        val output = StringBuilder()
        var exitCode = -1
        var timedOut = false
        var error = ""
        var process: java.lang.Process? = null
        try {
            val running = ProcessBuilder("su", "0", "sh", "-c", command).redirectErrorStream(true).start()
            process = running
            val reader = Thread {
                try {
                    running.inputStream.bufferedReader().useLines { lines ->
                        lines.forEach { line ->
                            synchronized(output) {
                                if (output.length < 14000) output.append(line).append('\n')
                            }
                        }
                    }
                } catch (_: Exception) { }
            }
            reader.start()
            if (!running.waitFor(7, java.util.concurrent.TimeUnit.SECONDS)) {
                timedOut = true
                running.destroyForcibly()
                running.waitFor(1, java.util.concurrent.TimeUnit.SECONDS)
            } else {
                exitCode = running.exitValue()
            }
            reader.join(1000)
        } catch (e: Exception) {
            error = e.message ?: e.javaClass.simpleName
            try { process?.destroyForcibly() } catch (_: Exception) { }
        }
        return JSONObject().apply {
            put("command", command)
            put("output", synchronized(output) { output.toString().take(14000) })
            put("exitCode", exitCode)
            put("timedOut", timedOut)
            put("error", error)
        }
    }

"""
s = s.replace(hook, hook + '\n        put("performanceDiagnostics", collectPerformanceDiagnostics())', 1)
s = s.replace(marker, method + marker, 1)
src.write_text(s, encoding="utf-8")
print("Inserted v1.4.0 read-only CPU, RAM, ZRAM, thermal, GPU, storage and process collectors.")
