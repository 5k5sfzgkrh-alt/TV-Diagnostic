from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path("project")
SRC=ROOT/"app/src/main/java/com/tvdiagnostic/hi3751/MainActivity.kt"
GRADLE=ROOT/"app/build.gradle.kts"
MANIFEST=ROOT/"app/src/main/AndroidManifest.xml"
s=SRC.read_text(encoding="utf-8")

# Repair inherited v1.3.3 legacy archive HTTP handler before compiling.
legacy_start=s.find("    private fun startLegacyArchiveHttpServer")
legacy_end=s.find("    private fun confirmSystemVendorBackup", legacy_start)
if legacy_start < 0 or legacy_end < 0 or legacy_end <= legacy_start:
    raise SystemExit("Legacy archive HTTP handler anchors not found")
legacy=s[legacy_start:legacy_end]
if legacy.count(r'\\r\\n') != 11 or legacy.count(r'\\n') != 18:
    raise SystemExit("Legacy HTTP escape count changed; refusing broad replacement")
legacy=legacy.replace(r'\\r\\n', r'\r\n').replace(r'\\n', r'\n')
bad_header=r'filename=\\"$filename\\"'
if legacy.count(bad_header) != 1:
    raise SystemExit("Legacy Content-Disposition quote anchor mismatch")
legacy=legacy.replace(bad_header, r'filename=\"$filename\"')
bad_scope='''                        if (request.startsWith("GET /download?token=$token HTTP/")) {
                            val out = client.getOutputStream()'''
good_scope='''                        val out = client.getOutputStream()
                        if (request.startsWith("GET /download?token=$token HTTP/")) {'''
if legacy.count(bad_scope) != 1:
    raise SystemExit("Legacy HTTP output-stream scope anchor mismatch")
legacy=legacy.replace(bad_scope, good_scope)
s=s[:legacy_start]+legacy+s[legacy_end:]
g=GRADLE.read_text(encoding="utf-8")
if 'versionCode = 160' not in g or 'versionName = "1.6.0"' not in g:
    raise SystemExit("Not a v1.6.0 source tree")

# Fix the known over-escaped root-detection regex, and make the root probe use su 0 id.
s=s.replace(r'Regex("uid=0(?:\\\\(|\\\\s|$)")', r'Regex("uid=0(?:\\(|\\s|$)")')
s=s.replace('ProcessBuilder("su", "-c", "id")', 'ProcessBuilder("su", "0", "id")')
s=s.replace("1.5.0", "1.6.0").replace("tv-diagnostic-report-v150.json", "tv-diagnostic-report-v160.json")

# Add explicit controls to the existing v1.5 main screen.
if "startLanTransferServer()" not in s:
    anchor='        outer.addView(backupTitle)'
    if s.count(anchor)!=1: raise SystemExit("Main-screen anchor mismatch")
    s=s.replace(anchor,anchor+'''
        val lanButtons = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        lanButtons.addView(makeButton("Передача файлов по Wi-Fi") { startLanTransferServer() })
        lanButtons.addView(makeButton("Остановить сервер") { stopLanTransferServer() })
        outer.addView(lanButtons)
''',1)

