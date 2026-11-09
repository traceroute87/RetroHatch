package app.retrohatch.rotate.model

import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import java.security.MessageDigest

class DownloadException(message: String) : Exception(message)
class DownloadCancelled : Exception("Cancelled")

/**
 * HTTPS download with size and SHA-256 verification. Same rules as the Nano's core/rh_net.c:
 *  - https only, including redirects (an https -> http redirect is refused); the platform checks the certificate and host name (never overridden)
 *  - the size in the signed catalog is binding: a different Content-Length, or more bytes than that, is refused
 *  - bytes go to `<dest>.part` and are hashed while they arrive; only a file whose SHA-256 equals the signed one is renamed to `dest`
 *  - progress callback, cooperative cancel; any failure removes the partial file
 * [open] and [mapUrl] are seams: tests inject a fake connection, DEBUG builds map the fixture host (DevHooks) to the local test server.
 */
class Downloader(
    private val open: (URL) -> HttpURLConnection = { it.openConnection() as HttpURLConnection },
    private val mapUrl: (String) -> String = { it },
    private val connectMs: Int = 15000, private val readMs: Int = 15000, private val totalMs: Long = 10 * 60_000L,
) {
    companion object { const val MAX_REDIRECTS = 5 }

    private fun httpsUrl(s: String): URL {
        if (!s.startsWith("https://") || s.any { it <= ' ' || it.code >= 0x7f || it == '\\' }) throw DownloadException("Only https:// links are allowed")
        val u = try { URI(s) } catch (e: Exception) { throw DownloadException("Only https:// links are allowed") }
        if (u.host.isNullOrEmpty() || u.userInfo != null) throw DownloadException("Only https:// links are allowed")
        return URL(s)
    }

    /** Open `url` (after the fixture mapping), follow https->https redirects, return the connection of the final 200 reply. */
    private fun open200(url: String): HttpURLConnection {
        var cur = httpsUrl(url)
        var hop = 0
        while (true) {
            if (hop++ > MAX_REDIRECTS) throw DownloadException("Too many redirects")
            val c = open(httpsUrl(mapUrl(cur.toString())))
            c.instanceFollowRedirects = false
            c.connectTimeout = connectMs; c.readTimeout = readMs
            c.setRequestProperty("User-Agent", "RetroHatch-Android/1")
            c.setRequestProperty("Accept-Encoding", "identity")
            val code = try { c.responseCode } catch (e: IOException) { throw DownloadException(netMessage(e)) }
            if (code in 300..399 && code != 304 && code != 300) {
                val loc = c.getHeaderField("Location") ?: throw DownloadException("Bad redirect")
                c.disconnect()
                val next = try { cur.toURI().resolve(loc).toString() } catch (e: Exception) { throw DownloadException("Bad redirect") }
                if (!next.startsWith("https://")) throw DownloadException("Redirect to a non-https link refused")
                cur = httpsUrl(next)
                continue
            }
            if (code != 200) { c.disconnect(); throw DownloadException(if (code == 404) "Not found on the server (404)" else "Server error (HTTP $code)") }
            val enc = c.getHeaderField("Content-Encoding")
            if (enc != null && !enc.equals("identity", true)) { c.disconnect(); throw DownloadException("Unsupported encoding") }
            return c
        }
    }

    /** A small document (the signed catalog and its signature) into memory. Same https/redirect rules; more than [maxBytes] is refused. */
    fun fetch(url: String, maxBytes: Int): ByteArray {
        val c = open200(url)
        try {
            val len = c.getHeaderField("Content-Length")?.toLongOrNull()
            if (len != null && len > maxBytes) throw DownloadException("Reply is larger than allowed")
            val out = java.io.ByteArrayOutputStream()
            val buf = ByteArray(8192)
            val deadline = System.nanoTime() + totalMs * 1_000_000L
            c.inputStream.use { ins ->
                while (true) {
                    if (System.nanoTime() > deadline) throw DownloadException("Download took too long")
                    val n = try { ins.read(buf) } catch (e: IOException) { throw DownloadException(netMessage(e)) }
                    if (n < 0) break
                    if (out.size() + n > maxBytes) throw DownloadException("Reply is larger than allowed")
                    out.write(buf, 0, n)
                }
            }
            return out.toByteArray()
        } finally { c.disconnect() }
    }

    fun download(url: String, dest: File, expectedSize: Long, expectedSha256: String, cancelled: () -> Boolean, progress: (Long, Long) -> Unit): File {
        if (expectedSize < 1 || expectedSha256.length != 64) throw DownloadException("Bad request")
        val part = File(dest.path + ".part")
        dest.parentFile?.mkdirs()
        val deadline = System.nanoTime() + totalMs * 1_000_000L
        try {
            val c = open200(url)
            val len = c.getHeaderField("Content-Length")?.toLongOrNull()
            if (len != null && len != expectedSize) { c.disconnect(); throw DownloadException("Size differs from the catalog") }
            val md = MessageDigest.getInstance("SHA-256")
            var got = 0L
            try {
                c.inputStream.use { ins -> part.outputStream().use { out ->
                    val buf = ByteArray(32 * 1024)
                    var last = 0L
                    progress(0, expectedSize)
                    while (true) {
                        if (cancelled()) throw DownloadCancelled()
                        if (System.nanoTime() > deadline) throw DownloadException("Download took too long")
                        val n = try { ins.read(buf) } catch (e: IOException) { throw DownloadException(netMessage(e)) }
                        if (n < 0) break
                        got += n
                        if (got > expectedSize) throw DownloadException("File is larger than the catalog says")
                        out.write(buf, 0, n); md.update(buf, 0, n)
                        val now = System.nanoTime()
                        if (now - last > 100_000_000L) { last = now; progress(got, expectedSize) }
                    }
                } }
            } finally { c.disconnect() }
            if (got != expectedSize) throw DownloadException("Download was cut short")
            val digest = md.digest().joinToString("") { "%02x".format(it) }
            if (digest != expectedSha256) throw DownloadException("SHA-256 mismatch: file rejected")
            if (!part.renameTo(dest)) throw DownloadException("Cannot write to storage")
            progress(got, expectedSize)
            return dest
        } finally {
            part.delete()   // no-op after a successful rename
        }
    }

    private fun netMessage(e: IOException): String = when (e) {
        is javax.net.ssl.SSLHandshakeException -> "Certificate not trusted or TLS handshake failed"
        is javax.net.ssl.SSLException -> "TLS error: ${e.message}"
        is java.net.SocketTimeoutException -> "Connection stalled"
        is java.net.UnknownHostException -> "Cannot reach the server (offline?)"
        else -> "Connection error"
    }
}

object Sha {
    fun ofFile(f: File): String {
        val md = MessageDigest.getInstance("SHA-256")
        f.inputStream().use { ins -> val b = ByteArray(64 * 1024); while (true) { val n = ins.read(b); if (n < 0) break; md.update(b, 0, n) } }
        return md.digest().joinToString("") { "%02x".format(it) }
    }
}
