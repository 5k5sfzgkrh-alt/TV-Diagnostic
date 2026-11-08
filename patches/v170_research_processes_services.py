from pathlib import Path
import xml.etree.ElementTree as ET

root = Path("project")
main = root / "app/src/main/java/com/tvdiagnostic/hi3751/MainActivity.kt"
src = main.read_text(encoding="utf-8")

if "ProcessResearchActivity" not in src:
    anchor = 'import android.content.Context\n'
    if src.count(anchor) != 1:
        raise SystemExit("MainActivity import anchor mismatch")
    src = src.replace(anchor, anchor + 'import android.content.Intent\n', 1)
    anchor = '        outer.addView(buttons)\n'
    insert = '''        outer.addView(buttons)
        val researchRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        researchRow.addView(makeButton("Исследование процессов и служб") {
            startActivity(Intent(this, ProcessResearchActivity::class.java))
        })
        outer.addView(researchRow)
'''
    if src.count(anchor) != 1:
        raise SystemExit("MainActivity UI anchor mismatch")
    src = src.replace(anchor, insert, 1)
    src = src.replace("TV DIAGNOSTIC  •  Hi3751V553  •  1.6.2",
                      "TV DIAGNOSTIC  •  Hi3751V553  •  1.7.0", 1)
    main.write_text(src, encoding="utf-8")

