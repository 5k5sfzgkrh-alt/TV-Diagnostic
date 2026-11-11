from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path("project")
SRC = ROOT / "app/src/main/java/com/tvdiagnostic/hi3751/MainActivity.kt"
GRADLE = ROOT / "app/build.gradle.kts"
MANIFEST = ROOT / "app/src/main/AndroidManifest.xml"
src = SRC.read_text(encoding="utf-8")

anchors = (
    '        outer.addView(systemBackupButtons)\n',
    '    @Volatile private var backupServer: java.net.ServerSocket? = null\n',
    '    private fun confirmSystemBackup() {\n',
    'TV DIAGNOSTIC  •  Hi3751V553  •  1.7.0'
)
for anchor in anchors:
    if src.count(anchor) != 1:
        raise SystemExit("Expected unique v1.7.0 source anchor: " + anchor)
if "confirmRamdiskDirectExport" in src:
    raise SystemExit("RAMDISK export already exists; refusing duplicate patch")

button = '''        outer.addView(systemBackupButtons)
        val ramdiskButtons = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        ramdiskButtons.addView(makeButton("Экспорт RAMDISK • 1 МиБ") { confirmRamdiskDirectExport() })
        outer.addView(ramdiskButtons)
'''
src = src.replace(anchors[0], button, 1)
src = src.replace(anchors[3], "TV DIAGNOSTIC  •  Hi3751V553  •  1.8.0", 1)
src = src.replace(anchors[1], anchors[1] +
    '    @Volatile private var ramdiskExportInProgress: Boolean = false\n', 1)

