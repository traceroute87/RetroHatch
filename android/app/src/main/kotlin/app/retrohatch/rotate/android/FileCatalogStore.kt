package app.retrohatch.rotate.android

import android.content.Context
import app.retrohatch.rotate.model.CatalogStore
import app.retrohatch.rotate.model.KeyClass
import app.retrohatch.rotate.model.RefreshStatus
import app.retrohatch.rotate.model.TrustState
import java.io.DataInputStream
import java.io.DataOutputStream
import java.io.File
import java.io.FileOutputStream

/**
 * Last valid signed catalog (one file per trust class, written to a temp file and renamed so the old one survives any failure), rollback state and
 * last refresh outcome, all in app-private storage. The cache is verified again every time it is loaded, so the files need no extra protection.
 */
class FileCatalogStore(ctx: Context) : CatalogStore {
    private val dir = File(ctx.filesDir, "catalog").also { it.mkdirs() }
    private val prefs = ctx.getSharedPreferences("catalog", Context.MODE_PRIVATE)

    private fun file(c: KeyClass) = File(dir, "${c.dir}.cache")

    override fun readCache(c: KeyClass): Pair<ByteArray, ByteArray>? = try {
        val f = file(c)
        if (!f.isFile) null else DataInputStream(f.inputStream().buffered()).use { ins ->
            val n = ins.readInt()
            if (n < 1 || n > 4096) null else {
                val sig = ByteArray(n).also { ins.readFully(it) }
                Pair(ins.readBytes(), sig)   // (index, signature)
            }
        }
    } catch (e: Exception) { null }

    override fun writeCache(c: KeyClass, index: ByteArray, sig: ByteArray) {
        val tmp = File(dir, "${c.dir}.tmp")
        FileOutputStream(tmp).use { fos ->
            DataOutputStream(fos).apply { writeInt(sig.size); write(sig); write(index); flush() }
            fos.fd.sync()
        }
        if (!tmp.renameTo(file(c))) { tmp.delete(); throw java.io.IOException("cannot replace the catalog cache") }
    }

    override fun state(c: KeyClass): TrustState? =
        if (prefs.contains("serial_${c.dir}")) TrustState(prefs.getLong("serial_${c.dir}", 0), prefs.getString("sha_${c.dir}", "") ?: "") else null

    override fun setState(c: KeyClass, s: TrustState) { prefs.edit().putLong("serial_${c.dir}", s.serial).putString("sha_${c.dir}", s.sha256).commit() }

    override fun status(): RefreshStatus? =
        if (prefs.contains("status_ms")) RefreshStatus(prefs.getLong("status_ms", 0), prefs.getBoolean("status_ok", false), prefs.getString("status_text", "") ?: "") else null

    override fun setStatus(s: RefreshStatus) { prefs.edit().putLong("status_ms", s.atMs).putBoolean("status_ok", s.ok).putString("status_text", s.text).commit() }
}
