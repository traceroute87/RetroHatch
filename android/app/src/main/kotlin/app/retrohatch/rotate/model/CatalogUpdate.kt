package app.retrohatch.rotate.model

/** The online catalog: the same signed index the Nano uses (tools/trust.py build + sign), published on GitHub Pages. */
object CatalogConfig {
    const val BASE = "https://traceroute87.github.io/RetroHatch/catalog/"
    const val INDEX_URL = BASE + "index.json"
    const val SIG_URL = BASE + "index.json.sig"
}

/**
 * Production and DEV trust never mix: a catalog verified by a production key is cached and rollback-tracked under PROD, one verified by a
 * DEV fixture key (debug builds only) under DEV. A DEV catalog can never satisfy, replace or advance the production state, and vice versa.
 */
enum class KeyClass(val dir: String) { PROD("prod"), DEV("dev") }

data class RefreshStatus(val atMs: Long, val ok: Boolean, val text: String)

/** Where the last valid signed catalog, its rollback state and the last refresh outcome live. Android: app-private files + SharedPreferences. */
interface CatalogStore {
    fun readCache(c: KeyClass): Pair<ByteArray, ByteArray>?
    /** Must be atomic: a crash or a full disk may never leave a half-written cache (the previous one stays). */
    fun writeCache(c: KeyClass, index: ByteArray, sig: ByteArray)
    fun state(c: KeyClass): TrustState?
    fun setState(c: KeyClass, s: TrustState)
    fun status(): RefreshStatus?
    fun setStatus(s: RefreshStatus)
}

sealed class RefreshResult {
    data class Updated(val serial: Long, val dev: Boolean) : RefreshResult()
    data class UpToDate(val serial: Long, val dev: Boolean) : RefreshResult()
    /** Downloaded fine, but not acceptable (signature, rollback, policy). The previous catalog is kept. */
    data class Rejected(val reason: String) : RefreshResult()
    /** Could not get it (offline, HTTP error ...). The previous catalog is kept. */
    data class Failed(val reason: String) : RefreshResult()
}

/**
 * Fetch -> verify -> cache. Nothing is shown, trusted or stored before the Ed25519 signature, the canonical form, every publish gate and the
 * rollback rule have passed. Any failure leaves the previous cache and state untouched.
 */
class CatalogUpdater(
    private val fetch: (url: String, maxBytes: Int) -> ByteArray,
    private val store: CatalogStore,
    private val prodKeys: List<String> = Trust.PRODUCTION_KEYS,
    private val devKeys: List<String> = emptyList(),
    private val now: () -> Long = { System.currentTimeMillis() },
    private val indexUrl: String = CatalogConfig.INDEX_URL,
    private val sigUrl: String = CatalogConfig.SIG_URL,
) {
    private fun classOf(keyId: String): KeyClass? = when {
        prodKeys.any { Trust.keyId(Trust.unhex(it)) == keyId } -> KeyClass.PROD
        devKeys.any { Trust.keyId(Trust.unhex(it)) == keyId } -> KeyClass.DEV
        else -> null
    }

    fun refresh(): RefreshResult {
        val r = attempt()
        val text = when (r) {
            is RefreshResult.Updated -> "Updated to serial ${r.serial}"
            is RefreshResult.UpToDate -> "Already up to date (serial ${r.serial})"
            is RefreshResult.Rejected -> "Rejected: ${r.reason}. The previous catalog is kept."
            is RefreshResult.Failed -> "Failed: ${r.reason}. The previous catalog is kept."
        }
        store.setStatus(RefreshStatus(now(), r is RefreshResult.Updated || r is RefreshResult.UpToDate, text))
        return r
    }

    private fun attempt(): RefreshResult {
        var verdict: TrustException? = null
        for (round in 1..2) {   // the index and its signature are two requests; if the site changed in between, ask once more
            val sig: ByteArray
            val index: ByteArray
            try {
                sig = fetch(sigUrl, Trust.MAX_SIG)
                index = fetch(indexUrl, Trust.MAX_INDEX)
            } catch (e: DownloadException) {
                return RefreshResult.Failed(e.message ?: "download failed")
            } catch (e: Exception) {
                return RefreshResult.Failed("download failed")
            }
            try {
                val v = Trust.verify(index, sig, prodKeys + devKeys, stateFor = { kid -> classOf(kid)?.let { store.state(it) } },
                    experimentalKeyIds = devKeys.map { Trust.keyId(Trust.unhex(it)) }.toSet())
                val cls = classOf(v.keyId) ?: return RefreshResult.Rejected("unknown signing key")
                val have = store.state(cls)
                val cached = store.readCache(cls)
                if (have == v.state && cached != null && cached.first.contentEquals(index)) return RefreshResult.UpToDate(v.state.serial, cls == KeyClass.DEV)
                store.writeCache(cls, index, sig)          // cache first, then the rollback state: a crash in between only leaves a verified file
                store.setState(cls, v.state)
                return RefreshResult.Updated(v.state.serial, cls == KeyClass.DEV)
            } catch (e: TrustException) {
                verdict = e
                if (e.message != "bad signature") break
            }
        }
        return RefreshResult.Rejected(verdict?.message ?: "not acceptable")
    }
}

/** Startup / reload: the best verified catalog we hold, never an unverified one. */
object CatalogRepository {
    /**
     * Order: production cache, DEV cache (only if DEV keys exist, i.e. debug builds), bundled production snapshot, else the PREVIEW sample.
     * Every candidate is verified again against its own class's keys and rollback state, so a damaged or swapped cache file is dropped.
     */
    fun load(store: CatalogStore, prodKeys: List<String>, devKeys: List<String>, bundled: Pair<ByteArray, ByteArray>?, preview: ByteArray?,
             devBundled: Pair<ByteArray, ByteArray>? = null): LoadedCatalog {
        var why: String? = null
        fun tryOne(c: Pair<ByteArray, ByteArray>?, cls: KeyClass, cached: Boolean, label: String): LoadedCatalog? {
            if (c == null) return null
            val r = CatalogLoader.load(c.first, c.second, preview,
                trusted = if (cls == KeyClass.PROD) prodKeys else emptyList(), devKeys = if (cls == KeyClass.DEV) devKeys else emptyList(), state = store.state(cls))
            val s = r.source
            if (s is CatalogSource.Signed) return LoadedCatalog(s.copy(cached = cached), r.catalog, r.newState)
            if (why == null) why = (s as CatalogSource.Preview).reason.replaceFirst("Signed catalog", "$label catalog")
            return null
        }
        tryOne(store.readCache(KeyClass.PROD), KeyClass.PROD, true, "Cached")?.let { return it }
        if (devKeys.isNotEmpty()) tryOne(store.readCache(KeyClass.DEV), KeyClass.DEV, true, "Cached DEV")?.let { return it }
        tryOne(bundled, KeyClass.PROD, false, "Bundled")?.let { return it }
        if (devKeys.isNotEmpty()) tryOne(devBundled, KeyClass.DEV, false, "Bundled DEV")?.let { return it }   // debug builds ship a signed DEV snapshot of the real-app candidates
        return CatalogLoader.load(null, null, preview).let { LoadedCatalog(CatalogSource.Preview(why ?: (it.source as CatalogSource.Preview).reason), it.catalog) }
    }
}
