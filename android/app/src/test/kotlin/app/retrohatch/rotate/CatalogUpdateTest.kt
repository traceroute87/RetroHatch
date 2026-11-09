package app.retrohatch.rotate

import app.retrohatch.rotate.model.CatalogRepository
import app.retrohatch.rotate.model.CatalogSource
import app.retrohatch.rotate.model.CatalogStore
import app.retrohatch.rotate.model.CatalogUpdater
import app.retrohatch.rotate.model.DeviceFilter
import app.retrohatch.rotate.model.DownloadException
import app.retrohatch.rotate.model.KeyClass
import app.retrohatch.rotate.model.RefreshResult
import app.retrohatch.rotate.model.RefreshStatus
import app.retrohatch.rotate.model.StrictJson
import app.retrohatch.rotate.model.Targets
import app.retrohatch.rotate.model.Trust
import app.retrohatch.rotate.model.TrustState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

private class MemStore : CatalogStore {
    val cache = HashMap<KeyClass, Pair<ByteArray, ByteArray>>()
    val states = HashMap<KeyClass, TrustState>()
    var st: RefreshStatus? = null
    var writes = 0
    override fun readCache(c: KeyClass) = cache[c]
    override fun writeCache(c: KeyClass, index: ByteArray, sig: ByteArray) { writes++; cache[c] = index to sig }
    override fun state(c: KeyClass) = states[c]
    override fun setState(c: KeyClass, s: TrustState) { states[c] = s }
    override fun status() = st
    override fun setStatus(s: RefreshStatus) { st = s }
}

/** Signed catalog documents for tests: one device (rg-rotate), apps with an APK for it, signed by a throwaway key. */
private class Catalogs(val key: TestKey) {
    private val rotate = mapOf("schema" to 1L, "id" to "rg-rotate", "name" to "RG Rotate", "adapter" to "android-packageinstaller", "package_format" to "apk",
        "display" to mapOf("w" to 720L, "h" to 720L), "firmware" to listOf("android-12"))
    private val nano = mapOf("schema" to 1L, "id" to "rg-nano", "name" to "Nano", "adapter" to "opk-funkeyos", "package_format" to "opk", "firmware" to listOf("funkeyos-drum78"))

    fun app(id: String, device: String = "rg-rotate"): Pair<Map<String, Any?>, Map<String, Any?>> {
        val sha = Trust.sha256Hex(id.toByteArray()); val apk = device == "rg-rotate"
        val base = "https://github.com/acme/$id"
        val art = mapOf("device" to device, "firmware" to if (apk) "android-12" else "funkeyos-drum78", "format" to if (apk) "apk" else "opk", "status" to "available", "version" to "1.0",
            "url" to "$base/releases/download/v1/f.${if (apk) "apk" else "opk"}", "sha256" to sha, "size" to 1000L,
            "compatibility" to mapOf("level" to "verified", "evidence" to listOf(mapOf("sha256" to sha, "date" to "2026-11-01", "tester" to "t")))) +
            (if (apk) mapOf("android" to mapOf("package" to "app.acme.$id".replace("-", "_"), "version_code" to 1L, "signer_sha256" to listOf("cd".repeat(32))))
             else mapOf("install" to mapOf("dest_name" to "$id.opk")))
        val a = mapOf("schema" to 1L, "id" to id, "name" to id.replaceFirstChar { it.uppercase() }, "description" to "d", "developer" to "acme", "source" to base,
            "license" to "MIT", "category" to "utility", "artifacts" to listOf(art))
        val ap = mapOf("app" to id, "device" to device, "firmware" to art["firmware"], "sha256" to sha, "size" to 1000L, "release" to "$base/releases/tag/v1", "approved_by" to "me", "date" to "2026-11-02")
        return a to ap
    }

    /** Returns (index, signature). */
    fun build(serial: Long, vararg ids: String, nanoOnly: Boolean = false, signer: TestKey = key): Pair<ByteArray, ByteArray> {
        val entries = ids.map { app(it, if (nanoOnly) "rg-nano" else "rg-rotate") }
        val doc = mapOf("format" to 1L, "serial" to serial, "generated" to "2026-11-09", "devices" to listOf(rotate, nano), "apps" to entries.map { it.first },
            "approvals" to entries.map { it.second }, "revoked" to emptyList<Any?>())
        val idx = StrictJson.canonical(doc)
        return idx to signer.sign(idx)
    }
}

class CatalogUpdateTest {
    private val prod = TestKey()
    private val dev = TestKey()
    private val cats = Catalogs(prod)
    private val preview = repo("android/app/src/main/assets/preview/index.json").readBytes()

    /** A scripted "server": url -> bytes, or an exception to throw. */
    private class Server(var index: ByteArray, var sig: ByteArray, var down: String? = null, var calls: Int = 0) {
        fun fetch(url: String, max: Int): ByteArray {
            calls++
            down?.let { throw DownloadException(it) }
            val b = if (url.endsWith(".sig")) sig else index
            if (b.size > max) throw DownloadException("Reply is larger than allowed")
            return b
        }
    }

