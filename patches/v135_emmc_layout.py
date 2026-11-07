from pathlib import Path

src = Path("project/app/src/main/java/com/tvdiagnostic/hi3751/MainActivity.kt")
s = src.read_text(encoding="utf-8")

hook = '        put("rawPartitionDataRead", false)'
marker = '    private fun collectBootInfo(): JSONObject = JSONObject().apply {'
if s.count(hook) != 1:
    raise SystemExit(f"Expected exactly one partition safety marker, got {s.count(hook)}")
if s.count(marker) != 1:
    raise SystemExit(f"Expected exactly one collectBootInfo marker, got {s.count(marker)}")
if "private fun collectEmmcLayout()" in s:
    raise SystemExit("eMMC layout collector already exists; refusing duplicate patch")

method = r"""
    // v1.3.5: read-only eMMC geometry and GPT inventory.
    // Linux sysfs start/size values are expressed in 512-byte sectors.
    // No raw partition contents are opened, and no partition metadata is changed.
    private fun collectEmmcLayout(): JSONObject {
        val report = JSONObject()
        val sectorBytes = 512L
        val diskSizeSectors = readNumber("/sys/class/block/mmcblk0/size")
        report.put("device", "/dev/block/mmcblk0")
        report.put("sectorSizeBytes", sectorBytes)
        report.put("diskSizeSectors512", diskSizeSectors ?: JSONObject.NULL)
        report.put("diskSizeBytes", diskSizeSectors?.times(sectorBytes) ?: JSONObject.NULL)

        val partitions = JSONArray()
        val rows = mutableListOf<JSONObject>()
        val sysBlock = File("/sys/class/block")
        sysBlock.listFiles()
            ?.filter { Regex("^mmcblk0p[0-9]+$").matches(it.name) }
            ?.sortedBy { it.name.substringAfter("mmcblk0p").toIntOrNull() ?: Int.MAX_VALUE }
            ?.forEach { node ->
                val start = readNumber(node.absolutePath + "/start")
                val size = readNumber(node.absolutePath + "/size")
                val endExclusive = if (start != null && size != null) start + size else null
                val row = JSONObject().apply {
                    put("name", node.name)
                    put("path", "/dev/block/" + node.name)
                    put("startSector512", start ?: JSONObject.NULL)
                    put("sizeSectors512", size ?: JSONObject.NULL)
                    put("endSectorExclusive512", endExclusive ?: JSONObject.NULL)
                    put("endSectorInclusive512", if (endExclusive != null && size != 0L) endExclusive - 1L else JSONObject.NULL)
                    put("startBytes", start?.times(sectorBytes) ?: JSONObject.NULL)
                    put("sizeBytes", size?.times(sectorBytes) ?: JSONObject.NULL)
                    put("metadataComplete", start != null && size != null)
                }
                partitions.put(row)
                rows.add(row)
            }
        report.put("partitions", partitions)
        report.put("partitionCount", partitions.length())
        report.put("partitionMetadataComplete", rows.isNotEmpty() && rows.all { it.optBoolean("metadataComplete") })

        val ordered = rows.filter { it.optBoolean("metadataComplete") }
            .sortedBy { it.optLong("startSector512") }
        val gaps = JSONArray()
        val overlaps = JSONArray()
        val outOfBounds = JSONArray()
        var cursor = 0L
        ordered.forEach { row ->
            val start = row.optLong("startSector512")
            val size = row.optLong("sizeSectors512")
            val end = start + size
            if (start > cursor) {
                gaps.put(JSONObject().apply {
                    put("startSector512", cursor)
                    put("endSectorExclusive512", start)
                    put("sizeSectors512", start - cursor)
                    put("note", "Unallocated gap; may include GPT metadata or intentional reserved space")
                })
            } else if (start < cursor) {
                overlaps.put(JSONObject().apply {
                    put("partition", row.optString("name"))
                    put("startSector512", start)
                    put("previousEndSectorExclusive512", cursor)
                    put("overlapSectors512", cursor - start)
                })
            }
            if (diskSizeSectors != null && end > diskSizeSectors) {
                outOfBounds.put(JSONObject().apply {
                    put("partition", row.optString("name"))
                    put("endSectorExclusive512", end)
                    put("diskSizeSectors512", diskSizeSectors)
                })
            }
            if (end > cursor) cursor = end
        }
        if (diskSizeSectors != null && cursor < diskSizeSectors) {
            gaps.put(JSONObject().apply {
                put("startSector512", cursor)
                put("endSectorExclusive512", diskSizeSectors)
                put("sizeSectors512", diskSizeSectors - cursor)
                put("note", "Trailing unallocated area; may contain backup GPT metadata")
            })
        }
        report.put("gaps", gaps)
        report.put("overlaps", overlaps)
        report.put("outOfBounds", outOfBounds)
        report.put("overlapCount", overlaps.length())
        report.put("outOfBoundsCount", outOfBounds.length())

        val bootAreas = JSONArray()
        listOf("mmcblk0boot0", "mmcblk0boot1").forEach { name ->
            val sectors = readNumber("/sys/class/block/" + name + "/size")
            bootAreas.put(JSONObject().apply {
                put("name", name)
                put("sizeSectors512", sectors ?: JSONObject.NULL)
                put("sizeBytes", sectors?.times(sectorBytes) ?: JSONObject.NULL)
                put("metadataAvailable", sectors != null)
            })
        }
        report.put("emmcBootAreas", bootAreas)

        val rootProbe = runEmmcReadOnlyCommand("id")
        val rootOutput = rootProbe.optString("output")
        val rootConfirmed = rootProbe.optInt("exitCode", -1) == 0 &&
            Regex("uid=0(?:\\(|\\s|$)").containsMatchIn(rootOutput)
        report.put("rootProbe", rootProbe)
        report.put("rootConfirmedForGptRead", rootConfirmed)

        val gptCommands = JSONArray()
        val commands = listOf(
            Pair("sfdisk", "if command -v sfdisk >/dev/null 2>&1; then sfdisk --dump /dev/block/mmcblk0; else echo __MISSING_TOOL__:sfdisk; exit 127; fi"),
            Pair("sgdisk", "if command -v sgdisk >/dev/null 2>&1; then sgdisk -p /dev/block/mmcblk0; else echo __MISSING_TOOL__:sgdisk; exit 127; fi"),
            Pair("fdisk", "if command -v fdisk >/dev/null 2>&1; then fdisk -l /dev/block/mmcblk0; else echo __MISSING_TOOL__:fdisk; exit 127; fi")
        )
        commands.forEach { item ->
            val result = if (rootConfirmed) {
                runEmmcReadOnlyCommand(item.second).apply { put("tool", item.first) }
            } else {
                JSONObject().apply {
                    put("tool", item.first)
                    put("status", "skipped_root_unavailable")
                    put("command", item.second)
                    put("output", "")
                    put("exitCode", JSONObject.NULL)
                    put("timedOut", false)
                }
            }
            gptCommands.put(result)
        }
        report.put("gptReadOnlyCommands", gptCommands)
        report.put("rawPartitionContentsRead", false)
        report.put("partitionWriteAttempted", false)
        report.put("gptWriteAttempted", false)
        report.put("note", "Геометрия получена из sysfs; команды GPT только читают таблицу. Содержимое raw-разделов не читалось, разметка не изменялась. Пропуски могут быть штатными областями GPT.")
        return report
    }

    // Executes only fixed, read-only inventory commands through the existing root manager.
    private fun runEmmcReadOnlyCommand(command: String): JSONObject {
        val output = StringBuilder()
        var exitCode = -1
        var timedOut = false
        var error = ""
        var process: Process? = null
        try {
            val running = ProcessBuilder("su", "0", "sh", "-c", command)
                .redirectErrorStream(true)
                .start()
            process = running
            val reader = Thread {
                try {
                    running.inputStream.bufferedReader().useLines { lines ->
                        lines.forEach { line ->
                            synchronized(output) {
                                if (output.length < 18000) output.append(line).append('\n')
                            }
                        }
                    }
                } catch (_: Exception) { }
            }
            reader.start()
            if (!running.waitFor(8, java.util.concurrent.TimeUnit.SECONDS)) {
                timedOut = true
                running.destroyForcibly()
                running.waitFor(1, java.util.concurrent.TimeUnit.SECONDS)
            } else {
                exitCode = running.exitValue()
            }
            reader.join(1200)
        } catch (e: Exception) {
            error = e.message ?: e.javaClass.simpleName
            try { process?.destroyForcibly() } catch (_: Exception) { }
        }
        val captured = synchronized(output) { output.toString().take(18000) }
        return JSONObject().apply {
            put("command", command)
            put("output", captured)
            put("exitCode", exitCode)
            put("timedOut", timedOut)
            put("error", error)
            put("toolMissing", captured.contains("__MISSING_TOOL__"))
        }
    }

"""
s = s.replace(hook, '        put("eMMCLayout", collectEmmcLayout())\n' + hook, 1)
s = s.replace(marker, method + marker, 1)
src.write_text(s, encoding="utf-8")
print("Inserted read-only eMMC geometry, gap/overlap checks, boot0/boot1 metadata and GPT command probes.")