activity = r'''package com.tvdiagnostic.hi3751

import android.app.Activity
import android.app.ActivityManager
import android.content.Context
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.concurrent.Executors

class ProcessResearchActivity : Activity() {
    private lateinit var output: TextView
    private lateinit var status: TextView
    private val worker = Executors.newSingleThreadExecutor()
    private val handler = Handler(Looper.getMainLooper())
    @Volatile private var active = true
    @Volatile private var lastProcesses = JSONArray()

    private val refreshTask = object : Runnable {
        override fun run() {
            if (!active) return
            refreshProcesses()
            handler.postDelayed(this, 4000L)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 18, 24, 18)
            setBackgroundColor(0xFF101820.toInt())
        }
        val title = TextView(this).apply {
            text = "ИССЛЕДОВАНИЕ ПРОЦЕССОВ И СЛУЖБ • 1.7.0"
            textSize = 22f
            setTextColor(0xFFFFFFFF.toInt())
        }
        status = TextView(this).apply {
            textSize = 14f
            setTextColor(0xFF80CBC4.toInt())
            setPadding(0, 8, 0, 12)
        }
        val actions = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        actions.addView(makeButton("Обновить") { refreshProcesses() })
        actions.addView(makeButton("Полный снимок JSON") { createSnapshot() })
        actions.addView(makeButton("Назад") { finish() })
        output = TextView(this).apply {
            textSize = 15f
            setTextColor(0xFFE8EEF2.toInt())
            setLineSpacing(4f, 1f)
            setPadding(0, 14, 0, 20)
            isFocusable = true
        }
        val scroll = ScrollView(this).apply { addView(output) }
        root.addView(title)
        root.addView(status)
        root.addView(actions)
        root.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(root)
        refreshProcesses()
        handler.postDelayed(refreshTask, 4000L)
    }

    private fun makeButton(label: String, action: () -> Unit) =
        Button(this).apply {
            text = label
            textSize = 13f
            isFocusable = true
            setOnClickListener { action() }
        }

    private fun refreshProcesses() {
        status.text = "Обновление списка процессов…"
        worker.execute {
            val rootResult = runRoot("ps -A -o PID,PPID,USER,NAME", 7000L, 50000)
            val lines = rootResult.first.lineSequence().filter { it.isNotBlank() }.toList()
            val rootAvailable = rootResult.second && lines.size > 1
            val rows = JSONArray()
            if (rootAvailable) {
                for (line in lines.drop(1)) {
                    val m = Regex("^\\s*(\\d+)\\s+(\\d+)\\s+(\\S+)\\s+(.+?)\\s*$").find(line)
                    if (m != null) rows.put(JSONObject()
                        .put("pid", m.groupValues[1].toIntOrNull() ?: -1)
                        .put("ppid", m.groupValues[2].toIntOrNull() ?: -1)
                        .put("user", m.groupValues[3])
                        .put("name", m.groupValues[4]))
                }
            } else {
                val am = getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
                am.runningAppProcesses?.forEach { p ->
                    rows.put(JSONObject().put("pid", p.pid).put("ppid", JSONObject.NULL)
                        .put("user", "app-visible").put("name", p.processName))
                }
            }
            lastProcesses = rows
            val shown = buildString {
                appendLine("РЕЖИМ: " + if (rootAvailable) "ROOT — полный список ps" else "без root — только видимые приложению процессы")
                appendLine("Процессов: @@{rows.length()}")
                appendLine("Обновление: каждые 4 секунды")
                appendLine()
                appendLine("PID      PPID     USER           PROCESS")
                for (i in 0 until minOf(rows.length(), 90)) {
                    val p = rows.optJSONObject(i) ?: continue
                    appendLine(String.format("%-8s %-8s %-14s %s",
                        p.opt("pid"), p.opt("ppid"), p.optString("user"), p.optString("name")))
                }
                if (rows.length() > 90) appendLine("… ещё @@{rows.length() - 90} процессов в JSON-снимке")
                appendLine()
                appendLine("Без root список процессов может быть неполным.")
                appendLine("Службы, HAL, модули и свойства системы собираются отдельным полным снимком.")
                appendLine("Режим только чтение: процессы не останавливаются и не изменяются.")
            }
            runOnUiThread {
                output.text = shown
                status.text = "Live-монитор • @@{if (rootAvailable) "root доступен" else "ограниченный доступ"} • @@{System.currentTimeMillis()}"
            }
        }
    }

    private fun createSnapshot() {
        status.text = "Сбор полного снимка процессов, служб, HAL и ядра…"
        worker.execute {
            val ps = runRoot("ps -A -o PID,PPID,USER,NAME", 9000L, 60000)
            val activity = runRoot("dumpsys activity services", 12000L, 50000)
            val serviceList = runRoot("service list", 8000L, 20000)
            val hwServices = runRoot("lshal", 8000L, 30000)
            val modules = readFile("/proc/modules", 24000)
            val partitions = readFile("/proc/partitions", 12000)
            val mounts = readFile("/proc/mounts", 20000)
            val cmdline = readFile("/proc/cmdline", 6000)
            val kernel = readFile("/proc/version", 3000)
            val meminfo = readFile("/proc/meminfo", 10000)
            val properties = runRoot("getprop", 10000L, 30000)
            val thermal = runRoot("for d in /sys/class/thermal/thermal_zone*; do [ -d \\"$d\\" ] || continue; echo \\"[$d]\\"; cat \\"$d/type\\" 2>/dev/null; cat \\"$d/temp\\" 2>/dev/null; done", 7000L, 12000)
            val wifi = runRoot("dumpsys wifi", 10000L, 20000)
            val bluetooth = runRoot("dumpsys bluetooth_manager", 10000L, 12000)
            val media = runRoot("dumpsys media.codec", 10000L, 16000)

            val snapshot = JSONObject()
                .put("schema", "tv-diagnostic-research-1")
                .put("appVersion", "1.7.0")
                .put("timestamp", System.currentTimeMillis())
                .put("device", JSONObject()
                    .put("manufacturer", android.os.Build.MANUFACTURER)
                    .put("brand", android.os.Build.BRAND)
                    .put("model", android.os.Build.MODEL)
                    .put("device", android.os.Build.DEVICE)
                    .put("board", android.os.Build.BOARD)
                    .put("product", android.os.Build.PRODUCT)
                    .put("android", android.os.Build.VERSION.RELEASE)
                    .put("sdk", android.os.Build.VERSION.SDK_INT)
                    .put("fingerprint", android.os.Build.FINGERPRINT))
                .put("rootPs", JSONObject().put("available", ps.second).put("output", ps.first))
                .put("runningProcesses", lastProcesses)
                .put("activityServices", activity.first)
                .put("binderServices", serviceList.first)
                .put("hardwareServicesLshal", hwServices.first)
                .put("kernelModules", modules)
                .put("partitions", partitions)
                .put("mounts", mounts)
                .put("kernelCmdline", cmdline)
                .put("kernelVersion", kernel)
                .put("memoryInfo", meminfo)
                .put("systemProperties", properties.first)
                .put("thermalZones", thermal.first)
                .put("wifiDumpsys", wifi.first)
                .put("bluetoothDumpsys", bluetooth.first)
                .put("mediaCodecDumpsys", media.first)
                .put("access", JSONObject()
                    .put("rootPs", ps.second)
                    .put("activityServices", activity.second)
                    .put("binderServices", serviceList.second)
                    .put("lshal", hwServices.second)
                    .put("properties", properties.second))
                .put("safety", JSONObject()
                    .put("readOnly", true)
                    .put("blockDeviceContentsRead", false)
                    .put("partitionWrites", false)
                    .put("servicesStopped", false)
                    .put("modulesChanged", false))

            val dir = File(filesDir, "backups")
            val saved = try {
                if (!dir.exists() && !dir.mkdirs()) throw IllegalStateException("Не удалось создать каталог отчётов")
                val file = File(dir, "research-snapshot-@@{System.currentTimeMillis()}.json")
                file.writeText(snapshot.toString(2), Charsets.UTF_8)
                file
            } catch (_: Exception) { null }

            runOnUiThread {
                if (saved != null) {
                    status.text = "Снимок сохранён: @@{saved.name} • @@{saved.length()} байт"
                    output.text = "ПОЛНЫЙ ТЕХНИЧЕСКИЙ СНИМОК СОЗДАН\\n\\n" +
                        "Файл: @@{saved.absolutePath}\\n" +
                        "Размер: @@{saved.length()} байт\\n" +
                        "Процессы: @@{lastProcesses.length()}\\n" +
                        "Собраны: свойства, службы Android, Binder, HAL (lshal), модули ядра, разделы, mounts, память, температура, Wi-Fi, Bluetooth и media codec.\\n\\n" +
                        "Файл находится в приватном каталоге приложения backups и доступен для передачи через LAN-сервер 1.6.2.\\n" +
                        "Данные блочных устройств не читались; запись, остановка служб и изменение модулей не выполнялись."
                } else {
                    status.text = "Не удалось сохранить JSON-снимок"
                    output.text = snapshot.toString(2)
                }
            }
        }
    }

    private fun readFile(path: String, limit: Int): String = try {
        File(path).takeIf { it.canRead() }?.inputStream()?.bufferedReader()?.use { it.readText().take(limit) }
            ?: "unavailable"
    } catch (e: Exception) { "unavailable: @@{e.javaClass.simpleName}" }

    private fun runRoot(command: String, timeoutMs: Long, limit: Int): Pair<String, Boolean> {
        var process: Process? = null
        return try {
            process = ProcessBuilder("su", "-c", command).redirectErrorStream(true).start()
            val finished = process.waitFor(timeoutMs, java.util.concurrent.TimeUnit.MILLISECONDS)
            if (!finished) process.destroyForcibly()
            val text = process.inputStream.bufferedReader().use { it.readText().take(limit) }
            Pair(text, finished && process.exitValue() == 0)
        } catch (e: Exception) {
            try { process?.destroyForcibly() } catch (_: Exception) {}
            Pair("unavailable: @@{e.javaClass.simpleName}: @@{e.message ?: ""}", false)
        }
    }

    override fun onDestroy() {
        active = false
        handler.removeCallbacksAndMessages(null)
        worker.shutdownNow()
        super.onDestroy()
    }
}
'''.replace("@@{", "\${")