    private fun updater(store: MemStore, server: Server, prodKeys: List<String> = listOf(prod.pubHex), devKeys: List<String> = emptyList()) =
        CatalogUpdater(server::fetch, store, prodKeys, devKeys, now = { 1_700_000_000_000L })

    private fun serverFor(p: Pair<ByteArray, ByteArray>) = Server(p.first, p.second)

    @Test fun successfulRefreshIsVerifiedCachedAndShown() {
        val store = MemStore(); val srv = serverFor(cats.build(1, "alpha", "beta"))
        val r = updater(store, srv).refresh()
        assertEquals(RefreshResult.Updated(1, false), r)
        assertNotNull(store.cache[KeyClass.PROD]); assertEquals(1L, store.states[KeyClass.PROD]!!.serial)
        assertTrue(store.st!!.ok); assertEquals("Updated to serial 1", store.st!!.text)
        val loaded = CatalogRepository.load(store, listOf(prod.pubHex), emptyList(), null, preview)
        val s = loaded.source as CatalogSource.Signed
        assertTrue(s.cached); assertFalse(s.dev)
        assertEquals(listOf("Alpha", "Beta"), DeviceFilter.forDevice(loaded.catalog, Targets.RG_ROTATE).map { it.app.name })
    }

    @Test fun sameCatalogAgainIsUpToDateAndNewerSerialReplacesIt() {
        val store = MemStore(); val srv = serverFor(cats.build(1, "alpha")); val u = updater(store, srv)
        u.refresh(); val w = store.writes
        assertEquals(RefreshResult.UpToDate(1, false), u.refresh()); assertEquals(w, store.writes)
        srv.index = cats.build(2, "alpha", "gamma").first; srv.sig = cats.build(2, "alpha", "gamma").second
        // canonical JSON is deterministic and Ed25519 is deterministic, so rebuild once and use the pair
        val p2 = cats.build(2, "alpha", "gamma"); srv.index = p2.first; srv.sig = p2.second
        assertEquals(RefreshResult.Updated(2, false), u.refresh())
        assertEquals(2L, store.states[KeyClass.PROD]!!.serial)
    }

    private fun primed(): Triple<MemStore, Server, CatalogUpdater> {
        val store = MemStore(); val srv = serverFor(cats.build(5, "alpha")); val u = updater(store, srv)
        assertTrue(u.refresh() is RefreshResult.Updated)
        return Triple(store, srv, u)
    }

    private fun assertKept(store: MemStore, before: Pair<ByteArray, ByteArray>) {
        assertTrue("cache untouched", store.cache[KeyClass.PROD]!!.first.contentEquals(before.first) && store.cache[KeyClass.PROD]!!.second.contentEquals(before.second))
        assertEquals(5L, store.states[KeyClass.PROD]!!.serial)
        val loaded = CatalogRepository.load(store, listOf(prod.pubHex), emptyList(), null, preview)
        assertEquals("the last valid catalog is still what the app shows", 5L, (loaded.source as CatalogSource.Signed).serial)
    }

    @Test fun invalidSignatureIsRejectedAndTheCacheSurvives() {
        val (store, srv, u) = primed(); val before = store.cache[KeyClass.PROD]!!
        val good = cats.build(6, "alpha")
        val badSig = Trust.sha256Hex(good.second).let { String(good.second).replace("\"sig\":\"", "\"sig\":\"A") }   // corrupt the signature bytes
        srv.index = good.first; srv.sig = badSig.toByteArray()
        val r = u.refresh()
        assertTrue(r is RefreshResult.Rejected)
        assertFalse(store.st!!.ok); assertTrue(store.st!!.text.contains("previous catalog is kept"))
        assertKept(store, before)
    }

    @Test fun tamperedIndexAndUnknownKeyAreRejectedAndTheCacheSurvives() {
        val (store, srv, u) = primed(); val before = store.cache[KeyClass.PROD]!!
        val good = cats.build(6, "alpha")
        srv.index = good.first.copyOf().also { it[good.first.size / 2] = (it[good.first.size / 2].toInt() xor 1).toByte() }; srv.sig = good.second
        assertEquals(RefreshResult.Rejected("bad signature"), u.refresh()); assertKept(store, before)
        val foreign = cats.build(6, "alpha", signer = TestKey())
        srv.index = foreign.first; srv.sig = foreign.second
        assertEquals(RefreshResult.Rejected("unknown signing key"), u.refresh()); assertKept(store, before)
    }

