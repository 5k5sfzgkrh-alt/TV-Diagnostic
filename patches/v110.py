from pathlib import Path
import os

src = Path(os.environ["SRC"])
gradle = Path(os.environ["GRADLE"])

g = gradle.read_text()
if 'versionName = "1.0.0"' not in g or "versionCode = 100" not in g:
    raise SystemExit("Expected v1.0.0")
g = g.replace("versionCode = 100", "versionCode = 110", 1)
g = g.replace('versionName = "1.0.0"', 'versionName = "1.1.0"', 1)
gradle.write_text(g)

s = src.read_text()
if "Hi3751V553  •  1.0.0" not in s:
    raise SystemExit("Expected v1.0.0 source")
s = s.replace("Hi3751V553  •  1.0.0", "Hi3751V553  •  1.1.0", 1)
s = s.replace('"appVersion", "1.0.0"', '"appVersion", "1.1.0"', 1)
s = s.replace("tv-diagnostic-report-v100.json", "tv-diagnostic-report-v110.json")

# Add a separate explicit action; DTBO remains available.
button_anchor = 'backupButtons.addView(makeButton("Остановить Wi-Fi") { stopBackupServer() })'
button_new = button_anchor + '\n        backupButtons.addView(makeButton("Бэкап BOOT + RECOVERY") { confirmSystemBackup() })'
if 'confirmSystemBackup()' not in s:
    if button_anchor not in s:
        raise SystemExit("v1.0 backup button anchor missing")
    s = s.replace(button_anchor, button_new, 1)