methods = r'''
    // v1.8.0: read-only RAMDISK export. The TV stores no image file.
    private fun confirmRamdiskDirectExport() {
        android.app.AlertDialog.Builder(this)
            .setTitle("Экспорт RAMDISK • только чтение")
            .setMessage(
                "Проверяется только /dev/block/by-name/ramdisk -> /dev/block/mmcblk0p25 " +
                "размером ровно 1 МиБ. Первый проход вычисляет SHA-256, второй передаёт " +
                "байты напрямую на телефон по одноразовой ссылке. Файл на ТВ не создаётся. " +
                "Запись в разделы не выполняется. HTTP без шифрования — только доверенная сеть."
            )
            .setNegativeButton("Отмена", null)
            .setPositiveButton("Проверить и передать") { _, _ -> startRamdiskDirectExport() }
            .show()
    }

    private fun startRamdiskDirectExport() {
        if (backupServer != null || ramdiskExportInProgress) {
            statusView.text = "Сначала останови предыдущую передачу"
            return
        }
        ramdiskExportInProgress = true
        statusView.text = "Проверка Root, пути и размера RAMDISK…"
        executor.execute {
            try {
                val root = runReadOnlyCommand(listOf("su", "0", "id"), 5000)
                val rootText = root.optString("output")
                if (root.optInt("exitCode", -1) != 0 ||
                    root.optBoolean("timedOut", false) ||
                    !Regex("uid=0(?:\\(|\\s|$)").containsMatchIn(rootText)) {
                    throw IllegalStateException("Root не подтверждён: " + rootText)
                }

                val link = "/dev/block/by-name/ramdisk"
                val resolved = runReadOnlyCommand(
                    listOf("su", "0", "readlink", "-f", link), 5000
                )
                val device = resolved.optString("output").trim()
                if (resolved.optInt("exitCode", -1) != 0 ||
                    resolved.optBoolean("timedOut", false) ||
                    device != "/dev/block/mmcblk0p25") {
                    throw IllegalStateException("Неверный путь RAMDISK: " + link + " -> " + device)
                }

                val expectedBytes = 1048576L
                val size = runReadOnlyCommand(
                    listOf("su", "0", "blockdev", "--getsize64", device), 5000
                )
                val bytes = size.optString("output").trim().toLongOrNull() ?: 0L
                if (size.optInt("exitCode", -1) != 0 ||
                    size.optBoolean("timedOut", false) || bytes != expectedBytes) {
                    throw IllegalStateException("Размер RAMDISK не равен 1048576 байт: " + bytes)
                }

                val sectorsResult = runReadOnlyCommand(
                    listOf("su", "0", "cat", "/sys/class/block/mmcblk0p25/size"), 4000
                )
                val sectors = sectorsResult.optString("output").trim().toLongOrNull() ?: 0L
                if (sectorsResult.optInt("exitCode", -1) != 0 ||
                    sectorsResult.optBoolean("timedOut", false) ||
                    sectors != 2048L || sectors * 512L != expectedBytes) {
                    throw IllegalStateException("Проверка sysfs размера не пройдена: " + sectors)
                }

                runOnUiThread {
                    statusView.text = "RAMDISK подтверждён • 1 МиБ. Вычисление SHA-256…"
                }
                val hash = computeRamdiskSha256(device, expectedBytes)
                startRamdiskDirectHttpServer(device, expectedBytes, hash)
            } catch (e: Exception) {
                ramdiskExportInProgress = false
                runOnUiThread {
                    statusView.text = "Экспорт RAMDISK НЕ выполнен: " +
                        (e.message ?: e.javaClass.simpleName) +
                        ". Файл на ТВ не создавался; разделы не изменялись."
                }
            }
        }
    }

    private fun computeRamdiskSha256(device: String, expectedBytes: Long): String {
        val blocks = expectedBytes / 4096L
        val proc = ProcessBuilder(
            "su", "0", "dd", "if=" + device, "bs=4096", "count=" + blocks
        ).start()
        val digest = java.security.MessageDigest.getInstance("SHA-256")
        val copied = java.util.concurrent.atomic.AtomicLong(0L)
        val failure = java.util.concurrent.atomic.AtomicReference<String?>(null)
        val errors = StringBuilder()
        val reader = Thread {
            try {
                proc.inputStream.use { input ->
                    val buffer = ByteArray(32768)
                    while (true) {
                        val n = input.read(buffer)
                        if (n < 0) break
                        if (n == 0) continue
                        val total = copied.addAndGet(n.toLong())
                        if (total > expectedBytes) {
                            failure.set("dd прочитал больше ожидаемого размера")
                            proc.destroyForcibly()
                            break
                        }
                        digest.update(buffer, 0, n)
                    }
                }
            } catch (e: Exception) {
                failure.set(e.message ?: e.javaClass.simpleName)
            }
        }
        val errorReader = Thread {
            try {
                proc.errorStream.bufferedReader().use { stream ->
                    while (true) {
                        val line = stream.readLine() ?: break
                        synchronized(errors) {
                            if (errors.length < 2000) errors.append(line).append('\n')
                        }
                    }
                }
            } catch (_: Exception) { }
        }
        reader.start()
        errorReader.start()
        if (!proc.waitFor(30, java.util.concurrent.TimeUnit.SECONDS)) {
            proc.destroyForcibly()
            reader.join(2000)
            errorReader.join(1000)
            throw IllegalStateException("Первое чтение RAMDISK превысило 30 секунд")
        }
        reader.join(5000)
        errorReader.join(1000)
        if (reader.isAlive) {
            proc.destroyForcibly()
            throw IllegalStateException("Поток чтения RAMDISK не завершился")
        }
        failure.get()?.let { throw IllegalStateException("Ошибка чтения RAMDISK: " + it) }
        if (proc.exitValue() != 0) {
            throw IllegalStateException("dd завершился с кодом " + proc.exitValue() + ": " + errors)
        }
        if (copied.get() != expectedBytes) {
            throw IllegalStateException("Неполное чтение RAMDISK: " + copied.get())
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    private fun startRamdiskDirectHttpServer(
        device: String,
        expectedBytes: Long,
        expectedSha256: String
    ) {
        Thread {
            var created: java.net.ServerSocket? = null
            try {
                val server = java.net.ServerSocket()
                created = server
                server.reuseAddress = false
                server.bind(java.net.InetSocketAddress(0), 1)
                server.soTimeout = 5 * 60 * 1000
                backupServer = server

                val random = ByteArray(16)
                java.security.SecureRandom().nextBytes(random)
                val token = random.joinToString("") { "%02x".format(it) }
                val ip = java.util.Collections.list(java.net.NetworkInterface.getNetworkInterfaces())
                    .asSequence()
                    .filter { try { it.isUp && !it.isLoopback } catch (_: Exception) { false } }
                    .flatMap { java.util.Collections.list(it.inetAddresses).asSequence() }
                    .filterIsInstance<java.net.Inet4Address>()
                    .firstOrNull { it.isSiteLocalAddress && !it.isLoopbackAddress }
                    ?.hostAddress ?: throw IllegalStateException("Не найден локальный IPv4 телевизора")
                val url = "http://" + ip + ":" + server.localPort + "/download?token=" + token
                runOnUiThread {
                    statusView.text = "RAMDISK готов • " + expectedBytes + " байт\nSHA-256: " +
                        expectedSha256 + "\nОткрой на iPhone в той же Wi-Fi сети:\n" + url +
                        "\nОдноразовая ссылка действует 5 минут. Файл на ТВ не сохраняется."
                }

                val socket = server.accept()
                socket.use { client ->
                    client.soTimeout = 10000
                    val reader = client.getInputStream().bufferedReader(Charsets.ISO_8859_1)
                    val request = reader.readLine() ?: ""
                    while (true) {
                        val line = reader.readLine() ?: break
                        if (line.isEmpty()) break
                    }
                    val expectedRequest = "GET /download?token=" + token + " HTTP/"
                    val out = client.getOutputStream()
                    if (!request.startsWith(expectedRequest)) {
                        out.write((
                            "HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n" +
                            "Cache-Control: no-store\r\nConnection: close\r\n\r\n"
                        ).toByteArray(Charsets.US_ASCII))
                        out.flush()
                        throw IllegalStateException("Одноразовый токен не совпал")
                    }

                    val headers = "HTTP/1.1 200 OK\r\n" +
                        "Content-Type: application/octet-stream\r\n" +
                        "Content-Length: " + expectedBytes + "\r\n" +
                        "Content-Disposition: attachment; filename=ramdisk.img\r\n" +
                        "X-Content-SHA256: " + expectedSha256 + "\r\n" +
                        "Cache-Control: no-store\r\nConnection: close\r\n\r\n"
                    out.write(headers.toByteArray(Charsets.US_ASCII))
                    out.flush()
                    val actualHash = streamRamdiskToClient(
                        device, expectedBytes, expectedSha256, out
                    )
                    runOnUiThread {
                        statusView.text = "RAMDISK передан напрямую на телефон. Размер: " +
                            expectedBytes + " байт\nSHA-256: " + actualHash +
                            "\nОба прохода совпали. Локальный файл на ТВ не создавался."
                    }
                }
            } catch (e: Exception) {
                if (backupServer != null) runOnUiThread {
                    statusView.text = "Передача RAMDISK остановлена: " +
                        (e.message ?: e.javaClass.simpleName) + ". Раздел не изменялся."
                }
            } finally {
                try { created?.close() } catch (_: Exception) { }
                if (backupServer === created) backupServer = null
                ramdiskExportInProgress = false
            }
        }.start()
    }

    private fun streamRamdiskToClient(
        device: String,
        expectedBytes: Long,
        expectedSha256: String,
        output: java.io.OutputStream
    ): String {
        val blocks = expectedBytes / 4096L
        val proc = ProcessBuilder(
            "su", "0", "dd", "if=" + device, "bs=4096", "count=" + blocks
        ).start()
        val digest = java.security.MessageDigest.getInstance("SHA-256")
        var copied = 0L
        val errors = StringBuilder()
        val errorReader = Thread {
            try {
                proc.errorStream.bufferedReader().use { stream ->
                    while (true) {
                        val line = stream.readLine() ?: break
                        synchronized(errors) {
                            if (errors.length < 2000) errors.append(line).append('\n')
                        }
                    }
                }
            } catch (_: Exception) { }
        }
        errorReader.start()
        val watchdog = Thread {
            try {
                Thread.sleep(30000L)
                if (proc.isAlive) proc.destroyForcibly()
            } catch (_: InterruptedException) { }
        }
        watchdog.isDaemon = true
        watchdog.start()
        try {
            proc.inputStream.use { input ->
                val buffer = ByteArray(32768)
                while (true) {
                    val n = input.read(buffer)
                    if (n < 0) break
                    if (n == 0) continue
                    copied += n.toLong()
                    if (copied > expectedBytes) {
                        throw IllegalStateException("Второй проход прочитал больше 1 МиБ")
                    }
                    digest.update(buffer, 0, n)
                    output.write(buffer, 0, n)
                }
            }
            if (!proc.waitFor(5, java.util.concurrent.TimeUnit.SECONDS)) {
                proc.destroyForcibly()
                throw IllegalStateException("Второе чтение RAMDISK не завершилось")
            }
            errorReader.join(1000)
            if (proc.exitValue() != 0) {
                throw IllegalStateException("dd второго прохода: " + proc.exitValue() + ": " + errors)
            }
            if (copied != expectedBytes) {
                throw IllegalStateException("Передано " + copied + " из " + expectedBytes + " байт")
            }
            val actualHash = digest.digest().joinToString("") { "%02x".format(it) }
            if (!actualHash.equals(expectedSha256, true)) {
                throw IllegalStateException("SHA-256 второго прохода не совпал")
            }
            output.flush()
            return actualHash
        } catch (e: Exception) {
            proc.destroyForcibly()
            throw e
        } finally {
            watchdog.interrupt()
        }
    }

'''
marker = '    private fun confirmSystemBackup() {\n'
if src.count(marker) != 1:
    raise SystemExit("RAMDISK methods insertion anchor mismatch")