    @Test fun rollbackAndForkAreRejected() {
        val (store, srv, u) = primed(); val before = store.cache[KeyClass.PROD]!!
        val old = cats.build(4, "alpha"); srv.index = old.first; srv.sig = old.second
        assertEquals(RefreshResult.Rejected("rollback: serial 4 < 5"), u.refresh()); assertKept(store, before)
        val fork = cats.build(5, "alpha", "extra"); srv.index = fork.first; srv.sig = fork.second     // same serial, different content
        assertEquals(RefreshResult.Rejected("same serial, different content"), u.refresh()); assertKept(store, before)
    }

    @Test fun offlineOrServerErrorKeepsTheCachedCatalogForOfflineUse() {
        val (store, srv, u) = primed(); val before = store.cache[KeyClass.PROD]!!
        for (why in listOf("Cannot reach the server (offline?)", "Server error (HTTP 503)", "Not found on the server (404)", "Certificate not trusted or TLS handshake failed")) {
            srv.down = why
            assertEquals(RefreshResult.Failed(why), u.refresh())
            assertKept(store, before)
        }
        assertTrue(store.st!!.text.startsWith("Failed:"))
    }

    @Test fun oversizedReplyIsRefused() {
        val store = MemStore(); val big = ByteArray(Trust.MAX_INDEX + 1)
        val r = updater(store, Server(big, big)).refresh()
        assertTrue(r is RefreshResult.Failed); assertNull(store.cache[KeyClass.PROD])
    }

    @Test fun nothingCachedAndNothingPublishedMeansPreview() {
        val store = MemStore()
        val loaded = CatalogRepository.load(store, listOf(prod.pubHex), emptyList(), null, preview)
        assertTrue((loaded.source as CatalogSource.Preview).reason.contains("No signed Android catalog"))
        assertTrue(loaded.catalog.apps.isNotEmpty())    // the labelled sample
    }

    @Test fun aDamagedCacheIsDroppedNotTrusted() {
        val (store, _, _) = primed()
        val c = store.cache[KeyClass.PROD]!!
        store.cache[KeyClass.PROD] = c.first.copyOf().also { it[10] = (it[10].toInt() xor 1).toByte() } to c.second
        val loaded = CatalogRepository.load(store, listOf(prod.pubHex), emptyList(), null, preview)
        val src = loaded.source as CatalogSource.Preview
        assertTrue(src.reason, src.reason.contains("Cached catalog rejected"))
    }

    @Test fun productionAndDevTrustNeverMix() {
        val store = MemStore()
        val devCat = Catalogs(dev).build(9, "devapp"); val prodCat = cats.build(1, "realapp")
        val srv = serverFor(devCat)
        val u = updater(store, srv, devKeys = listOf(dev.pubHex))
        assertEquals(RefreshResult.Updated(9, true), u.refresh())
        assertNull(store.states[KeyClass.PROD]); assertEquals(9L, store.states[KeyClass.DEV]!!.serial); assertNull(store.cache[KeyClass.PROD])
        // a production catalog with a LOWER serial is not a rollback: its own state is separate
        srv.index = prodCat.first; srv.sig = prodCat.second
        assertEquals(RefreshResult.Updated(1, false), u.refresh())
        assertEquals(1L, store.states[KeyClass.PROD]!!.serial); assertEquals(9L, store.states[KeyClass.DEV]!!.serial)
        // production wins at load time, and is not labelled DEV
        val withBoth = CatalogRepository.load(store, listOf(prod.pubHex), listOf(dev.pubHex), null, preview)
        assertFalse((withBoth.source as CatalogSource.Signed).dev)
        // a release build has no DEV keys: the DEV cache is ignored, a DEV key cannot verify anything
        store.cache.remove(KeyClass.PROD)
        val release = CatalogRepository.load(store, listOf(prod.pubHex), emptyList(), null, preview)
        assertTrue(release.source is CatalogSource.Preview)
        // a DEV-signed file slipped into the PRODUCTION cache slot is not accepted
        store.cache[KeyClass.PROD] = devCat
        assertTrue(CatalogRepository.load(store, listOf(prod.pubHex), emptyList(), null, preview).source is CatalogSource.Preview)
        // and a release-build updater refuses a DEV-signed catalog outright
        val relStore = MemStore()
        assertEquals(RefreshResult.Rejected("unknown signing key"), updater(relStore, serverFor(devCat)).refresh())
        assertTrue(relStore.cache.isEmpty() && relStore.states.isEmpty())
    }

    @Test fun aCatalogWithNoRotateAppsIsAcceptedAndShowsNothing() {
        val store = MemStore(); val srv = serverFor(cats.build(1, "nanoonly", nanoOnly = true))
        assertTrue(updater(store, srv).refresh() is RefreshResult.Updated)
        val loaded = CatalogRepository.load(store, listOf(prod.pubHex), emptyList(), null, preview)
        assertTrue(loaded.source is CatalogSource.Signed)
        assertEquals(0, DeviceFilter.forDevice(loaded.catalog, Targets.RG_ROTATE).size)
        assertEquals(1, DeviceFilter.hiddenCount(loaded.catalog, Targets.RG_ROTATE))
    }
}