methods = r"""
    // v1.1.0: read-only backups of boot and recovery, one partition at a time.
    // Strict allowlist: no userdata, secure, calibration, identity or unknown partitions.
    private fun confirmSystemBackup() {
        android.app.AlertDialog.Builder(this)
            .setTitle("Резервная копия BOOT и RECOVERY")
            .setMessage("Будут последовательно считаны только разделы boot и recovery. Для каждого проверяются Root, размер, полный объём чтения и SHA-256. Файлы сохраняются в закрытой папке приложения и передаются по временной ссылке в локальной сети. Запись в разделы телевизора не выполняется. Продолжить?")
            .setNegativeButton("Отмена", null)
            .setPositiveButton("Начать копирование") { _, _ -> startSystemPartitionBackup() }
            .show()
    }

    private fun startSystemPartitionBackup() {
        if (backupServer != null) {
            statusView.text = "Сначала останови предыдущую Wi-Fi-передачу"
            return
        }
        statusView.text = "Проверка Root и разделов BOOT / RECOVERY…"
        executor.execute {
            val completed = mutableListOf<File>()
            try {
                val root = runReadOnlyCommand(listOf("su", "0", "id"), 4000)
                val rootText = root.optString("output")
                if (root.optInt("exitCode", -1) != 0 ||
                    !Regex("uid=0(?:\\(|\\s|$)").containsMatchIn(rootText)) {
                    throw IllegalStateException("Root не подтверждён: " + rootText)
                }

                val dir = File(filesDir, "backups")
                if (!dir.exists() && !dir.mkdirs())
                    throw IllegalStateException("Не удалось создать папку резервных копий")

                val allowed = listOf("boot", "recovery")
                for (partition in allowed) {
                    runOnUiThread { statusView.text = "Подготовка раздела " + partition.uppercase() + "…" }
                    val device = "/dev/block/by-name/" + partition
                    val sizeResult = runReadOnlyCommand(
                        listOf("su", "0", "blockdev", "--getsize64", device), 5000
                    )
                    val bytes = sizeResult.optString("output").trim().toLongOrNull() ?: 0L
                    val maxBytes = 128L * 1024L * 1024L
                    if (sizeResult.optInt("exitCode", -1) != 0 ||
                        bytes <= 0L || bytes > maxBytes || bytes % 512L != 0L) {
                        throw IllegalStateException(
                            "Размер " + partition + " не прошёл проверку безопасности: " + bytes + " байт"
                        )
                    }
                    if (android.os.StatFs(filesDir.absolutePath).availableBytes < bytes + 16L * 1024L * 1024L) {
                        throw IllegalStateException("Недостаточно свободного места для " + partition)
                    }

                    val blockSize = if (bytes % 4096L == 0L) 4096L else 512L
                    val blocks = bytes / blockSize
                    val file = File(dir, partition + "-" + System.currentTimeMillis() + ".img")
                    val hash = java.security.MessageDigest.getInstance("SHA-256")
                    val buffer = ByteArray(64 * 1024)
                    var copied = 0L
                    var proc: Process? = null
                    try {
                        proc = ProcessBuilder(
                            "su", "0", "dd", "if=" + device,
                            "bs=" + blockSize, "count=" + blocks
                        ).start()
                        val process = proc
                        val errors = StringBuilder()
                        val errorReader = Thread {
                            try {
                                process.errorStream.bufferedReader().use { reader ->
                                    while (true) {
                                        val line = reader.readLine() ?: break
                                        synchronized(errors) {
                                            if (errors.length < 2000) errors.append(line).append('\n')
                                        }
                                    }
                                }
                            } catch (_: Exception) { }
                        }
                        errorReader.start()

                        java.io.FileOutputStream(file).use { output ->
                            process.inputStream.use { input ->
                                while (copied < bytes) {
                                    val wanted = minOf(buffer.size.toLong(), bytes - copied).toInt()
                                    val n = input.read(buffer, 0, wanted)
                                    if (n < 0) break
                                    if (n == 0) continue
                                    copied += n.toLong()
                                    hash.update(buffer, 0, n)
                                    output.write(buffer, 0, n)
                                }
                            }
                            output.fd.sync()
                        }
                        if (!process.waitForWithTimeout(20000)) {
                            process.destroyForcibly()
                            throw IllegalStateException("Чтение " + partition + " превысило лимит времени")
                        }
                        errorReader.join(1500)
                        if (process.exitValue() != 0) {
                            throw IllegalStateException(
                                "dd для " + partition + " завершился с кодом " +
                                    process.exitValue() + ": " + errors.toString()
                            )
                        }
                        if (copied != bytes || file.length() != bytes) {
                            throw IllegalStateException(
                                "Неполный образ " + partition + ": " + copied + " из " + bytes + " байт"
                            )
                        }

                        val hash1 = hash.digest().joinToString("") { "%02x".format(it) }
                        val check = java.security.MessageDigest.getInstance("SHA-256")
                        java.io.FileInputStream(file).use { input ->
                            while (true) {
                                val n = input.read(buffer)
                                if (n < 0) break
                                if (n > 0) check.update(buffer, 0, n)
                            }
                        }
                        val hash2 = check.digest().joinToString("") { "%02x".format(it) }
                        if (!hash1.equals(hash2, true))
                            throw IllegalStateException("Повторная проверка SHA-256 не совпала для " + partition)
                        completed.add(file)
                        runOnUiThread {
                            statusView.text = partition.uppercase() + " готов: " + bytes +
                                " байт\nSHA-256: " + hash2 + "\nПодготовка следующего раздела…"
                        }
                    } catch (e: Exception) {
                        try { file.delete() } catch (_: Exception) { }
                        throw e
                    } finally {
                        if (proc != null && proc.isAlive) proc.destroyForcibly()
                    }
                }

                // Transfer one archive containing only the two verified images.
                val archive = File(dir, "boot-recovery-" + System.currentTimeMillis() + ".zip")
                java.util.zip.ZipOutputStream(java.io.FileOutputStream(archive)).use { zip ->
                    completed.forEach { file ->
                        zip.putNextEntry(java.util.zip.ZipEntry(file.name))
                        java.io.FileInputStream(file).use { input -> input.copyTo(zip, 64 * 1024) }
                        zip.closeEntry()
                    }
                    zip.finish()
                }
                val archiveHash = java.security.MessageDigest.getInstance("SHA-256")
                java.io.FileInputStream(archive).use { input ->
                    while (true) {
                        val n = input.read(buffer)
                        if (n < 0) break
                        if (n > 0) archiveHash.update(buffer, 0, n)
                    }
                }
                val zipSha = archiveHash.digest().joinToString("") { "%02x".format(it) }
                runOnUiThread {
                    statusView.text = "BOOT и RECOVERY скопированы и проверены.\n" +
                        completed.joinToString("\n") { it.name + " • " + it.length() + " байт" } +
                        "\nZIP SHA-256: " + zipSha + "\nПодготовка Wi-Fi…"
                }
                startBackupHttpServer(archive, zipSha)
            } catch (e: Exception) {
                runOnUiThread {
                    statusView.text = "Резервное копирование остановлено: " +
                        (e.message ?: e.javaClass.simpleName) +
                        ". Уже созданные проверенные файлы оставлены в папке приложения; разделы ТВ не изменялись."
                }
            }
        }
    }

"""
anchor = "    private fun formatReport(j: JSONObject): String {"
if "private fun startSystemPartitionBackup()" not in s:
    if anchor not in s:
        raise SystemExit("v1.0 formatter anchor missing")
    s = s.replace(anchor, methods + anchor, 1)

# Serve the archive under its actual filename, retaining the one-time token and timeout.
old_header = r'"\\r\\nContent-Disposition: attachment; filename=\\\"dtbo.img\\\"" +'
new_header = r'"\\r\\nContent-Disposition: attachment; filename=\\\"" + file.name + "\\\"" +'
if old_header in s:
    s = s.replace(old_header, new_header, 1)
elif 'filename=\\\"' + '" + file.name' not in s:
    raise SystemExit("Could not safely generalize backup download filename")

required = [
    'versionName = "1.1.0"', "versionCode = 110",
    '"appVersion", "1.1.0"', "confirmSystemBackup()",
    "private fun startSystemPartitionBackup()", 'listOf("boot", "recovery")',
    'maxBytes = 128L * 1024L * 1024L',
    'startBackupHttpServer(archive, zipSha)',
    'tv-diagnostic-report-v110.json'
]
missing = [x for x in required if x not in g + s]
if missing:
    raise SystemExit("v1.1.0 verification failed: " + ", ".join(missing))
src.write_text(s)
print("v1.1.0 boot/recovery read-only backup patch applied and verified")
