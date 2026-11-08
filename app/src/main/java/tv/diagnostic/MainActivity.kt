package tv.diagnostic

import android.app.Activity
import android.app.ActivityManager
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.os.StatFs
import android.view.Gravity
import android.widget.Button
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.google.zxing.BarcodeFormat
import com.google.zxing.qrcode.QRCodeWriter
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.Inet4Address
import java.net.NetworkInterface
import java.net.ServerSocket
import java.security.SecureRandom
import java.util.Collections
import java.util.UUID
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

class MainActivity : Activity() {
    private lateinit var output: TextView
    private lateinit var qrImage: ImageView
    private var lastReport = JSONObject()
    @Volatile private var server: ServerSocket? = null
    @Volatile private var serverRunning = false
    private val io = Executors.newSingleThreadExecutor()
    private var transferInfo: TextView? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(20, 18, 20, 18) }
        root.addView(TextView(this).apply { text = "TV Diagnostic 2.0 • CS2352P687"; textSize = 22f })
        root.addView(Button(this).apply { text = "Базовое сканирование"; setOnClickListener { scanBasic() } })
        root.addView(Button(this).apply { text = "Расширенный аудит (ROOT, только чтение)"; setOnClickListener { scanRoot() } })
        root.addView(Button(this).apply { text = "Передать отчёт: QR / Wi-Fi"; setOnClickListener { startTransfer() } })
        root.addView(Button(this).apply { text = "Остановить Wi-Fi передачу"; setOnClickListener { stopTransfer(); transferInfo?.text = "Передача остановлена" } })
        root.addView(Button(this).apply { text = "Экспорт JSON"; setOnClickListener { shareReport() } })
        qrImage = ImageView(this).apply { adjustViewBounds = true; visibility = android.view.View.GONE; scaleType = ImageView.ScaleType.FIT_CENTER }
        root.addView(qrImage, LinearLayout.LayoutParams(240, 240).apply { gravity = Gravity.CENTER })
        transferInfo = TextView(this).apply { textSize = 13f }
        root.addView(transferInfo)
        output = TextView(this).apply { textSize = 13f; setTextIsSelectable(true) }
        root.addView(ScrollView(this).apply { addView(output) }, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(root)
        scanBasic()
    }

    private fun scanBasic() {
        val report = JSONObject()
        val d = JSONObject()
        d.put("manufacturer", Build.MANUFACTURER); d.put("model", Build.MODEL)
        d.put("device", Build.DEVICE); d.put("product", Build.PRODUCT)
        d.put("hardware", Build.HARDWARE); d.put("board", Build.BOARD)
        d.put("fingerprint", Build.FINGERPRINT); d.put("android_release", Build.VERSION.RELEASE)
        d.put("sdk", Build.VERSION.SDK_INT); d.put("build_display", Build.DISPLAY)
        d.put("supported_abis", JSONArray(Build.SUPPORTED_ABIS.toList()))
        report.put("device", d)
        val mem = ActivityManager.MemoryInfo()
        (getSystemService(ACTIVITY_SERVICE) as ActivityManager).getMemoryInfo(mem)
        report.put("memory", JSONObject().put("total_bytes", mem.totalMem).put("available_bytes", mem.availMem).put("low_memory", mem.lowMemory))
        val stat = StatFs(Environment.getDataDirectory().absolutePath)
        report.put("data_storage", JSONObject().put("total_bytes", stat.totalBytes).put("available_bytes", stat.availableBytes))
        val props = JSONObject()
        listOf("ro.product.", "ro.build.", "ro.boot.", "ro.vendor.", "ro.hardware", "ro.board.platform", "ro.soc.").forEach { prefix ->
            props.put(prefix, "Будут собраны расширенным root-аудитом")
        }
        report.put("property_groups", props)
        val apps = JSONArray()
        @Suppress("DEPRECATION")
        val installed = packageManager.getInstalledApplications(PackageManager.GET_META_DATA)
        installed.sortedBy { it.packageName }.forEach { ai ->
            val item = JSONObject().put("package", ai.packageName)
                .put("system", (ai.flags and android.content.pm.ApplicationInfo.FLAG_SYSTEM) != 0)
                .put("enabled", ai.enabled).put("source_dir", ai.sourceDir)
            try {
                @Suppress("DEPRECATION")
                val pi = packageManager.getPackageInfo(ai.packageName,
                    PackageManager.GET_PERMISSIONS or PackageManager.GET_SERVICES or PackageManager.GET_RECEIVERS or PackageManager.GET_PROVIDERS)
                item.put("requested_permissions", JSONArray(pi.requestedPermissions?.toList() ?: emptyList<String>()))
                item.put("service_count", pi.services?.size ?: 0)
                item.put("receiver_count", pi.receivers?.size ?: 0)
                item.put("provider_count", pi.providers?.size ?: 0)
            } catch (_: Exception) { item.put("component_metadata", "недоступно") }
            apps.put(item)
        }
        report.put("packages", apps)
        val visible = JSONArray()
        val running = (getSystemService(ACTIVITY_SERVICE) as ActivityManager).runningAppProcesses ?: emptyList()
        running.forEach { visible.put(JSONObject().put("pid", it.pid).put("process", it.processName).put("importance", it.importance)) }
        report.put("visible_processes", visible)
        report.put("safety", safetyBlock())
        lastReport = report
        renderSummary("Базовый аудит завершён", "Пакетов: ${apps.length()}; видимых процессов: ${visible.length()}. Для полного системного снимка запусти ROOT-аудит.")
    }

    private fun safetyBlock() = JSONObject()
        .put("mode", "READ_ONLY")
        .put("package_disable_or_uninstall", false)
        .put("partition_write_or_flash", false)
        .put("classification_policy", "GREEN запрещён без подтверждённого графа зависимостей и тестов; по умолчанию YELLOW/GRAY/RED")
        .put("note", "Отсутствие компонента в доступном снимке не доказывает его отсутствие.")

    private fun scanRoot() {
        renderSummary("Выполняется ROOT-аудит…", "Команды чтения фиксированы; записи в системные разделы не выполняются.")
        io.execute {
            val script = """
echo '=== ROOT_ID ==='; id
echo '=== GETPROP ==='; getprop
echo '=== CPUINFO ==='; cat /proc/cpuinfo
echo '=== MEMINFO ==='; cat /proc/meminfo
echo '=== PARTITIONS ==='; cat /proc/partitions
echo '=== MOUNTS ==='; cat /proc/mounts
echo '=== MODULES ==='; cat /proc/modules
echo '=== CMDLINE ==='; cat /proc/cmdline
echo '=== DT_MODEL ==='; cat /sys/firmware/devicetree/base/model 2>/dev/null
echo '=== DT_COMPATIBLE ==='; cat /sys/firmware/devicetree/base/compatible 2>/dev/null
echo '=== BLOCK_BY_NAME ==='; ls -l /dev/block/by-name 2>/dev/null
echo '=== BLOCK_MMС ==='; ls -l /dev/block/mmc* 2>/dev/null
echo '=== WIFI_SYSFS ==='; ls -l /sys/class/net 2>/dev/null
echo '=== WLAN_MODULES ==='; ls -l /sys/module 2>/dev/null
echo '=== DRM ==='; ls -R /sys/class/drm 2>/dev/null
echo '=== FRAMEBUFFER ==='; cat /sys/class/graphics/fb0/virtual_size 2>/dev/null; cat /sys/class/graphics/fb0/bits_per_pixel 2>/dev/null
echo '=== FSTAB ==='; for f in /vendor/etc/fstab* /odm/etc/fstab*; do [ -f "$f" ] && echo "--- $f" && cat "$f"; done
echo '=== VINTF_VENDOR ==='; cat /vendor/etc/vintf/manifest.xml 2>/dev/null
echo '=== VINTF_SYSTEM ==='; cat /system/etc/vintf/manifest.xml 2>/dev/null
echo '=== INIT_LIST ==='; ls -l /vendor/etc/init /vendor/etc/init/hw /system/etc/init 2>/dev/null
echo '=== INIT_BIGFISH ==='; cat /vendor/etc/init/hw/init.bigfish.rc 2>/dev/null
echo '=== BUILD_PROPS ==='; for f in /system/build.prop /vendor/build.prop /system/product/etc/build.prop /system_ext/build.prop; do [ -f "$f" ] && echo "--- $f" && cat "$f"; done
echo '=== WIFI_DRIVER ==='; dmesg 2>/dev/null | grep -iE 'wlan|wifi|bluetooth|firmware|panel|tcon|mali|hisilicon' | tail -n 250
""".trimIndent()
            val result = runRootReadOnly(script)
            runOnUiThread {
                val rootObj = JSONObject().put("available", result.first).put("output", result.second)
                lastReport.put("root_audit", rootObj)
                lastReport.put("safety", safetyBlock())
                renderSummary(if (result.first) "ROOT-аудит завершён" else "ROOT-аудит недоступен",
                    if (result.first) "Собран расширенный снимок свойств, CPU, памяти, разделов, модулей, DT, fstab, HAL/init и журналов." else result.second)
            }
        }
    }

    private fun runRootReadOnly(script: String): Pair<Boolean, String> {
        return try {
            val p = ProcessBuilder("su", "-c", script).redirectErrorStream(true).start()
            val done = p.waitFor(25, TimeUnit.SECONDS)
            if (!done) { p.destroyForcibly(); false to "Тайм-аут ROOT-команды (25 секунд)." }
            else {
                val text = p.inputStream.bufferedReader().use { it.readText() }.take(1_500_000)
                (p.exitValue() == 0) to text
            }
        } catch (e: Exception) { false to "ROOT недоступен: ${e.javaClass.simpleName}: ${e.message}" }
    }

    private fun renderSummary(title: String, detail: String) = runOnUiThread {
        output.text = "$title\n\n$detail\n\nУстройство: ${Build.DEVICE} / ${Build.HARDWARE}\nAndroid ${Build.VERSION.RELEASE} • ${Build.FINGERPRINT}\n\nРежим: ТОЛЬКО ЧТЕНИЕ. Функций отключения, удаления и прошивки нет."
    }

    private fun wifiIp(): String? {
        try {
            val wm = applicationContext.getSystemService(WIFI_SERVICE) as WifiManager
            val ip = wm.connectionInfo.ipAddress
            if (ip != 0) return listOf(ip and 255, ip shr 8 and 255, ip shr 16 and 255, ip shr 24 and 255).joinToString(".")
        } catch (_: Exception) { }
        return try {
            Collections.list(NetworkInterface.getNetworkInterfaces()).flatMap { Collections.list(it.inetAddresses) }
                .firstOrNull { !it.isLoopbackAddress && it is Inet4Address }?.hostAddress
        } catch (_: Exception) { null }
    }

    private fun startTransfer() {
        if (serverRunning) { transferInfo?.text = "Сервер уже запущен"; return }
        val ip = wifiIp()
        if (ip == null) { transferInfo?.text = "Не удалось определить IP. Подключи ТВ к Wi-Fi или Ethernet."; return }
        val token = UUID.randomUUID().toString().replace("-", "")
        io.execute {
            try {
                val socket = ServerSocket(0)
                server = socket; serverRunning = true
                val url = "http://$ip:${socket.localPort}/report?token=$token"
                val matrix = QRCodeWriter().encode(url, BarcodeFormat.QR_CODE, 420, 420)
                val bitmap = Bitmap.createBitmap(420, 420, Bitmap.Config.RGB_565)
                for (x in 0 until 420) for (y in 0 until 420) bitmap.setPixel(x, y, if (matrix[x, y]) android.graphics.Color.BLACK else android.graphics.Color.WHITE)
                runOnUiThread {
                    qrImage.setImageBitmap(bitmap); qrImage.visibility = android.view.View.VISIBLE
                    transferInfo?.text = "Отсканируй QR телефоном в той же сети Wi-Fi.\n$url\nТокен одноразовый; останови сервер после скачивания."
                }
                while (serverRunning) {
                    val client = socket.accept()
                    client.soTimeout = 5000
                    val reader = BufferedReader(InputStreamReader(client.getInputStream()))
                    val request = reader.readLine() ?: ""
                    while (reader.readLine()?.isNotEmpty() == true) { }
                    val valid = request.startsWith("GET /report?token=$token ")
                    val body = if (valid) lastReport.toString(2).toByteArray(Charsets.UTF_8) else "Unauthorized".toByteArray()
                    val status = if (valid) "200 OK" else "403 Forbidden"
                    val out = client.getOutputStream()
                    out.write("HTTP/1.1 $status\r\nContent-Type: ${if (valid) "application/json; charset=utf-8" else "text/plain"}\r\nContent-Length: ${body.size}\r\nContent-Disposition: attachment; filename=\"tv-diagnostic-report.json\"\r\nConnection: close\r\n\r\n".toByteArray(Charsets.US_ASCII))
                    out.write(body); out.flush(); client.close()
                }
            } catch (e: Exception) {
                runOnUiThread { transferInfo?.text = "Передача завершена: ${e.message ?: "сервер остановлен"}" }
            } finally { serverRunning = false; try { server?.close() } catch (_: Exception) { }; server = null }
        }
    }

    private fun stopTransfer() {
        serverRunning = false
        try { server?.close() } catch (_: Exception) { }
        server = null
        qrImage.visibility = android.view.View.GONE
    }

    private fun shareReport() {
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "application/json"
            putExtra(Intent.EXTRA_SUBJECT, "TV Diagnostic report")
            putExtra(Intent.EXTRA_TEXT, lastReport.toString(2))
        }
        startActivity(Intent.createChooser(intent, "Передать отчёт"))
    }

    override fun onDestroy() { stopTransfer(); io.shutdownNow(); super.onDestroy() }
}
