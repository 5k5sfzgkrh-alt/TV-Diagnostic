from pathlib import Path
import os

src = Path(os.environ["SRC"])
gradle = Path(os.environ["GRADLE"])
manifest = Path(os.environ["MANIFEST"])

g = gradle.read_text()
if 'versionName = "0.9.0"' not in g or "versionCode = 9" not in g:
    raise SystemExit("Expected v0.9.0")
g = g.replace("versionCode = 9", "versionCode = 100", 1)
g = g.replace('versionName = "0.9.0"', 'versionName = "1.0.0"', 1)
gradle.write_text(g)

s = src.read_text()
if "Hi3751V553  •  0.9.0" not in s:
    raise SystemExit("Expected v0.9.0 source")
s = s.replace("Hi3751V553  •  0.9.0", "Hi3751V553  •  1.0.0", 1)
s = s.replace('"appVersion", "0.9.0"', '"appVersion", "1.0.0"', 1)
s = s.replace("tv-diagnostic-report-v090.json", "tv-diagnostic-report-v100.json")

ui_anchor = """        outer.addView(buttons)
        outer.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))"""
ui_insert = """        outer.addView(buttons)
        val backupButtons = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        backupButtons.addView(makeButton("Создать бэкап DTBO") { confirmDtboBackup() })
        backupButtons.addView(makeButton("Остановить Wi-Fi") { stopBackupServer() })
        outer.addView(backupButtons)
        outer.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))"""
if "confirmDtboBackup()" not in s:
    if ui_anchor not in s:
        raise SystemExit("UI anchor missing")
    s = s.replace(ui_anchor, ui_insert, 1)