activity_path = root / "app/src/main/java/com/tvdiagnostic/hi3751/ProcessResearchActivity.kt"
activity_path.write_text(activity, encoding="utf-8")

gradle = root / "app/build.gradle.kts"
g = gradle.read_text(encoding="utf-8")
for old, new in [('versionCode = 162','versionCode = 170'), ('versionName = "1.6.2"','versionName = "1.7.0"')]:
    if g.count(old) != 1:
        raise SystemExit("Gradle version anchor mismatch: " + old)
    g = g.replace(old, new, 1)
gradle.write_text(g, encoding="utf-8")

manifest = root / "app/src/main/AndroidManifest.xml"
ET.register_namespace("android", "http://schemas.android.com/apk/res/android")
tree = ET.parse(manifest)
app = tree.getroot().find("application")
if app is None:
    raise SystemExit("No application element in manifest")
app.set("{http://schemas.android.com/apk/res/android}label", "TV Diagnostic 1.7.0")
if not any(a.get("{http://schemas.android.com/apk/res/android}name") == ".ProcessResearchActivity"
           for a in app.findall("activity")):
    node = ET.SubElement(app, "activity")
    node.set("{http://schemas.android.com/apk/res/android}name", ".ProcessResearchActivity")
    node.set("{http://schemas.android.com/apk/res/android}exported", "false")
tree.write(manifest, encoding="utf-8", xml_declaration=True)

if "Исследование процессов и служб" not in main.read_text(encoding="utf-8"):
    raise SystemExit("Research entry point missing")
if "tv-diagnostic-research-1" not in activity_path.read_text(encoding="utf-8"):
    raise SystemExit("Snapshot schema missing")
print("v1.7.0 research patch applied: live process monitor, read-only service/HAL/kernel snapshot, app-private JSON export.")
