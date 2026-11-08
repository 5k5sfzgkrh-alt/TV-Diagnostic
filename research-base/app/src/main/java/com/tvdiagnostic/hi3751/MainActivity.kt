package com.tvdiagnostic.hi3751

import android.app.Activity
import android.app.ActivityManager
import android.content.pm.PackageManager
import android.os.Process
import android.content.Context
import android.opengl.GLSurfaceView
import android.media.MediaCodecList
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.os.StatFs
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.Locale
import java.util.concurrent.Executors
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10

class MainActivity : Activity() {
    private lateinit var reportView: TextView
    private lateinit var statusView: TextView
    private var gpuInfo = "GPU: данные OpenGL ещё не получены"
    private val executor = Executors.newSingleThreadExecutor()
    private var lastReport = JSONObject()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        buildUi()
        collectGpuInfo()
        refreshReport()
    }

    private fun buildUi() {
        val outer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(28, 22, 28, 22)
            setBackgroundColor(0xFF101820.toInt())
        }
        val title = TextView(this).apply {
            text = "TV DIAGNOSTIC  •  Hi3751V553  •  1.3.3"
            textSize = 23f
            setTextColor(0xFFFFFFFF.toInt())
        }
        statusView = TextView(this).apply {
            text = "Инициализация диагностики…"
            textSize = 15f
            setTextColor(0xFF80CBC4.toInt())
            setPadding(0, 8, 0, 14)
        }
        val buttons = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val refresh = makeButton("Обновить") { refreshReport() }
        val root = makeButton("Проверить Root") { checkRoot() }
        val export = makeButton("Экспорт JSON") { exportReport() }
        val share = makeButton("Поделиться отчётом") { shareReport() }
        buttons.addView(refresh)
        buttons.addView(root)
        buttons.addView(export)
        buttons.addView(share)
        reportView = TextView(this).apply {
            textSize = 16f
            setTextColor(0xFFE8EEF2.toInt())
            setLineSpacing(5f, 1.0f)
            setPadding(0, 16, 0, 24)
            isFocusable = true
        }
        val scroll = ScrollView(this).apply { addView(reportView) }
        outer.addView(title)
        outer.addView(statusView)
        outer.addView(buttons)
        val backupButtons = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        backupButtons.addView(makeButton("Создать бэкап DTBO") { confirmDtboBackup() })
        backupButtons.addView(makeButton("Остановить Wi-Fi") { stopBackupServer() })
        backupButtons.addView(makeButton("Бэкап BOOT + RECOVERY") { confirmSystemBackup() })
        outer.addView(backupButtons)
        val systemBackupButtons = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        systemBackupButtons.addView(makeButton("Бэкап SYSTEM + VENDOR") { confirmSystemVendorBackup() })
        systemBackupButtons.addView(makeButton("Найти бэкап 1.3.0") { findLegacySystemVendorBackups() })
        outer.addView(systemBackupButtons)
        outer.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(outer)
        refresh.requestFocus()
    }

    private fun makeButton(label: String, action: () -> Unit): Button =
        Button(this).apply {
            text = label
            isFocusable = true
            textSize = 13f
            setOnClickListener { action() }
        }

    private fun collectGpuInfo() {
        val glView = GLSurfaceView(this)
        glView.setEGLContextClientVersion(2)
        glView.setRenderer(object : GLSurfaceView.Renderer {
            override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
                val vendor = gl?.glGetString(GL10.GL_VENDOR) ?: "неизвестно"
                val renderer = gl?.glGetString(GL10.GL_RENDERER) ?: "неизвестно"
                val version = gl?.glGetString(GL10.GL_VERSION) ?: "неизвестно"
                runOnUiThread {
                    gpuInfo = "GPU Vendor: $vendor\nGPU Renderer: $renderer\nOpenGL ES: $version"
                    if (::reportView.isInitialized) refreshReport()
                }
            }
            override fun onSurfaceChanged(gl: GL10?, width: Int, height: Int) {}
            override fun onDrawFrame(gl: GL10?) {}
        })
        addContentView(glView, android.widget.FrameLayout.LayoutParams(1, 1, Gravity.TOP or Gravity.START))
    }

    private fun refreshReport() {
        statusView.text = "Сбор показателей CPU, RAM, температуры и ZRAM…"
        executor.execute {
            val report = collectBasicReport()
            lastReport = report
            runOnUiThread {
                reportView.text = formatReport(report)
                statusView.text = "Обычный режим • только чтение • без изменений системы"
            }
        }
    }

    private fun collectBasicReport(): JSONObject {
        val j = JSONObject()
        j.put("timestamp", System.currentTimeMillis())
        j.put("appVersion", "1.3.0")
        j.put("deviceTreeInfo", collectDeviceTreeInfo())
        j.put("kernelInfo", collectKernelInfo())
        j.put("driverInfo", collectDriverInfo())
        j.put("manufacturer", Build.MANUFACTURER)
        j.put("brand", Build.BRAND)
        j.put("model", Build.MODEL)
        j.put("device", Build.DEVICE)
        j.put("board", Build.BOARD)
        j.put("product", Build.PRODUCT)
        j.put("android", Build.VERSION.RELEASE)
        j.put("sdk", Build.VERSION.SDK_INT)
        j.put("fingerprint", Build.FINGERPRINT)
        j.put("kernel", readText("/proc/version"))
        j.put("cpuinfo", readText("/proc/cpuinfo", 12000))
        j.put("meminfo", readText("/proc/meminfo", 6000))
        j.put("swaps", readText("/proc/swaps", 3000))
        j.put("uptime", readText("/proc/uptime", 1000))
        j.put("partitionInfo", collectPartitionInfo())
        j.put("bootInfo", collectBootInfo())
        j.put("securityInfo", collectSecurityInfo())
        j.put("recoveryInfo", collectRecoveryInfo())
        j.put("accessInfo", collectAccessInfo())
        j.put("backupInstallAssessment", collectBackupInstallAssessment())
        j.put("extendedDiagnostics", collectExtendedDiagnostics())
        j.put("rootBlockReadProbe", collectRootBlockReadProbe())
        j.put("gpu", gpuInfo)
        j.put("mediaCodecs", collectMediaCodecs())

        val am = getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val mi = ActivityManager.MemoryInfo()
        am.getMemoryInfo(mi)
        j.put("ramTotalBytes", mi.totalMem)
        j.put("ramAvailableBytes", mi.availMem)
        j.put("lowMemory", mi.lowMemory)

        val stat = StatFs(Environment.getDataDirectory().absolutePath)
        j.put("dataTotalBytes", stat.totalBytes)
        j.put("dataAvailableBytes", stat.availableBytes)
        j.put("display", "${resources.displayMetrics.widthPixels}x${resources.displayMetrics.heightPixels}")
        j.put("densityDpi", resources.displayMetrics.densityDpi)

        j.put("cpuFrequencies", collectCpuFrequencies())
        j.put("cpuGovernor", collectCpuGovernor())
        j.put("cpuLoadPercent", collectCpuLoad())
        j.put("temperatures", collectTemperatures())
        j.put("zram", collectZram())
        j.put("runningProcesses", collectRunningProcesses())
        j.put("installedPackages", collectInstalledPackages())
        j.put("rootStatus", "not_checked")
        return j
    }


    private fun collectPartitionInfoV040(): JSONObject = JSONObject().apply {
        put("procPartitions", readText("/proc/partitions", 12000))
        put("mounts", readText("/proc/mounts", 12000))
        val devices = JSONArray()
        File("/sys/block").listFiles()?.sortedBy { it.name }?.forEach { devices.put(it.name) }
        put("blockDevices", devices)
        put("note", "Доступные блочные устройства и точки монтирования; не полный дамп таблицы разделов")
    }


    // Read-only inventory. No block device contents are opened or modified.
    private fun collectPartitionInfo(): JSONObject = JSONObject().apply {
        put("procPartitions", readText("/proc/partitions", 16000))
        put("mounts", readText("/proc/mounts", 16000))
        put("fstab", readText("/vendor/etc/fstab", 12000))
        put("fstabDevice", readText("/odm/etc/fstab", 8000))
        val devices = JSONArray()
        File("/sys/block").listFiles()?.sortedBy { it.name }?.forEach { device ->
            devices.put(JSONObject().apply {
                put("name", device.name)
                put("sectors512", readNumber("${device.absolutePath}/size") ?: JSONObject.NULL)
                put("readOnly", readNumber("${device.absolutePath}/ro") ?: JSONObject.NULL)
                put("removable", readNumber("${device.absolutePath}/removable") ?: JSONObject.NULL)
                put("logicalBlockSize", readNumber("${device.absolutePath}/queue/logical_block_size") ?: JSONObject.NULL)
                put("physicalBlockSize", readNumber("${device.absolutePath}/queue/physical_block_size") ?: JSONObject.NULL)
            })
        }
        put("blockDevices", devices)
        val byName = JSONArray()
        val candidates = mutableListOf(File("/dev/block/by-name"), File("/dev/block/bootdevice/by-name"))
        File("/dev/block/platform").listFiles()?.forEach { platform ->
            candidates.add(File(platform, "by-name"))
            platform.listFiles()?.forEach { child -> candidates.add(File(child, "by-name")) }
        }
        candidates.distinctBy { it.absolutePath }.filter { it.isDirectory }.forEach { dir ->
            dir.listFiles()?.sortedBy { it.name }?.forEach { node ->
                byName.put(JSONObject().apply {
                    put("name", node.name)
                    put("path", node.absolutePath)
                    put("target", try { node.canonicalPath } catch (_: Exception) { "unavailable" })
                    put("readableMetadata", node.canRead())
                })
            }
        }
        put("byNameEntries", byName)
        put("rawPartitionDataRead", false)
        put("note", "Метаданные разделов; содержимое блочных устройств не читалось и не изменялось.")
    }

    private fun collectBootInfo(): JSONObject = JSONObject().apply {
        put("bootProperties", collectProperties(listOf(
            "ro.boot.bootloader", "ro.boot.hardware", "ro.bootmode", "ro.boot.mode",
            "ro.boot.slot_suffix", "ro.boot.slot", "ro.boot.bootdevice", "ro.boot.boot_devices",
            "ro.bootloader", "ro.hardware", "ro.product.board"
        )))
        put("kernelCmdline", readText("/proc/cmdline", 16000))
        put("kernelBootconfig", readText("/proc/bootconfig", 12000))
        put("deviceTreeModel", readText("/proc/device-tree/model", 2000))
        put("deviceTreeCompatible", readText("/proc/device-tree/compatible", 4000))
        put("kernelModules", readText("/proc/modules", 12000))
        put("bootCompleted", getSystemProperty("sys.boot_completed"))
    }

    private fun collectSecurityInfo(): JSONObject = JSONObject().apply {
        put("properties", collectProperties(listOf(
            "ro.boot.verifiedbootstate", "ro.boot.flash.locked", "ro.boot.vbmeta.device_state",
            "ro.boot.avb_version", "ro.boot.veritymode", "ro.boot.dm_verity",
            "ro.crypto.state", "ro.crypto.type", "vold.decrypt", "ro.secure", "ro.debuggable",
            "ro.build.type", "ro.build.tags", "ro.build.version.security_patch"
        )))
        put("selinuxEnforce", readText("/sys/fs/selinux/enforce", 100).trim())
        put("selinuxContext", readText("/proc/self/attr/current", 500).trim())
        put("dataMount", readText("/proc/mounts", 16000).lineSequence()
            .filter { it.contains(" /data ") }.joinToString("\\n"))
        put("note", "Значения отражают только доступные свойства; недоступность не означает отключение защиты.")
    }

    private fun collectRecoveryInfo(): JSONObject = JSONObject().apply {
        val paths = listOf(
            "/system/bin/recovery", "/system/bin/update_engine", "/system/bin/bootctl",
            "/vendor/bin/bootctl", "/sbin/recovery", "/dev/block/by-name/recovery",
            "/dev/block/by-name/boot", "/dev/block/by-name/vendor_boot", "/dev/block/by-name/vbmeta"
        )
        val found = JSONArray()
        paths.forEach { path ->
            val f = File(path)
            if (f.exists()) found.put(JSONObject().apply {
                put("path", path); put("directory", f.isDirectory); put("readableMetadata", f.canRead())
            })
        }
        put("knownPaths", found)
        put("slotAndBootProperties", collectProperties(listOf(
            "ro.boot.slot_suffix", "ro.boot.slot", "ro.boot.dynamic_partitions",
            "ro.virtual_ab.enabled", "ro.boot.fastboot", "ro.bootmode", "sys.boot_completed"
        )))
        put("backupMethod", "not_determined")
        put("rawBackupAttempted", false)
        put("note", "Recovery/fastboot не запускаются; резервные копии разделов не создаются.")
    }

    private fun collectProperties(names: List<String>): JSONObject = JSONObject().apply {
        names.forEach { name -> put(name, getSystemProperty(name)) }
    }

    private fun getSystemProperty(name: String): String = try {
        val process = ProcessBuilder("getprop", name).redirectErrorStream(true).start()
        if (!process.waitForWithTimeout(1200)) {
            process.destroyForcibly()
            "timeout"
        } else if (process.exitValue() == 0) {
            process.inputStream.bufferedReader().use { it.readText().trim().take(1000) }
                .ifBlank { "empty" }
        } else "unavailable"
    } catch (_: Exception) { "unavailable" }



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


    // v0.8.0: expanded read-only diagnostics for panel, ADB/USB, storage and recovery planning.
    // This method deliberately does not read raw block contents or write to flash.
    private fun collectExtendedDiagnostics(): JSONObject = JSONObject().apply {
        put("deviceIdentity", JSONObject().apply {
            put("manufacturer", Build.MANUFACTURER)
            put("brand", Build.BRAND)
            put("model", Build.MODEL)
            put("device", Build.DEVICE)
            put("product", Build.PRODUCT)
            put("board", Build.BOARD)
            put("hardware", Build.HARDWARE)
            put("fingerprint", Build.FINGERPRINT)
            put("display", Build.DISPLAY)
            put("bootloader", Build.BOOTLOADER)
            put("androidRelease", Build.VERSION.RELEASE)
            put("sdk", Build.VERSION.SDK_INT)
            put("supportedAbis", JSONArray(Build.SUPPORTED_ABIS.toList()))
        })

        val propCommands = JSONArray()
        listOf(
            listOf("getprop", "ro.product.manufacturer"),
            listOf("getprop", "ro.product.brand"),
            listOf("getprop", "ro.product.model"),
            listOf("getprop", "ro.product.device"),
            listOf("getprop", "ro.product.name"),
            listOf("getprop", "ro.product.board"),
            listOf("getprop", "ro.hardware"),
            listOf("getprop", "ro.build.fingerprint"),
            listOf("getprop", "ro.build.description"),
            listOf("getprop", "ro.build.version.incremental"),
            listOf("getprop", "ro.build.version.security_patch"),
            listOf("getprop", "ro.bootloader"),
            listOf("getprop", "ro.boot.verifiedbootstate"),
            listOf("getprop", "ro.boot.flash.locked"),
            listOf("getprop", "ro.boot.vbmeta.device_state")
        ).forEach { command ->
            val result = runReadOnlyCommand(command, 2000)
            propCommands.put(JSONObject().apply {
                put("property", command.last())
                put("value", result.optString("output").trim())
                put("exitCode", result.optInt("exitCode", -1))
                put("error", result.optString("error"))
            })
        }
        put("buildProperties", propCommands)

        val panelCandidates = listOf(
            "/sys/class/graphics/fb0/name",
            "/sys/class/graphics/fb0/modes",
            "/sys/class/graphics/fb0/virtual_size",
            "/sys/class/graphics/fb0/bits_per_pixel",
            "/sys/class/display/HDMI/name",
            "/sys/class/display/HDMI/mode",
            "/sys/class/drm/card0-eDP-1/status",
            "/sys/class/drm/card0-HDMI-A-1/status",
            "/proc/device-tree/model",
            "/proc/device-tree/compatible",
            "/sys/firmware/devicetree/base/model",
            "/sys/firmware/devicetree/base/compatible",
            "/sys/class/graphics/fb0/device/modalias",
            "/sys/class/graphics/fb0/device/uevent"
        )
        val panel = JSONArray()
        panelCandidates.forEach { path ->
            val file = File(path)
            if (file.exists()) {
                val value = try {
                    file.readBytes().take(2048).toByteArray().toString(Charsets.UTF_8)
                        .replace("\u0000", " ").trim()
                } catch (e: Exception) { "" }
                panel.put(JSONObject().apply {
                    put("path", path)
                    put("readable", file.canRead())
                    put("value", value)
                    put("error", if (value.isEmpty() && file.canRead()) "empty_or_binary" else "")
                })
            }
        }
        put("panelAndDisplayCandidates", panel)
        put("panelIdentification",
            if (panel.length() == 0) "not_exposed_by_known_sysfs_paths"
            else "candidate_metadata_only_panel_model_not_confirmed")

        val adb = JSONObject()
        try {
            adb.put("settingsGlobalAdbEnabled",
                android.provider.Settings.Global.getInt(contentResolver, "adb_enabled", -1))
        } catch (e: Exception) {
            adb.put("settingsGlobalAdbEnabled", -1)
            adb.put("settingsReadError", e.message ?: e.javaClass.simpleName)
        }
        val usbProps = JSONArray()
        listOf(
            "sys.usb.config", "persist.sys.usb.config", "sys.usb.state",
            "service.adb.tcp.port", "persist.adb.tcp.port",
            "persist.service.adb.enable", "ro.adb.secure", "ro.debuggable"
        ).forEach { key ->
            val result = runReadOnlyCommand(listOf("getprop", key), 2000)
            usbProps.put(JSONObject().apply {
                put("name", key); put("value", result.optString("output").trim())
            })
        }
        adb.put("properties", usbProps)
        val usbPaths = listOf(
            "/sys/class/android_usb/android0/state",
            "/sys/class/android_usb/android0/functions",
            "/sys/class/android_usb/android0/enable",
            "/config/usb_gadget/g1/UDC",
            "/dev/usb-ffs/adb",
            "/dev/bus/usb"
        )
        val usbNodes = JSONArray()
        usbPaths.forEach { path ->
            val f = File(path)
            usbNodes.put(JSONObject().apply {
                put("path", path); put("exists", f.exists())
                put("directory", f.isDirectory); put("readable", f.canRead())
            })
        }
        adb.put("usbNodes", usbNodes)
        put("adbUsb", adb)

        val storage = JSONArray()
        val storagePaths = linkedSetOf<String>()
        storagePaths.add(Environment.getExternalStorageDirectory().absolutePath)
        getExternalFilesDir(null)?.let { storagePaths.add(it.absolutePath) }
        getExternalFilesDirs(null).filterNotNull().forEach { storagePaths.add(it.absolutePath) }
        storagePaths.forEach { path ->
            val f = File(path)
            val item = JSONObject().apply {
                put("path", path)
                put("exists", f.exists())
                put("directory", f.isDirectory)
                put("readable", f.canRead())
                put("writable", f.canWrite())
            }
            if (f.exists()) {
                try {
                    val stat = android.os.StatFs(path)
                    item.put("availableBytes", stat.availableBytes)
                    item.put("totalBytes", stat.totalBytes)
                } catch (e: Exception) {
                    item.put("statError", e.message ?: e.javaClass.simpleName)
                }
            }
            storage.put(item)
        }
        put("backupStorageCandidates", storage)
        put("backupStorageNote",
            "Оценены только доступность каталогов и свободное место. Тестовая запись не выполнялась; доступ к каталогу не гарантирует возможность сохранить полный дамп.")

        val zramPaths = listOf(
            "/sys/block/zram0/disksize",
            "/sys/block/zram0/mm_stat",
            "/sys/block/zram0/comp_algorithm",
            "/sys/block/zram0/backing_dev",
            "/sys/block/zram0/max_comp_streams",
            "/proc/meminfo",
            "/proc/swaps",
            "/proc/pressure/memory"
        )
        val memory = JSONArray()
        zramPaths.forEach { path ->
            val f = File(path)
            if (f.exists()) {
                val value = try { f.readText().take(6000).trim() }
                    catch (e: Exception) { "READ_ERROR: " + (e.message ?: e.javaClass.simpleName) }
                memory.put(JSONObject().apply { put("path", path); put("value", value) })
            }
        }
        put("memoryAndZram", memory)

        val thermal = JSONArray()
        for (i in 0..15) {
            val base = File("/sys/class/thermal/thermal_zone$i")
            if (!base.exists()) continue
            val type = try { File(base, "type").readText().trim() } catch (_: Exception) { "" }
            val temp = try { File(base, "temp").readText().trim() } catch (_: Exception) { "" }
            thermal.put(JSONObject().apply {
                put("zone", i); put("type", type); put("rawTemperature", temp)
            })
        }
        put("thermalZones", thermal)
        put("thermalNote",
            "Значения приведены в исходном виде из sysfs; единицы и масштаб зависят от драйвера и требуют проверки.")

        val blockLinks = JSONArray()
        listOf(
            "/dev/block/by-name",
            "/dev/block/platform/soc/f9830000.emmc/by-name",
            "/dev/block/platform/soc/fe340000.emmc/by-name"
        ).forEach { dir ->
            File(dir).listFiles()?.sortedBy { it.name }?.forEach { node ->
                blockLinks.put(JSONObject().apply {
                    put("name", node.name)
                    put("path", node.absolutePath)
                    put("target", try { node.canonicalPath } catch (_: Exception) { "" })
                    put("exists", node.exists())
                    put("readable", node.canRead())
                    put("writable", node.canWrite())
                    put("directory", node.isDirectory)
                })
            }
        }
        put("blockDeviceLinks", blockLinks)
        put("rawPartitionContentsRead", false)
        put("partitionWriteAttempted", false)
        put("firmwareUpdateAttempted", false)
        put("recoveryOrFastbootStarted", false)
    }


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

    private fun collectMediaCodecs(): JSONArray {
        val result = JSONArray()
        return try {
            MediaCodecList(MediaCodecList.ALL_CODECS).codecInfos.forEach { info ->
                val types = info.supportedTypes.filter { it.startsWith("video/", ignoreCase = true) }
                if (types.isNotEmpty()) result.put(JSONObject().apply {
                    put("name", info.name)
                    put("encoder", info.isEncoder)
                    put("videoTypes", JSONArray(types))
                    if (Build.VERSION.SDK_INT >= 29) put("hardwareAccelerated", info.isHardwareAccelerated)
                })
            }
            result
        } catch (e: Exception) {
            result.put(JSONObject().put("error", e.message ?: "codec list unavailable"))
            result
        }
    }

    private fun collectCpuFrequencies(): JSONArray {
        val result = JSONArray()
        for (i in 0..7) {
            val base = "/sys/devices/system/cpu/cpu$i/cpufreq/"
            val cur = readNumber(base + "scaling_cur_freq")
            val min = readNumber(base + "scaling_min_freq")
            val max = readNumber(base + "scaling_max_freq")
            if (cur != null || min != null || max != null) {
                result.put(JSONObject().apply {
                    put("cpu", i)
                    put("currentKHz", cur ?: JSONObject.NULL)
                    put("minKHz", min ?: JSONObject.NULL)
                    put("maxKHz", max ?: JSONObject.NULL)
                })
            }
        }
        return result
    }

    private fun collectCpuGovernor(): String {
        val candidates = listOf(
            "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor",
            "/sys/devices/system/cpu/cpufreq/policy0/scaling_governor"
        )
        return candidates.firstNotNullOfOrNull { readTextOrNull(it)?.trim() } ?: "недоступно"
    }

    private fun collectCpuLoad(): String {
        return try {
            val first = readCpuCounters() ?: return "недоступно"
            Thread.sleep(350)
            val second = readCpuCounters() ?: return "недоступно"
            val total = second.first - first.first
            val idle = second.second - first.second
            if (total <= 0) "недоступно"
            else String.format(Locale.US, "%.1f%%", 100.0 * (total - idle).toDouble() / total)
        } catch (_: Exception) {
            "недоступно"
        }
    }

    private fun readCpuCounters(): Pair<Long, Long>? {
        val line = readText("/proc/stat", 2000).lineSequence().firstOrNull { it.startsWith("cpu ") } ?: return null
        val v = line.trim().split(Regex("\\s+")).drop(1).mapNotNull { it.toLongOrNull() }
        if (v.size < 4) return null
        val total = v.sum()
        val idle = v[3] + (v.getOrNull(4) ?: 0L)
        return total to idle
    }

    private fun collectTemperatures(): JSONArray {
        val result = JSONArray()
        val dir = File("/sys/class/thermal")
        val zones = dir.listFiles { f -> f.name.startsWith("thermal_zone") } ?: return result
        zones.sortedBy { it.name }.forEach { zone ->
            val raw = readNumber("${zone.absolutePath}/temp")
            val type = readTextOrNull("${zone.absolutePath}/type")?.trim() ?: "unknown"
            if (raw != null) {
                val celsius = if (raw > 1000) raw / 1000.0 else raw.toDouble()
                result.put(JSONObject().apply {
                    put("zone", zone.name)
                    put("type", type)
                    put("celsius", celsius)
                })
            }
        }
        return result
    }

    private fun collectZram(): JSONObject {
        val z = JSONObject()
        val candidates = listOf("/sys/block/zram0", "/sys/block/zram1")
        val found = candidates.firstOrNull { File(it).exists() }
        if (found == null) {
            z.put("status", "не обнаружен или недоступен")
            return z
        }
        z.put("device", found)
        z.put("disksizeBytes", readNumber("$found/disksize") ?: JSONObject.NULL)
        z.put("mmStat", readTextOrNull("$found/mm_stat") ?: "недоступно")
        z.put("ioStat", readTextOrNull("$found/io_stat") ?: "недоступно")
        z.put("status", "обнаружен")
        return z
    }


    private fun collectRunningProcesses(): JSONArray {
        val result = JSONArray()
        return try {
            val am = getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
            val processes = am.runningAppProcesses ?: return result
            for (proc in processes.sortedBy { it.importance }.take(60)) {
                val item = JSONObject()
                item.put("processName", proc.processName ?: "unknown")
                item.put("pid", proc.pid)
                item.put("uid", proc.uid)
                item.put("importance", proc.importance)
                item.put("importanceLabel", importanceLabel(proc.importance))
                try {
                    val mem = am.getProcessMemoryInfo(intArrayOf(proc.pid)).firstOrNull()
                    if (mem != null) {
                        item.put("pssKb", mem.totalPss)
                        item.put("privateDirtyKb", mem.totalPrivateDirty)
                    }
                } catch (_: Exception) {
                    item.put("memoryInfo", "недоступно")
                }
                result.put(item)
            }
            result
        } catch (_: Exception) {
            result.put(JSONObject().put("error", "список процессов недоступен"))
            result
        }
    }

    private fun importanceLabel(value: Int): String = when (value) {
        ActivityManager.RunningAppProcessInfo.IMPORTANCE_FOREGROUND -> "foreground"
        ActivityManager.RunningAppProcessInfo.IMPORTANCE_FOREGROUND_SERVICE -> "foreground_service"
        ActivityManager.RunningAppProcessInfo.IMPORTANCE_VISIBLE -> "visible"
        ActivityManager.RunningAppProcessInfo.IMPORTANCE_PERCEPTIBLE -> "perceptible"
        ActivityManager.RunningAppProcessInfo.IMPORTANCE_SERVICE -> "service"
        ActivityManager.RunningAppProcessInfo.IMPORTANCE_CACHED -> "cached"
        else -> "other($value)"
    }

    @Suppress("DEPRECATION")
    private fun collectInstalledPackages(): JSONArray {
        val result = JSONArray()
        return try {
            val pm = packageManager
            val packages = pm.getInstalledPackages(PackageManager.GET_META_DATA)
            for (pkg in packages.sortedBy { it.packageName }.take(500)) {
                val appInfo = pkg.applicationInfo ?: continue
                val item = JSONObject()
                item.put("packageName", pkg.packageName)
                item.put("appName", try { pm.getApplicationLabel(appInfo).toString() } catch (_: Exception) { pkg.packageName })
                item.put("systemApp", (appInfo.flags and android.content.pm.ApplicationInfo.FLAG_SYSTEM) != 0)
                item.put("updatedSystemApp", (appInfo.flags and android.content.pm.ApplicationInfo.FLAG_UPDATED_SYSTEM_APP) != 0)
                item.put("enabled", appInfo.enabled)
                item.put("versionName", pkg.versionName ?: "")
                item.put("targetSdk", appInfo.targetSdkVersion)
                item.put("firstInstallTime", pkg.firstInstallTime)
                item.put("lastUpdateTime", pkg.lastUpdateTime)
                result.put(item)
            }
            result
        } catch (e: Exception) {
            result.put(JSONObject().put("error", e.message ?: "список пакетов недоступен"))
            result
        }
    }

    private fun checkRoot() {
        statusView.text = "Проверка root… Команда только читает идентификатор пользователя."
        executor.execute {
            val result = runRootProbe()
            lastReport.put("rootStatus", result.first)
            lastReport.put("rootOutput", result.second)
            runOnUiThread {
                statusView.text = "Проверка Root: ${result.first}"
                reportView.text = formatReport(lastReport)
            }
        }
    }

    private fun runRootProbe(): Pair<String, String> {
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

    private fun exportReport() {
        try {
            val intent = android.content.Intent(android.content.Intent.ACTION_CREATE_DOCUMENT).apply {
                addCategory(android.content.Intent.CATEGORY_OPENABLE)
                type = "application/json"
                putExtra(android.content.Intent.EXTRA_TITLE, "tv-diagnostic-report-v120.json")
            }
            startActivityForResult(intent, 4102)
        } catch (e: Exception) {
            try {
                val dir = getExternalFilesDir(android.os.Environment.DIRECTORY_DOCUMENTS) ?: filesDir
                val file = java.io.File(dir, "tv-diagnostic-report-v120.json")
                file.writeText(lastReport.toString(2), Charsets.UTF_8)
                statusView.text = "Окно сохранения недоступно. Отчёт сохранён внутри приложения: " + file.absolutePath
            } catch (saveError: Exception) {
                statusView.text = "Не удалось сохранить отчёт: " + (saveError.message ?: saveError.javaClass.simpleName)
            }
        }
    }

    private fun shareReport() {
    try {
        if (android.os.Build.VERSION.SDK_INT < 29) {
            statusView.text = "Отправка файла требует Android 10 или новее"
            return
        }
        val values = android.content.ContentValues().apply {
            put(android.provider.MediaStore.MediaColumns.DISPLAY_NAME, "tv-diagnostic-report.json")
            put(android.provider.MediaStore.MediaColumns.MIME_TYPE, "application/json")
            put(android.provider.MediaStore.MediaColumns.RELATIVE_PATH, android.os.Environment.DIRECTORY_DOWNLOADS + "/TV Diagnostic")
        }
        val uri = contentResolver.insert(android.provider.MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
            ?: throw IllegalStateException("Не удалось создать JSON-файл")
        contentResolver.openOutputStream(uri)?.use { output ->
            output.write(lastReport.toString(2).toByteArray(Charsets.UTF_8))
        } ?: throw IllegalStateException("Не удалось записать JSON-файл")
        val intent = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
            type = "application/json"
            putExtra(android.content.Intent.EXTRA_SUBJECT, "Отчёт TV Diagnostic")
            putExtra(android.content.Intent.EXTRA_STREAM, uri)
            clipData = android.content.ClipData.newUri(contentResolver, "TV Diagnostic report", uri)
            addFlags(android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        startActivity(android.content.Intent.createChooser(intent, "Отправить файл отчёта"))
        statusView.text = "JSON-файл создан. Выбери приложение для отправки"
    } catch (e: Exception) {
        statusView.text = "Не удалось подготовить файл отчёта: " + (e.message ?: e.javaClass.simpleName)
    }
}


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
                server.soTimeout = 30 * 60 * 1000
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
                                "\r\nContent-Disposition: attachment; filename=\"" + file.name + "\"" +
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
                val buffer = ByteArray(64 * 1024)
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
                    var copied = 0L
                    var proc: java.lang.Process? = null
                    try {
                        val process = ProcessBuilder(
                            "su", "0", "dd", "if=" + device,
                            "bs=" + blockSize, "count=" + blocks
                        ).start()
                        proc = process
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


    // v1.3.0: read-only SYSTEM + VENDOR backup. Stream directly into a ZIP
    // to avoid keeping both raw images and a second archive on internal storage.

    // v1.3.3: list and stream only an existing SYSTEM/VENDOR archive from v1.3.0.
    // No archive is copied to this app's storage; root cat writes directly to the HTTP socket.
    private fun findLegacySystemVendorBackups() {
        if (backupServer != null) {
            statusView.text = "Сначала останови предыдущую Wi-Fi-передачу"
            return
        }
        statusView.text = "Проверка Root и папки резервных копий 1.3.0…"
        executor.execute {
            try {
                val root = runReadOnlyCommand(listOf("su", "0", "id"), 5000)
                val rootText = root.optString("output")
                if (root.optInt("exitCode", -1) != 0 ||
                    !Regex("uid=0(?:\\(|\\s|$)").containsMatchIn(rootText)) {
                    throw IllegalStateException("Root не подтверждён: " + rootText)
                }

                val legacyDir = "/data/user/0/com.tvdiagnostic.hi3751/files/backups"
                val script = "pm path com.tvdiagnostic.hi3751 >/dev/null 2>&1 || { echo PACKAGE_NOT_INSTALLED; exit 5; }; " +
                    "d='$legacyDir'; [ -d \"\$d\" ] || { echo DIR_NOT_FOUND; exit 3; }; " +
                    "for f in \"\$d\"/system-vendor-*.zip; do " +
                    "[ -f \"\$f\" ] && [ ! -L \"\$f\" ] || continue; s=\$(wc -c < \"\$f\") || exit 4; " +
                    "printf '%s|%s\\n' \"\$s\" \"\$f\"; done"
                val result = runReadOnlyCommand(listOf("su", "0", "sh", "-c", script), 10000)
                val output = result.optString("output")
                if (result.optInt("exitCode", -1) != 0) {
                    val reason = if (output.contains("DIR_NOT_FOUND")) "Папка бэкапов 1.3.0 не найдена" else output
                    throw IllegalStateException(reason.ifBlank { "Не удалось прочитать список архивов" })
                }
                val candidates = output.lineSequence().mapNotNull { line ->
                    val split = line.split("|", limit = 2)
                    if (split.size != 2) return@mapNotNull null
                    val size = split[0].trim().toLongOrNull() ?: return@mapNotNull null
                    val path = split[1].trim()
                    if (size <= 0L || !path.startsWith(legacyDir + "/") ||
                        !Regex("system-vendor-[A-Za-z0-9._-]+\\.zip").containsMatchIn(path.substringAfterLast('/')))
                        return@mapNotNull null
                    Pair(path, size)
                }.toList()
                if (candidates.isEmpty()) throw IllegalStateException(
                    "В папке 1.3.0 не найдено готовых system-vendor-*.zip. Данные не изменялись."
                )
                runOnUiThread {
                    val labels = candidates.map { (path, size) ->
                        path.substringAfterLast('/') + " • " + String.format(Locale.US, "%.2f GiB", size / 1073741824.0)
                    }.toTypedArray()
                    android.app.AlertDialog.Builder(this)
                        .setTitle("Найденные архивы 1.3.0")
                        .setItems(labels) { _, which ->
                            val selected = candidates[which]
                            confirmLegacyArchiveTransfer(selected.first, selected.second)
                        }
                        .setNegativeButton("Отмена", null)
                        .show()
                    statusView.text = "Найдено архивов: ${candidates.size}. Исходные файлы не копировались."
                }
            } catch (e: Exception) {
                runOnUiThread {
                    statusView.text = "Поиск бэкапа 1.3.0 не выполнен: " +
                        (e.message ?: e.javaClass.simpleName) + ". Ничего не изменено."
                }
            }
        }
    }

    private fun confirmLegacyArchiveTransfer(path: String, size: Long) {
        android.app.AlertDialog.Builder(this)
            .setTitle("Передать готовый архив 1.3.0?")
            .setMessage("Файл: " + path.substringAfterLast('/') + "\\nРазмер: " + size +
                " байт. Архив будет прочитан через root и передан напрямую по Wi-Fi без создания второй копии на телевизоре. Исходный файл не изменяется. Продолжить?")
            .setNegativeButton("Отмена", null)
            .setPositiveButton("Передать") { _, _ -> startLegacyArchiveHttpServer(path, size) }
            .show()
    }

    private fun startLegacyArchiveHttpServer(path: String, expectedSize: Long) {
        if (backupServer != null) {
            statusView.text = "Сначала останови предыдущую Wi-Fi-передачу"
            return
        }
        statusView.text = "Подготовка потоковой передачи архива 1.3.0…"
        Thread {
            var created: java.net.ServerSocket? = null
            try {
                val server = java.net.ServerSocket()
                created = server
                server.reuseAddress = false
                server.bind(java.net.InetSocketAddress(0), 1)
                server.soTimeout = 30 * 60 * 1000
                backupServer = server
                val random = ByteArray(16)
                java.security.SecureRandom().nextBytes(random)
                val token = random.joinToString("") { "%02x".format(it) }
                val ip = java.util.Collections.list(java.net.NetworkInterface.getNetworkInterfaces())
                    .asSequence().filter { try { it.isUp && !it.isLoopback } catch (_: Exception) { false } }
                    .flatMap { java.util.Collections.list(it.inetAddresses).asSequence() }
                    .filterIsInstance<java.net.Inet4Address>()
                    .firstOrNull { it.isSiteLocalAddress && !it.isLoopbackAddress }
                    ?.hostAddress ?: throw IllegalStateException("Не найден локальный IPv4 телевизора")
                val url = "http://$ip:${server.localPort}/download?token=$token"
                val filename = path.substringAfterLast('/').replace("\"", "")
                runOnUiThread {
                    statusView.text = "Готов к передаче архива 1.3.0 • $expectedSize байт\\nОткрой на телефоне в той же сети:\\n$url\\n\\nСсылка действует 30 минут. Не закрывай приложение."
                }

                while (backupServer === server) {
                    val socket = server.accept()
                    var transferred = false
                    socket.use { client ->
                        client.soTimeout = 30000
                        val reader = client.getInputStream().bufferedReader(Charsets.ISO_8859_1)
                        val request = reader.readLine() ?: ""
                        while (true) {
                            val line = reader.readLine() ?: break
                            if (line.isEmpty()) break
                        }
                        if (request.startsWith("GET /download?token=$token HTTP/")) {
                            val out = client.getOutputStream()
                            val headers = "HTTP/1.1 200 OK\\r\\nContent-Type: application/zip\\r\\n" +
                                "Content-Length: $expectedSize\\r\\nContent-Disposition: attachment; filename=\\"$filename\\"\\r\\n" +
                                "Cache-Control: no-store\\r\\nConnection: close\\r\\n\\r\\n"
                            out.write(headers.toByteArray(Charsets.US_ASCII))
                            val process = ProcessBuilder("su", "0", "cat", path).start()
                            val errors = StringBuilder()
                            val errorThread = Thread {
                                try { process.errorStream.bufferedReader().use { it.forEachLine { line ->
                                    synchronized(errors) { if (errors.length < 2000) errors.append(line).append('\\n') }
                                } } } catch (_: Exception) { }
                            }
                            errorThread.isDaemon = true
                            errorThread.start()
                            val digest = java.security.MessageDigest.getInstance("SHA-256")
                            var sent = 0L
                            val buffer = ByteArray(64 * 1024)
                            val watchdog = Thread {
                                try {
                                    if (!process.waitFor(30, java.util.concurrent.TimeUnit.MINUTES))
                                        process.destroyForcibly()
                                } catch (_: InterruptedException) { }
                            }
                            watchdog.isDaemon = true
                            watchdog.start()
                            process.inputStream.use { input ->
                                while (true) {
                                    val n = input.read(buffer)
                                    if (n < 0) break
                                    if (n == 0) continue
                                    out.write(buffer, 0, n)
                                    digest.update(buffer, 0, n)
                                    sent += n.toLong()
                                    if (sent > expectedSize) throw IllegalStateException("Файл изменился: получено больше ожидаемого размера")
                                }
                            }
                            out.flush()
                            val exit = process.waitFor()
                            errorThread.join(2000)
                            val sha = digest.digest().joinToString("") { "%02x".format(it) }
                            if (exit != 0 || sent != expectedSize) {
                                throw IllegalStateException("Поток неполный: $sent из $expectedSize байт; exit=$exit; " + errors.toString())
                            }
                            runOnUiThread {
                                statusView.text = "Архив 1.3.0 передан полностью: $sent байт\\nSHA-256: $sha\\nИсходный архив на ТВ не изменён."
                            }
                            transferred = true
                        } else {
                            val body = "Forbidden".toByteArray(Charsets.UTF_8)
                            out.write(("HTTP/1.1 403 Forbidden\\r\\nContent-Length: ${body.size}\\r\\nConnection: close\\r\\n\\r\\n").toByteArray(Charsets.US_ASCII))
                            out.write(body)
                            out.flush()
                        }
                    }
                    if (transferred) break
                }
            } catch (e: Exception) {
                if (backupServer != null) runOnUiThread {
                    statusView.text = "Передача архива 1.3.0 остановлена: " + (e.message ?: e.javaClass.simpleName)
                }
            } finally {
                try { created?.close() } catch (_: Exception) { }
                if (backupServer === created) backupServer = null
            }
        }.start()
    }

    private fun confirmSystemVendorBackup() {
        android.app.AlertDialog.Builder(this)
            .setTitle("Резервная копия SYSTEM и VENDOR")
            .setMessage("Будут считаны только два заранее разрешённых раздела: SYSTEM (mmcblk0p20) и VENDOR (mmcblk0p21). Сначала проверяются Root, соответствие устройств, размеры и свободное место. Данные сразу записываются в ZIP в закрытой папке приложения; затем каждый файл внутри архива повторно проверяется по размеру и SHA-256. Записи в разделы телевизора нет. Копирование может занять продолжительное время. Продолжить?")
            .setNegativeButton("Отмена", null)
            .setPositiveButton("Начать копирование") { _, _ -> startSystemVendorBackup() }
            .show()
    }

    private fun startSystemVendorBackup() {
        if (backupServer != null) {
            statusView.text = "Сначала останови предыдущую Wi-Fi-передачу"
            return
        }
        statusView.text = "Проверка Root, SYSTEM и VENDOR…"
        executor.execute {
            var archive: File? = null
            try {
                val root = runReadOnlyCommand(listOf("su", "0", "id"), 5000)
                val rootText = root.optString("output")
                if (root.optInt("exitCode", -1) != 0 ||
                    !Regex("uid=0(?:\\(|\\s|$)").containsMatchIn(rootText)) {
                    throw IllegalStateException("Root не подтверждён: " + rootText)
                }

                val specs = listOf(
                    Triple("system", "/dev/block/by-name/system", "/dev/block/mmcblk0p20"),
                    Triple("vendor", "/dev/block/by-name/vendor", "/dev/block/mmcblk0p21")
                )
                val sizes = linkedMapOf<String, Long>()
                var totalBytes = 0L
                for ((name, path, expectedTarget) in specs) {
                    val canonical = runReadOnlyCommand(listOf("su", "0", "readlink", "-f", path), 5000)
                    val target = canonical.optString("output").trim()
                    if (canonical.optInt("exitCode", -1) != 0 || target != expectedTarget) {
                        throw IllegalStateException("Путь раздела " + name.uppercase() + " не совпал с ожидаемым: " + target)
                    }
                    val sizeResult = runReadOnlyCommand(
                        listOf("su", "0", "blockdev", "--getsize64", path), 7000
                    )
                    val bytes = sizeResult.optString("output").trim().toLongOrNull() ?: 0L
                    val maxPartitionBytes = 3L * 1024L * 1024L * 1024L
                    if (sizeResult.optInt("exitCode", -1) != 0 || bytes <= 0L ||
                        bytes > maxPartitionBytes || bytes % 512L != 0L) {
                        throw IllegalStateException("Размер " + name.uppercase() + " не прошёл проверку: " + bytes + " байт")
                    }
                    sizes[name] = bytes
                    totalBytes = Math.addExact(totalBytes, bytes)
                }

                val available = android.os.StatFs(filesDir.absolutePath).availableBytes
                val reserve = 64L * 1024L * 1024L
                if (available < totalBytes + reserve) {
                    throw IllegalStateException("Недостаточно места: нужно не менее " +
                        (totalBytes + reserve) + " байт, доступно " + available +
                        ". Ничего не скопировано.")
                }

                val dir = File(filesDir, "backups")
                if (!dir.exists() && !dir.mkdirs())
                    throw IllegalStateException("Не удалось создать папку резервных копий")
                archive = File(dir, "system-vendor-" + System.currentTimeMillis() + ".zip")
                val hashes = linkedMapOf<String, String>()
                val buffer = ByteArray(256 * 1024)

                java.util.zip.ZipOutputStream(java.io.BufferedOutputStream(java.io.FileOutputStream(archive))).use { zip ->
                    zip.setLevel(1)
                    for ((name, path, _) in specs) {
                        val bytes = sizes[name]!!
                        runOnUiThread { statusView.text = "Чтение " + name.uppercase() + ": 0%" }
                        val process = ProcessBuilder(
                            "su", "0", "dd", "if=" + path, "bs=512", "count=" + (bytes / 512L)
                        ).start()
                        // A blocked read from stdout must not bypass the overall timeout.
                        // The watchdog kills only the dd process; it never writes to a block device.
                        val readTimedOut = java.util.concurrent.atomic.AtomicBoolean(false)
                        val watchdog = Thread {
                            try {
                                if (!process.waitFor(30L, java.util.concurrent.TimeUnit.MINUTES)) {
                                    readTimedOut.set(true)
                                    process.destroyForcibly()
                                }
                            } catch (_: InterruptedException) { }
                        }
                        watchdog.isDaemon = true
                        watchdog.start()
                        val errors = StringBuilder()
                        val errorReader = Thread {
                            try {
                                process.errorStream.bufferedReader().use { reader ->
                                    while (true) {
                                        val line = reader.readLine() ?: break
                                        synchronized(errors) { if (errors.length < 3000) errors.append(line).append('\n') }
                                    }
                                }
                            } catch (_: Exception) { }
                        }
                        errorReader.start()
                        val digest = java.security.MessageDigest.getInstance("SHA-256")
                        var copied = 0L
                        try {
                            zip.putNextEntry(java.util.zip.ZipEntry(name + ".img"))
                            process.inputStream.use { input ->
                                while (copied < bytes) {
                                    val wanted = minOf(buffer.size.toLong(), bytes - copied).toInt()
                                    val n = input.read(buffer, 0, wanted)
                                    if (n < 0) break
                                    if (n == 0) continue
                                    copied += n.toLong()
                                    digest.update(buffer, 0, n)
                                    zip.write(buffer, 0, n)
                                    val pct = copied * 100L / bytes
                                    if (copied == bytes || copied % (16L * 1024L * 1024L) < n) {
                                        runOnUiThread { statusView.text = "Чтение " + name.uppercase() + ": " + pct + "% (" + copied + "/" + bytes + " байт)" }
                                    }
                                }
                            }
                            if (copied != bytes) throw IllegalStateException("Неполное чтение " + name.uppercase() + ": " + copied + " из " + bytes)
                            if (!process.waitForWithTimeout(5000L)) {
                                process.destroyForcibly()
                                throw IllegalStateException("Процесс чтения " + name.uppercase() + " не завершился")
                            }
                            watchdog.join(1000)
                            if (readTimedOut.get())
                                throw IllegalStateException("Чтение " + name.uppercase() + " превысило 30 минут")
                            errorReader.join(3000)
                            if (process.exitValue() != 0) throw IllegalStateException("dd " + name + " завершился с кодом " + process.exitValue() + ": " + errors)
                            zip.closeEntry()
                            hashes[name] = digest.digest().joinToString("") { "%02x".format(it) }
                        } catch (e: Exception) {
                            try { process.destroyForcibly() } catch (_: Exception) { }
                            throw e
                        }
                    }
                    val manifest = buildString {
                        appendLine("TV Diagnostic read-only backup")
                        appendLine("Device: SmartTV235X / Hi3751V553")
                        appendLine("Created: " + System.currentTimeMillis())
                        for ((name, _, _) in specs) appendLine(name.uppercase() + " bytes=" + sizes[name] + " sha256=" + hashes[name])
                        appendLine("No partition writes were performed.")
                    }
                    zip.putNextEntry(java.util.zip.ZipEntry("SHA256SUMS.txt"))
                    zip.write(manifest.toByteArray(Charsets.UTF_8))
                    zip.closeEntry()
                    zip.finish()
                }

                // Re-open the archive and independently verify each stored image.
                java.util.zip.ZipFile(archive).use { zf ->
                    for ((name, _, _) in specs) {
                        val entry = zf.getEntry(name + ".img") ?: throw IllegalStateException("В архиве отсутствует " + name)
                        if (entry.size != sizes[name]) throw IllegalStateException("Размер " + name + " внутри ZIP не совпал")
                        val digest = java.security.MessageDigest.getInstance("SHA-256")
                        var count = 0L
                        zf.getInputStream(entry).use { input ->
                            while (true) {
                                val n = input.read(buffer)
                                if (n < 0) break
                                if (n > 0) { digest.update(buffer, 0, n); count += n.toLong() }
                            }
                        }
                        val actual = digest.digest().joinToString("") { "%02x".format(it) }
                        if (count != sizes[name] || !actual.equals(hashes[name], true))
                            throw IllegalStateException("Повторная проверка SHA-256 " + name.uppercase() + " не пройдена")
                    }
                }
                val zipDigest = java.security.MessageDigest.getInstance("SHA-256")
                java.io.FileInputStream(archive).use { input ->
                    while (true) { val n = input.read(buffer); if (n < 0) break; if (n > 0) zipDigest.update(buffer, 0, n) }
                }
                val zipHash = zipDigest.digest().joinToString("") { "%02x".format(it) }
                runOnUiThread {
                    statusView.text = "SYSTEM и VENDOR скопированы. Архив повторно проверен.\n" +
                        specs.joinToString("\n") { (name, _, _) -> name.uppercase() + ": " + sizes[name] + " байт • SHA-256 " + hashes[name] } +
                        "\nZIP: " + archive.length() + " байт\nZIP SHA-256: " + zipHash + "\nПодготовка Wi-Fi…"
                }
                startBackupHttpServer(archive!!, zipHash)
            } catch (e: Exception) {
                try { archive?.delete() } catch (_: Exception) { }
                runOnUiThread {
                    statusView.text = "Бэкап SYSTEM/VENDOR НЕ завершён: " +
                        (e.message ?: e.javaClass.simpleName) + ". Разделы телевизора не изменялись."
                }
            }
        }
    }


    // v1.2.0: read-only inspection of the running kernel and live Device Tree.
    // No block-device contents are accessed; no files or partitions are modified.
    private fun collectDeviceTreeInfo(): JSONObject = JSONObject().apply {
        val base = File("/sys/firmware/devicetree/base")
        put("available", base.isDirectory)
        put("model", readText("/sys/firmware/devicetree/base/model", 2048).trim())
        put("compatibleRaw", readBinaryAsEscapedText("/sys/firmware/devicetree/base/compatible", 4096))
        put("procModel", readText("/proc/device-tree/model", 2048).trim())
        put("procCompatibleRaw", readBinaryAsEscapedText("/proc/device-tree/compatible", 4096))
        val paths = JSONArray()
        if (base.isDirectory) {
            val queue = java.util.ArrayDeque<Pair<File, Int>>()
            queue.add(Pair(base, 0))
            var visited = 0
            while (queue.isNotEmpty() && visited < 1500) {
                val (dir, depth) = queue.removeFirst()
                val children = try { dir.listFiles()?.sortedBy { it.name } ?: emptyList() }
                    catch (_: Exception) { emptyList() }
                for (child in children) {
                    if (visited >= 1500) break
                    visited++
                    val relative = child.absolutePath.removePrefix(base.absolutePath).trimStart('/')
                    if (child.isDirectory) {
                        paths.put(JSONObject().put("path", relative).put("type", "node"))
                        if (depth < 5) queue.add(Pair(child, depth + 1))
                    } else {
                        val size = try { child.length() } catch (_: Exception) { -1L }
                        val entry = JSONObject().put("path", relative).put("type", "property").put("size", size)
                        if (size in 1..512) {
                            entry.put("value", readBinaryAsEscapedText(child.absolutePath, 512))
                        } else if (size == 0L) {
                            entry.put("value", "")
                        }
                        paths.put(entry)
                    }
                }
            }
            put("truncated", queue.isNotEmpty() || visited >= 1500)
        } else {
            put("truncated", false)
        }
        put("entries", paths)
        put("entryCount", paths.length())
        put("note", "Только публичные узлы live Device Tree; бинарные свойства больше 512 байт не экспортируются.")
    }

    private fun readBinaryAsEscapedText(path: String, limit: Int): String = try {
        val bytes = File(path).inputStream().use { it.readNBytes(limit) }
        bytes.joinToString(" ") { b ->
            val v = b.toInt() and 0xff
            if (v in 32..126) v.toChar().toString() else String.format("\\x%02x", v)
        }
    } catch (_: Exception) { "" }

    private fun collectKernelInfo(): JSONObject = JSONObject().apply {
        put("version", readText("/proc/version", 4096).trim())
        put("cmdline", readText("/proc/cmdline", 12000).trim())
        put("bootconfig", readText("/proc/bootconfig", 12000).trim())
        put("modules", readText("/proc/modules", 24000))
        put("configGzAvailable", File("/proc/config.gz").canRead())
        put("configGzNote", "Конфигурация ядра не копируется автоматически; указывается только доступность.")
        put("kernelRelease", readText("/proc/sys/kernel/osrelease", 512).trim())
        put("kernelTaіnt", readText("/proc/sys/kernel/tainted", 128).trim())
    }

    private fun collectDriverInfo(): JSONObject = JSONObject().apply {
        val drivers = JSONArray()
        val roots = listOf("/sys/bus/platform/drivers", "/sys/bus/usb/drivers",
            "/sys/bus/mmc/drivers", "/sys/bus/i2c/drivers", "/sys/class")
        roots.forEach { root ->
            val dir = File(root)
            val children = try { dir.listFiles()?.sortedBy { it.name } ?: emptyList() }
                catch (_: Exception) { emptyList() }
            children.take(500).forEach { child ->
                drivers.put(JSONObject().put("root", root).put("name", child.name)
                    .put("directory", child.isDirectory))
            }
        }
        put("entries", drivers)
        put("count", drivers.length())
        put("note", "Инвентаризация имён sysfs; модули и драйверы не загружаются и не изменяются.")
    }

    private fun formatReport(j: JSONObject): String {
        fun mb(key: String) = String.format(Locale.US, "%.0f МБ", j.optLong(key) / 1048576.0)
        return buildString {
            appendLine("УСТРОЙСТВО")
            appendLine("${j.optString("manufacturer")} / ${j.optString("model")}")
            appendLine("Board: ${j.optString("board")}   Device: ${j.optString("device")}")
            appendLine("Product: ${j.optString("product")}")
            appendLine("Android: ${j.optString("android")} (API ${j.optInt("sdk")})")
            appendLine()
            appendLine("CPU")
            appendLine("Загрузка за короткий интервал: ${j.optString("cpuLoadPercent")}")
            appendLine("Governor: ${j.optString("cpuGovernor")}")
            val freqs = j.optJSONArray("cpuFrequencies") ?: JSONArray()
            if (freqs.length() == 0) appendLine("Частоты ядер: недоступны")
            for (i in 0 until freqs.length()) {
                val c = freqs.optJSONObject(i) ?: continue
                appendLine("CPU${c.optInt("cpu")}: ${formatMHz(c, "currentKHz")} МГц (min ${formatMHz(c, "minKHz")}, max ${formatMHz(c, "maxKHz")})")
            }
            appendLine()
            appendLine("GPU")
            appendLine(j.optString("gpu"))
            appendLine()
            appendLine("ПАМЯТЬ")
            appendLine("RAM всего: ${mb("ramTotalBytes")}")
            appendLine("RAM доступно: ${mb("ramAvailableBytes")}")
            appendLine("Low memory: ${j.optBoolean("lowMemory")}")
            appendLine("Раздел data: ${mb("dataAvailableBytes")} свободно из ${mb("dataTotalBytes")}")
            appendLine("Swap: ${j.optString("swaps").trim()}")
            val z = j.optJSONObject("zram") ?: JSONObject()
            appendLine("ZRAM: ${z.optString("status", "нет данных")} ${z.optString("device")}")
            if (z.has("disksizeBytes") && !z.isNull("disksizeBytes")) appendLine("ZRAM размер: ${formatBytes(z.optLong("disksizeBytes"))}")
            appendLine("ZRAM mm_stat: ${z.optString("mmStat", "нет данных")}")
            appendLine()
            appendLine("ТЕМПЕРАТУРА")
            val temps = j.optJSONArray("temperatures") ?: JSONArray()
            if (temps.length() == 0) appendLine("Датчики не обнаружены или закрыты для приложений")
            for (i in 0 until temps.length()) {
                val t = temps.optJSONObject(i) ?: continue
                appendLine("${t.optString("zone")} (${t.optString("type")}): ${String.format(Locale.US, "%.1f°C", t.optDouble("celsius"))}")
            }
            appendLine()
            appendLine("ЗАПУЩЕННЫЕ ПРОЦЕССЫ")
            val processes = j.optJSONArray("runningProcesses") ?: JSONArray()
            appendLine("Найдено: ${processes.length()} (показаны доступные приложению)")
            for (i in 0 until minOf(processes.length(), 25)) {
                val proc = processes.optJSONObject(i) ?: continue
                val pss = if (proc.has("pssKb")) " • ${proc.optInt("pssKb")} КБ PSS" else ""
                appendLine("${proc.optString("processName")} [PID ${proc.optInt("pid")}] ${proc.optString("importanceLabel")}$pss")
            }
            appendLine()
            appendLine("УСТАНОВЛЕННЫЕ ПРИЛОЖЕНИЯ")
            val packages = j.optJSONArray("installedPackages") ?: JSONArray()
            appendLine("Пакетов найдено: ${packages.length()}")
            for (i in 0 until minOf(packages.length(), 80)) {
                val pkg = packages.optJSONObject(i) ?: continue
                val kind = if (pkg.optBoolean("systemApp")) "системное" else "пользовательское"
                val enabled = if (pkg.optBoolean("enabled")) "включено" else "отключено"
                appendLine("${pkg.optString("appName")} • ${pkg.optString("packageName")} • $kind • $enabled")
            }
            appendLine()
            appendLine("НАКОПИТЕЛЬ И РАЗДЕЛЫ")
  val part = j.optJSONObject("partitionInfo") ?: JSONObject()
  val devices = part.optJSONArray("blockDevices") ?: JSONArray()
  appendLine("Блочных устройств: ${devices.length()}")
            appendLine("Записей by-name: ${(part.optJSONArray("byNameEntries") ?: JSONArray()).length()}")
            appendLine("Содержимое разделов не читалось и не изменялось")
            val boot = j.optJSONObject("bootInfo") ?: JSONObject()
            val bootProps = boot.optJSONObject("bootProperties") ?: JSONObject()
            appendLine("Bootloader: ${bootProps.optString("ro.boot.bootloader", "нет данных")}")
            val security = j.optJSONObject("securityInfo") ?: JSONObject()
            val sec = security.optJSONObject("properties") ?: JSONObject()
            appendLine("Verified Boot: ${sec.optString("ro.boot.verifiedbootstate", "нет данных")}")
            appendLine("Шифрование: ${sec.optString("ro.crypto.state", "нет данных")} / ${sec.optString("ro.crypto.type", "нет данных")}")
            appendLine("SELinux enforce: ${security.optString("selinuxEnforce", "нет данных")}")
  appendLine()
  appendLine("ЭКРАН")
            appendLine("${j.optString("display")} • ${j.optInt("densityDpi")} dpi")
            appendLine()
            appendLine("ROOT")
            appendLine("Статус: ${j.optString("rootStatus")}")
            if (j.has("rootOutput")) appendLine("Ответ: ${j.optString("rootOutput")}")
            appendLine()
            appendLine("ЯДРО")
            appendLine(j.optString("kernel").take(220))
            appendLine()
            appendLine("Примечание: недоступные sysfs/procfs параметры не означают отсутствие функции — прошивка может закрывать доступ.")
        }
    }

    private fun formatMHz(j: JSONObject, key: String): String {
        if (j.isNull(key)) return "?"
        return String.format(Locale.US, "%.0f", j.optDouble(key) / 1000.0)
    }

    private fun formatBytes(bytes: Long): String =
        String.format(Locale.US, "%.0f МБ", bytes / 1048576.0)

    private fun readNumber(path: String): Long? =
        readTextOrNull(path)?.trim()?.toLongOrNull()

    private fun readTextOrNull(path: String): String? =
        try { File(path).takeIf { it.canRead() }?.readText()?.take(8000) } catch (_: Exception) { null }

    private fun readText(path: String, max: Int = 8000): String =
        readTextOrNull(path)?.take(max) ?: "недоступно"

    private fun java.lang.Process.waitForWithTimeout(timeoutMs: Long): Boolean {
        val start = System.currentTimeMillis()
        while (System.currentTimeMillis() - start < timeoutMs) {
            try { exitValue(); return true } catch (_: IllegalThreadStateException) {}
            Thread.sleep(100)
        }
        return false
    }

    override fun onDestroy() {
        try { backupServer?.close() } catch (_: Exception) { }
        backupServer = null
        super.onDestroy()
        executor.shutdownNow()
    }
}