marker='    private fun reportJsonText(): String {'
if s.count(marker)!=1: raise SystemExit("Report method anchor mismatch")
server=r'''
    @Volatile private var lanSocket: java.net.ServerSocket? = null
    @Volatile private var lanThread: Thread? = null
    @Volatile private var lanToken: String = ""

    private fun lanFiles(): List<File> {
        val root=getExternalFilesDir(Environment.DIRECTORY_DOCUMENTS) ?: File(filesDir,"Documents")
        val dirs=listOf(root,File(root,"Backup")).filter { it.isDirectory }
        val extensions=setOf("img","zip","json","txt","sha256","bin")
        return dirs.flatMap { d -> d.listFiles()?.filter { f ->
            f.isFile && !f.name.endsWith(".tmp") && f.extension.lowercase(java.util.Locale.ROOT) in extensions &&
            try { f.canonicalPath.startsWith(d.canonicalPath+File.separator) } catch (_:Exception) { false }
        } ?: emptyList() }.distinctBy { it.canonicalPath }.sortedBy { it.name }
    }

    private fun lanIp(): String = try {
        val wm=applicationContext.getSystemService(android.content.Context.WIFI_SERVICE) as android.net.wifi.WifiManager
        val ip=wm.connectionInfo.ipAddress
        if(ip==0) "IP не определён" else
            listOf(ip and 255,ip shr 8 and 255,ip shr 16 and 255,ip shr 24 and 255).joinToString(".")
    } catch (_:Exception) { "IP не определён" }

    private fun startLanTransferServer() {
        if(lanThread?.isAlive==true) {
            statusView.text="Сервер уже запущен на порту " + (lanSocket?.localPort ?: 0)
            return
        }
        try {
            val root=getExternalFilesDir(Environment.DIRECTORY_DOCUMENTS) ?: File(filesDir,"Documents")
            if(!root.exists() && !root.mkdirs()) throw IllegalStateException("Не удалось создать Documents")
            lanToken=java.util.UUID.randomUUID().toString().replace("-","")
            val token=lanToken
            val ss=java.net.ServerSocket(0,8,java.net.InetAddress.getByName("0.0.0.0"))
            ss.soTimeout=1000
            lanSocket=ss
            lanThread=Thread({
                while(!Thread.currentThread().isInterrupted && !ss.isClosed) {
                    try {
                        val client=ss.accept()
                        Thread({ serveLanClient(client,token) },"TV-LAN-client").start()
                    } catch (_:java.net.SocketTimeoutException) {
                    } catch (_:Exception) { break }
                }
            },"TV-LAN-server").apply { isDaemon=true; start() }
            runOnUiThread {
                statusView.text="Локальный сервер запущен. На iPhone в той же Wi-Fi сети открой:\nhttp://" +
                    lanIp() + ":" + ss.localPort + "/?token=" + token +
                    "\nСервер показывает только файлы из Documents и Documents/Backup. Останови его после скачивания."
            }
        } catch(e:Exception) {
            stopLanTransferServer()
            statusView.text="Ошибка LAN-сервера: " + (e.message ?: e.javaClass.simpleName)
        }
    }

    private fun stopLanTransferServer() {
        try { lanSocket?.close() } catch (_:Exception) {}
        lanSocket=null
        lanThread?.interrupt()
        lanThread=null
        lanToken=""
    }

    private fun serveLanClient(client:java.net.Socket,token:String) {
        client.use { sock ->
            sock.soTimeout=15000
            val reader=sock.getInputStream().bufferedReader(Charsets.US_ASCII)
            val request=reader.readLine() ?: return
            val headers=mutableMapOf<String,String>()
            while(true) {
                val line=reader.readLine() ?: break
                if(line.isEmpty()) break
                val ix=line.indexOf(':')
                if(ix>0) headers[line.substring(0,ix).trim().lowercase(java.util.Locale.ROOT)]=line.substring(ix+1).trim()
            }
            val parts=request.split(" ")
            if(parts.size<2) return
            val method=parts[0]
            if(method!="GET" && method!="HEAD") {
                lanReply(sock,405,"Method Not Allowed","text/plain",ByteArray(0),method=="HEAD"); return
            }
            val uri=try { java.net.URI("http://localhost"+parts[1]) } catch (_:Exception) {
                lanReply(sock,400,"Bad Request","text/plain",ByteArray(0),method=="HEAD"); return
            }
            val q=uri.rawQuery.orEmpty().split("&").mapNotNull { v ->
                val a=v.split("=",limit=2); if(a.size==2) a[0] to a[1] else null
            }.toMap()
            val supplied=try { java.net.URLDecoder.decode(q["token"].orEmpty(),"UTF-8") } catch (_:Exception) { "" }
            if(!java.security.MessageDigest.isEqual(supplied.toByteArray(),token.toByteArray())) {
                lanReply(sock,403,"Forbidden","text/plain",ByteArray(0),method=="HEAD"); return
            }
            if(uri.path=="/" || uri.path=="/index") {
                val html=buildString {
                    append("<meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><h2>TV Diagnostic 1.6.0</h2><p>Локальная передача, только чтение.</p><ul>")
                    lanFiles().forEach { f ->
                        val n=java.net.URLEncoder.encode(f.name,"UTF-8").replace("+","%20")
                        append("<li><a href='/file/").append(n).append("?token=").append(token).append("'>")
                        append(f.name.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"))
                        append("</a> — ").append(f.length()).append(" байт</li>")
                    }
                    append("</ul>")
                }.toByteArray(Charsets.UTF_8)
                lanReply(sock,200,"OK","text/html; charset=utf-8",html,method=="HEAD"); return
            }
            if(!uri.path.startsWith("/file/")) {
                lanReply(sock,404,"Not Found","text/plain",ByteArray(0),method=="HEAD"); return
            }
            val name=try { java.net.URLDecoder.decode(uri.path.removePrefix("/file/"),"UTF-8") } catch (_:Exception) { "" }
            val file=lanFiles().firstOrNull { it.name==name }
            if(file==null) { lanReply(sock,404,"Not Found","text/plain",ByteArray(0),method=="HEAD"); return }
            val size=file.length()
            var start=0L
            var end=size-1
            var partial=false
            val range=headers["range"]
            if(range!=null && range.startsWith("bytes=") && size>0) {
                try {
                    val b=range.removePrefix("bytes=").substringBefore(",").split("-",limit=2)
                    start=if(b[0].isEmpty()) (size-b[1].toLong()).coerceAtLeast(0) else b[0].toLong()
                    if(b[0].isNotEmpty() && b.getOrNull(1).orEmpty().isNotEmpty()) end=b[1].toLong()
                    if(start<0 || start>=size || end<start) {
                        val o=sock.getOutputStream()
                        o.write(("HTTP/1.1 416 Range Not Satisfiable\r\nContent-Range: bytes */"+size+"\r\nContent-Length: 0\r\nConnection: close\r\n\r\n").toByteArray())
                        o.flush(); return
                    }
                    end=end.coerceAtMost(size-1); partial=true
                } catch (_:Exception) { lanReply(sock,400,"Bad Request","text/plain",ByteArray(0),method=="HEAD"); return }
            }
            val count=if(size==0L) 0L else end-start+1
            val out=sock.getOutputStream()
            val head=StringBuilder("HTTP/1.1 ").append(if(partial) "206 Partial Content" else "200 OK").append("\r\n")
                .append("Content-Type: application/octet-stream\r\nAccept-Ranges: bytes\r\nContent-Length: ").append(count)
                .append("\r\nConnection: close\r\n")
            if(partial) head.append("Content-Range: bytes ").append(start).append("-").append(end).append("/").append(size).append("\r\n")
            head.append("\r\n")
            out.write(head.toString().toByteArray(Charsets.US_ASCII))
            if(method=="GET" && count>0) java.io.RandomAccessFile(file,"r").use { raf ->
                raf.seek(start); val buf=ByteArray(65536); var left=count
                while(left>0) {
                    val n=raf.read(buf,0,minOf(buf.size.toLong(),left).toInt())
                    if(n<0) break
                    out.write(buf,0,n); left-=n
                }
            }
            out.flush()
        }
    }

    private fun lanReply(sock:java.net.Socket,code:Int,reason:String,type:String,body:ByteArray,head:Boolean) {
        try {
            val out=sock.getOutputStream()
            out.write(("HTTP/1.1 "+code+" "+reason+"\r\nContent-Type: "+type+"\r\nContent-Length: "+body.size+"\r\nConnection: close\r\n\r\n").toByteArray(Charsets.US_ASCII))
            if(!head) out.write(body)
            out.flush()
        } catch (_:Exception) {}
    }

'''
s=s.replace(marker,server+marker,1)
ET.register_namespace("android","http://schemas.android.com/apk/res/android")
tree=ET.parse(MANIFEST)
root=tree.getroot()
ns="{http://schemas.android.com/apk/res/android}"
for permission in ("android.permission.INTERNET","android.permission.ACCESS_WIFI_STATE"):
    if not any(x.get(ns+"name")==permission for x in root.findall("uses-permission")):
        e=ET.Element("uses-permission"); e.set(ns+"name",permission); root.insert(0,e)
tree.write(MANIFEST,encoding="utf-8",xml_declaration=True)
SRC.write_text(s,encoding="utf-8")
print("Applied v1.6.0 local LAN server: token, app-private file allowlist, GET/HEAD, streaming and HTTP Range.")