src = src.replace(marker, methods + marker, 1)

gradle = GRADLE.read_text(encoding="utf-8")
for old, new in [
    ("versionCode = 170", "versionCode = 180"),
    ('versionName = "1.7.0"', 'versionName = "1.8.0"')
]:
    if gradle.count(old) != 1:
        raise SystemExit("Gradle metadata anchor mismatch: " + old)
    gradle = gradle.replace(old, new, 1)
GRADLE.write_text(gradle, encoding="utf-8")

ET.register_namespace("android", "http://schemas.android.com/apk/res/android")
tree = ET.parse(MANIFEST)
app = tree.getroot().find("application")
if app is None:
    raise SystemExit("AndroidManifest has no application element")
label = "{http://schemas.android.com/apk/res/android}label"
if app.get(label) != "TV Diagnostic 1.7.0":
    raise SystemExit("Manifest label is not the expected v1.7.0 value")
app.set(label, "TV Diagnostic 1.8.0")
tree.write(MANIFEST, encoding="utf-8", xml_declaration=True)

start = src.index("    private fun confirmRamdiskDirectExport()")
end = src.index("    private fun confirmSystemBackup()", start)
ramdisk_code = src[start:end]
for forbidden in (
    "FileOutputStream", "File(filesDir", "dd of=", "blockdev --setrw",
    "fastboot flash", "flash_image", "erase_partition", "mkdirs()"
):
    if forbidden in ramdisk_code:
        raise SystemExit("Unsafe RAMDISK export token found: " + forbidden)
for required in (
    "/dev/block/mmcblk0p25", "1048576L", "2048L", "blockdev",
    "readlink", "computeRamdiskSha256", "streamRamdiskToClient",
    "X-Content-SHA256", "MessageDigest", "su", "dd"
):
    if required not in ramdisk_code:
        raise SystemExit("Required RAMDISK export check missing: " + required)

SRC.write_text(src, encoding="utf-8")
print("Applied v1.8.0 RAMDISK direct-export patch; no TV-side image file is created.")