methods = r"""
    // First backup milestone: DTBO only. dd reads the block node; no block-device writes.
    @Volatile private var backupServer: java.net.ServerSocket? = null

    private fun confirmDtboBackup() {
        android.app.AlertDialog.Builder(this)
            .setTitle("Резервная копия DTBO")
            .setMessage("Будет считан только раздел DTBO. Данные сохраняются в закрытую папку приложения; затем их можно скачать на телефон по локальной сети. Передача HTTP без шифрования, поэтому используй только доверенную домашнюю сеть. Продолжить?")
            .setNegativeButton("Отмена", null)
            .setPositiveButton("Начать копирование") { _, _ -> startDtboBackup() }
            .show()
    }

    private fun startDtboBackup() {
        if (backupServer != null) {
            statusView.text = "Сначала останови предыдущую Wi-Fi-передачу"
            return
        }
        statusView.text = "Проверка Root и размера DTBO…"
        executor.execute {
            var partial: File? = null
            try {
                val device = "/dev/block/by-name/dtbo"
                val root = runReadOnlyCommand(listOf("su", "0", "id"), 4000)
                val rootText = root.optString("output")
                if (root.optInt("exitCode", -1) != 0 ||
                    !Regex("uid=0(?:\\(|\\s|$)").containsMatchIn(rootText)) {
                    throw IllegalStateException("Root не подтверждён: " + rootText)
                }

                val sizeResult = runReadOnlyCommand(
                    listOf("su", "0", "blockdev", "--getsize64", device), 5000
                )
                var bytes = sizeResult.optString("output").trim().toLongOrNull() ?: 0L
                if (bytes <= 0L) {
                    val node = try { File(device).canonicalFile.name } catch (_: Exception) { "" }
                    val paths = listOf("/sys/class/block/" + node + "/size",
                        "/sys/block/mmcblk0/" + node + "/size")
                    val sectors = paths.firstNotNullOfOrNull { readNumber(it) } ?: 0L
                    bytes = sectors * 512L
                }
                if (bytes <= 0L || bytes > 16L * 1024L * 1024L || bytes % 4096L != 0L)
                    throw IllegalStateException("Размер DTBO не определён безопасно: " + bytes + " байт")
                if (android.os.StatFs(filesDir.absolutePath).availableBytes < bytes + 8L * 1024L * 1024L)
                    throw IllegalStateException("Недостаточно свободного места в папке приложения")

                val dir = File(filesDir, "backups")
                if (!dir.exists() && !dir.mkdirs()) throw IllegalStateException("Не удалось создать папку backup")
                val file = File(dir, "dtbo-" + System.currentTimeMillis() + ".img")
                partial = file
                val blocks = bytes / 4096L
                val proc = ProcessBuilder("su", "0", "dd", "if=" + device,
                    "bs=4096", "count=" + blocks).start()
                val errors = StringBuilder()
                val errorReader = Thread {
                    try {
                        proc.errorStream.bufferedReader().use { r ->
                            while (true) {
                                val line = r.readLine() ?: break
                                synchronized(errors) { if (errors.length < 2000) errors.append(line).append('\n') }
                            }
                        }
                    } catch (_: Exception) { }
                }
                errorReader.start()

                val hash = java.security.MessageDigest.getInstance("SHA-256")
                val buffer = ByteArray(64 * 1024)
                var copied = 0L
                java.io.FileOutputStream(file).use { out ->
                    proc.inputStream.use { input ->
                        while (true) {
                            val n = input.read(buffer)
                            if (n < 0) break
                            if (n == 0) continue
                            copied += n.toLong()
                            if (copied > bytes) throw IllegalStateException("Получено больше байт, чем размер DTBO")
                            hash.update(buffer, 0, n)
                            out.write(buffer, 0, n)
                            if (copied == bytes || copied % (256L * 1024L) < n) {
                                val pct = (copied * 100L / bytes).coerceIn(0L, 100L)
                                runOnUiThread { statusView.text = "Чтение DTBO: " + pct + "% (" + copied + "/" + bytes + " байт)" }
                            }
                        }
                    }
                    out.fd.sync()
                }
                if (!proc.waitForWithTimeout(15000)) {
                    proc.destroyForcibly()
                    throw IllegalStateException("Чтение DTBO превысило лимит времени")
                }
                errorReader.join(1500)
                if (proc.exitValue() != 0)
                    throw IllegalStateException("dd завершился с кодом " + proc.exitValue() + ": " + errors.toString())
                if (copied != bytes || file.length() != bytes)
                    throw IllegalStateException("Неполный образ: " + copied + " из " + bytes + " байт")

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
                if (!hash1.equals(hash2, true)) throw IllegalStateException("Повторная проверка SHA-256 не совпала")

                runOnUiThread {
                    statusView.text = "DTBO скопирован: " + copied + " байт\nSHA-256: " + hash2 + "\nПодготовка Wi-Fi…"
                }
                startBackupHttpServer(file, hash2)
            } catch (e: Exception) {
                try { partial?.delete() } catch (_: Exception) { }
                runOnUiThread {
                    statusView.text = "Бэкап DTBO НЕ создан: " + (e.message ?: e.javaClass.simpleName) + ". Разделы ТВ не изменялись."
                }
            }
        }
    }

    private fun startBackupHttpServer(file: File, sha256: String) {
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
                    statusView.text = "БЭКАП DTBO ГОТОВ • " + file.length() + " байт\nSHA-256: " + sha256 +
                        "\n\nОткрой на телефоне в той же сети:\n" + url +
                        "\n\nОдноразовая ссылка, 5 минут. HTTP без шифрования — только доверенная сеть."
                }

                while (backupServer === server) {
                    val socket = server.accept()
                    var transferred = false
                    socket.use { client ->
                        client.soTimeout = 10000
                        val reader = client.getInputStream().bufferedReader(Charsets.ISO_8859_1)
                        val request = reader.readLine() ?: ""
                        while (true) {
                            val line = reader.readLine() ?: break
                            if (line.isEmpty()) break
                        }
                        val expected = "/download?token=" + token
                        if (!request.startsWith("GET " + expected + " HTTP/")) {
                            val body = "Forbidden".toByteArray(Charsets.UTF_8)
                            val out = client.getOutputStream()
                            out.write(("HTTP/1.1 403 Forbidden\r\nContent-Length: " + body.size +
                                "\r\nConnection: close\r\n\r\n").toByteArray(Charsets.US_ASCII))
                            out.write(body)
                            out.flush()
                        } else {
                            val out = client.getOutputStream()
                            val headers = "HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\n" +
                                "Content-Length: " + file.length() +
                                "\r\nContent-Disposition: attachment; filename=\"dtbo.img\"" +
                                "\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n"
                            out.write(headers.toByteArray(Charsets.US_ASCII))
                            java.io.FileInputStream(file).use { it.copyTo(out, 64 * 1024) }
                            out.flush()
                            runOnUiThread { statusView.text = "DTBO передан на телефон. SHA-256: " + sha256 + "\nСервер остановлен." }
                            transferred = true
                        }
                    }
                    if (transferred) break
                }
            } catch (e: Exception) {
                if (backupServer != null) runOnUiThread {
                    statusView.text = "Wi-Fi-передача остановлена: " + (e.message ?: e.javaClass.simpleName)
                }
            } finally {
                try { created?.close() } catch (_: Exception) { }
                if (backupServer === created) backupServer = null
            }
        }.start()
    }

    private fun stopBackupServer() {
        try { backupServer?.close() } catch (_: Exception) { }
        backupServer = null
        statusView.text = "Wi-Fi-сервер остановлен. Локальная копия остаётся в папке приложения."
    }

"""
anchor = "    private fun formatReport(j: JSONObject): String {"
if "private fun startDtboBackup()" not in s:
    if anchor not in s:
        raise SystemExit("Backup insertion anchor missing")
    s = s.replace(anchor, methods + anchor, 1)

on_destroy_old = """    override fun onDestroy() {
        super.onDestroy()
        executor.shutdownNow()
    }"""
on_destroy_new = """    override fun onDestroy() {
        try { backupServer?.close() } catch (_: Exception) { }
        backupServer = null
        super.onDestroy()
        executor.shutdownNow()
    }"""
if on_destroy_old in s:
    s = s.replace(on_destroy_old, on_destroy_new, 1)

m = manifest.read_text()
if "android.permission.INTERNET" not in m:
    marker = '<manifest xmlns:android="http://schemas.android.com/apk/res/android">'
    if marker not in m:
        raise SystemExit("Manifest anchor missing")
    m = m.replace(marker, marker + '\n    <uses-permission android:name="android.permission.INTERNET" />', 1)
manifest.write_text(m)

required = ['versionName = "1.0.0"', "versionCode = 100",
            '"appVersion", "1.0.0"', "private fun startDtboBackup()",
            "private fun startBackupHttpServer(", "private fun stopBackupServer()",
            "Повторная проверка SHA-256 не совпала"]
missing = [x for x in required if x not in g + s]
if missing:
    raise SystemExit("v1.0.0 verification failed: " + ", ".join(missing))
src.write_text(s)
print("v1.0.0 DTBO backup, SHA-256 verification and one-time LAN transfer patch applied")
