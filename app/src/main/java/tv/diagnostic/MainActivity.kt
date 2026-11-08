package tv.diagnostic

import android.app.Activity
import android.app.ActivityManager
import android.os.Build
import android.os.Bundle
import android.os.Debug
import android.os.Environment
import android.os.StatFs
import android.content.pm.PackageManager
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

class MainActivity : Activity() {
    private lateinit var output: TextView
    private var lastReport = JSONObject()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 24, 24, 24)
        }
        val title = TextView(this).apply {
            text = "TV Diagnostic 2.0 — только чтение"
            textSize = 22f
        }
        val scan = Button(this).apply {
            text = "Сканировать систему"
            setOnClickListener { scanSystem() }
        }
        val export = Button(this).apply {
            text = "Экспорт JSON"
            setOnClickListener { shareReport() }
        }
        output = TextView(this).apply { textSize = 14f; setTextIsSelectable(true) }
        root.addView(title)
        root.addView(scan)
        root.addView(export)
        val scroll = ScrollView(this).apply { addView(output) }
        root.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(root)
        scanSystem()
    }

    private fun readProp(name: String): String =
        try { File("/system/build.prop").readLines().firstOrNull { it.startsWith("$name=") }?.substringAfter("=") ?: "недоступно" }
        catch (_: Exception) { "недоступно" }

    private fun scanSystem() {
        val report = JSONObject()
        val device = JSONObject()
        device.put("manufacturer", Build.MANUFACTURER)
        device.put("model", Build.MODEL)
        device.put("device", Build.DEVICE)
        device.put("product", Build.PRODUCT)
        device.put("hardware", Build.HARDWARE)
        device.put("board", Build.BOARD)
        device.put("fingerprint", Build.FINGERPRINT)
        device.put("android", Build.VERSION.RELEASE)
        device.put("sdk", Build.VERSION.SDK_INT)
        device.put("build_display", Build.DISPLAY)
        device.put("ro_board_platform", readProp("ro.board.platform"))
        device.put("ro_boot_hardware", readProp("ro.boot.hardware"))
        report.put("device", device)

        val mem = ActivityManager.MemoryInfo()
        (getSystemService(ACTIVITY_SERVICE) as ActivityManager).getMemoryInfo(mem)
        val memory = JSONObject()
        memory.put("total_bytes", mem.totalMem)
        memory.put("available_bytes", mem.availMem)
        memory.put("low_memory", mem.lowMemory)
        report.put("memory", memory)

        val storage = JSONObject()
        try {
            val stat = StatFs(Environment.getDataDirectory().absolutePath)
            storage.put("data_total_bytes", stat.totalBytes)
            storage.put("data_available_bytes", stat.availableBytes)
        } catch (_: Exception) { }
        report.put("storage", storage)

        val packages = JSONArray()
        val pm = packageManager
        val apps = try {
            getInstalledApps(pm)
        } catch (_: Exception) { emptyList() }
        for (app in apps.sortedBy { it.packageName }) {
            val item = JSONObject()
            item.put("package", app.packageName)
            item.put("system", (app.flags and android.content.pm.ApplicationInfo.FLAG_SYSTEM) != 0)
            item.put("enabled", app.enabled)
            item.put("source_dir", app.sourceDir)
            packages.put(item)
        }
        report.put("packages", packages)

        val processes = JSONArray()
        val running = (getSystemService(ACTIVITY_SERVICE) as ActivityManager).runningAppProcesses ?: emptyList()
        for (p in running) {
            val item = JSONObject()
            item.put("pid", p.pid)
            item.put("process", p.processName)
            item.put("importance", p.importance)
            processes.put(item)
        }
        report.put("visible_processes", processes)
        report.put("safety", JSONObject()
            .put("mode", "READ_ONLY")
            .put("disable_actions", false)
            .put("partition_write_actions", false)
            .put("note", "Android limits visibility of processes and services for ordinary apps; absence is not proof of absence."))

        lastReport = report
        output.text = buildString {
            appendLine("Устройство: ${Build.MANUFACTURER} ${Build.MODEL}")
            appendLine("Board: ${Build.BOARD} | Hardware: ${Build.HARDWARE}")
            appendLine("Android: ${Build.VERSION.RELEASE} (SDK ${Build.VERSION.SDK_INT})")
            appendLine("Build: ${Build.FINGERPRINT}")
            appendLine("RAM: ${mem.totalMem / 1024 / 1024} MiB; свободно: ${mem.availMem / 1024 / 1024} MiB")
            appendLine("Установлено пакетов: ${packages.length()}")
            appendLine("Видимых процессов: ${processes.length()}")
            appendLine()
            appendLine("Ограничения: это снимок доступных приложению данных, не полный список процессов/HAL/init.")
            appendLine("Автоматическое отключение компонентов отсутствует.")
        }
    }

    @Suppress("DEPRECATION")
    private fun getInstalledApps(pm: PackageManager): List<android.content.pm.ApplicationInfo> {
        return if (Build.VERSION.SDK_INT >= 33) pm.getInstalledApplications(PackageManager.ApplicationInfoFlags.of(0)) else pm.getInstalledApplications(0)
    }

    private fun shareReport() {
        val intent = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
            type = "application/json"
            putExtra(android.content.Intent.EXTRA_SUBJECT, "TV Diagnostic 2.0 report")
            putExtra(android.content.Intent.EXTRA_TEXT, lastReport.toString(2))
        }
        startActivity(android.content.Intent.createChooser(intent, "Передать отчёт"))
    }
}
