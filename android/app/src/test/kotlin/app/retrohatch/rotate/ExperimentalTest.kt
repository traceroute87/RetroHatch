package app.retrohatch.rotate

import app.retrohatch.rotate.model.CatalogLoader
import app.retrohatch.rotate.model.CatalogMapper
import app.retrohatch.rotate.model.CatalogPolicy
import app.retrohatch.rotate.model.CatalogSource
import app.retrohatch.rotate.model.DeviceFilter
import app.retrohatch.rotate.model.StrictJson
import app.retrohatch.rotate.model.Targets
import app.retrohatch.rotate.model.Trust
import app.retrohatch.rotate.model.TrustException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/** The EXPERIMENTAL / UNVERIFIED channel: level "experimental" is accepted ONLY from a DEV-class key, never from a production key, and keeps every other gate. */
class ExperimentalTest {
    private val dev = TestKey()
    private val prod = TestKey()
    private val rotate = mapOf("schema" to 1L, "id" to "rg-rotate", "name" to "RG Rotate", "adapter" to "android-packageinstaller", "package_format" to "apk",
        "display" to mapOf("w" to 720L, "h" to 720L), "firmware" to listOf("android-12"))

    private fun app(id: String = "tool", level: String = "experimental", license: String = "GPL-3.0", url: String = "https://github.com/acme/tool/releases/download/v1/t.apk",
                    android: Any? = mapOf("package" to "app.acme.tool", "version_code" to 3L, "signer_sha256" to listOf("cd".repeat(32)))): Map<String, Any?> {
        val art = mutableMapOf<String, Any?>("device" to "rg-rotate", "firmware" to "android-12", "format" to "apk", "status" to "available", "version" to "1.0", "url" to url,
            "sha256" to "ab".repeat(32), "size" to 1000L, "compatibility" to mapOf("level" to level))
        if (android != null) art["android"] = android
        return mapOf("schema" to 1L, "id" to id, "name" to "Tool", "description" to "EXPERIMENTAL / UNVERIFIED", "developer" to "acme", "source" to "https://github.com/acme/tool",
            "license" to license, "category" to "application", "artifacts" to listOf(art))
    }

    private fun doc(vararg apps: Map<String, Any?>, revoked: List<Any?> = emptyList()) = mapOf("format" to 1L, "serial" to 5L, "generated" to "2026-11-09",
        "devices" to listOf(rotate), "apps" to apps.toList(), "approvals" to emptyList<Any?>(), "revoked" to revoked)

    private fun signed(d: Map<String, Any?>, key: TestKey = dev): Pair<ByteArray, ByteArray> { val b = StrictJson.canonical(d); return b to key.sign(b) }
    private fun devKid() = Trust.keyId(unhex(dev.pubHex))

    @Test fun externalListingsAreDevOnlyAndNeverCarryADownload() {
        val ext = mapOf("id" to "paid-emu", "name" to "Paid Emu", "description" to "Store only.", "developer" to "acme", "source" to "https://example.org/emu", "license" to "proprietary",
            "label" to "Google Play", "url" to "https://play.google.com/store/apps/details?id=x", "reason" to "Paid, store-only.", "group" to "emulators", "tags" to listOf("ps2"))
        fun withExt(e: Map<String, Any?>) = doc(app()) + ("external" to listOf(e))
        assertNull(CatalogPolicy.check(withExt(ext), allowExperimental = true))
        assertTrue("production keys never accept an external list", CatalogPolicy.check(withExt(ext), allowExperimental = false)!!.contains("unexpected"))
        for ((bad, why) in listOf(ext + ("sha256" to "ab".repeat(32)) to "carries no download", ext + ("artifacts" to emptyList<Any?>()) to "carries no download", ext + ("url" to "http://x") to "bad url",
                                  ext + ("id" to "tool") to "duplicate id", ext + ("group" to "movies") to "bad group", ext - "reason" to "wrong fields", ext + ("extra" to "x") to "wrong fields"))
            assertTrue("$why: " + CatalogPolicy.check(withExt(bad), allowExperimental = true), CatalogPolicy.check(withExt(bad), allowExperimental = true)!!.contains(why))
        val mapped = CatalogMapper.fromDoc(withExt(ext)).external.single()
        assertEquals("Google Play", mapped.external!!.label); assertTrue(mapped.artifacts.isEmpty())
        val l = DeviceFilter.forDevice(CatalogMapper.fromDoc(withExt(ext)), Targets.RG_ROTATE).single { it.app.id == "paid-emu" }
        assertFalse(l.installable); assertNull(l.artifact.url); assertNull(l.artifact.sha256)
    }

    @Test fun acceptedOnlyFromADevKey() {
        val (i, s) = signed(doc(app()))
        Trust.verify(i, s, listOf(dev.pubHex), experimentalKeyIds = setOf(devKid()))
        try { Trust.verify(i, s, listOf(dev.pubHex)); fail("a key that is not marked DEV must not carry experimental entries") } catch (e: TrustException) { assertTrue(e.message!!.contains("not publishable")) }
        val (pi, ps) = signed(doc(app()), prod)       // a production key signing the same: rejected even though a DEV key id set exists
        try { Trust.verify(pi, ps, listOf(prod.pubHex, dev.pubHex), experimentalKeyIds = setOf(devKid())); fail() } catch (e: TrustException) { assertTrue(e.message!!.contains("not publishable")) }
    }

    @Test fun everyOtherGateStillApplies() {
        fun bad(d: Map<String, Any?>, why: String) = assertTrue(why, CatalogPolicy.check(d, allowExperimental = true) != null)
        assertNull(CatalogPolicy.check(doc(app()), allowExperimental = true))
        bad(doc(app(license = "unknown")), "unknown licence")
        bad(doc(app(url = "https://example.com/t.apk")), "not a GitHub release of the source repo")
        bad(doc(app(url = "http://github.com/acme/tool/releases/download/v1/t.apk")), "plain http")
        bad(doc(app(android = null)), "no android identity")
        bad(doc(app(android = mapOf("package" to "nodots", "version_code" to 3L, "signer_sha256" to listOf("cd".repeat(32))))), "bad package")
        bad(doc(app(android = mapOf("package" to "app.acme.tool", "version_code" to 3L, "signer_sha256" to emptyList<String>()))), "no signer")
        bad(doc(app(level = "community")), "other levels are never allowed")
        bad(doc(app(level = "untested")), "untested")
        bad(doc(app(), revoked = listOf(mapOf("app" to "tool", "sha256" to "ab".repeat(32), "reason" to "bad"))), "revoked")
        assertTrue("verified keeps the production gates (no approval)", CatalogPolicy.check(doc(app(level = "verified")), allowExperimental = true) != null)
    }

    @Test fun loaderLabelsItDevAndHidesOtherDevices() {
        val (i, s) = signed(doc(app()))
        val r = CatalogLoader.load(i, s, null, trusted = listOf(prod.pubHex), devKeys = listOf(dev.pubHex))
        val src = r.source as CatalogSource.Signed
        assertTrue(src.dev)
        val l = DeviceFilter.forDevice(r.catalog, Targets.RG_ROTATE).single()
        assertEquals("experimental", l.artifact.level); assertTrue(l.installable)
        // a release build (no DEV keys) shows nothing of it
        val rel = CatalogLoader.load(i, s, null, trusted = listOf(prod.pubHex))
        assertTrue(rel.source is CatalogSource.Preview)
    }

    /** The committed debug-build snapshot (android/app/src/debug/assets/dev/catalog) verifies with the DEV key only and matches candidates/android-curated.json fact for fact. */
    @Test fun bundledDevCatalogMatchesTheCuratedFile() {
        val dir = "android/app/src/debug/assets/dev"
        val key = repo("$dir/dev_keys.txt").readLines().first { it.isNotBlank() && !it.startsWith("#") }.trim()
        val v = Trust.verify(repo("$dir/catalog/index.json").readBytes(), repo("$dir/catalog/index.json.sig").readBytes(), listOf(key), experimentalKeyIds = setOf(Trust.keyId(unhex(key))))
        val cat = CatalogMapper.fromDoc(v.doc)
        @Suppress("UNCHECKED_CAST") val cur = (StrictJson.parseObject(repo("candidates/android-curated.json").readBytes())["apps"] as List<Map<String, Any?>>)
        val inst = cur.filter { it["mode"] == "install" }; val ext = cur.filter { it["mode"] == "external" }
        assertEquals(inst.size, cat.apps.size); assertEquals(ext.size, cat.external.size)
        val shown = DeviceFilter.forDevice(cat, Targets.RG_ROTATE)
        assertEquals("every entry is for RG Rotate", cur.size, shown.size)
        for (e in inst) {
            @Suppress("UNCHECKED_CAST") val ap = e["apk"] as Map<String, Any?>
            val l = shown.single { it.app.id == e["id"] }; val a = l.artifact
            assertEquals("experimental", a.level); assertTrue(l.installable)
            assertEquals(ap["sha256"], a.sha256); assertEquals(ap["url"], a.url); assertEquals(ap["size"], a.size)
            assertEquals(ap["version_code"], a.android!!.versionCode); assertEquals(ap["signers"], a.android!!.signerSha256); assertEquals(e["package"], a.android!!.packageName)
            assertTrue(a.url!!.startsWith(l.app.source + "/releases/download/") || a.url!!.lowercase().startsWith((l.app.source + "/releases/download/").lowercase()))
        }
        for (e in ext) { val l = shown.single { it.app.id == e["id"] }; assertTrue(l.app.external != null && !l.installable && l.artifact.url == null) }
        // a held entry is never installable
        assertTrue(shown.none { it.app.id in setOf("daijisho", "pegasus-frontend") && it.installable })
        // production trust refuses the very same files
        try { Trust.verify(repo("$dir/catalog/index.json").readBytes(), repo("$dir/catalog/index.json.sig").readBytes(), Trust.PRODUCTION_KEYS); fail() } catch (e: TrustException) { /* unknown signing key */ }
    }
}
