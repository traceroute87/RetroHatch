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

    /** The committed debug-build snapshot (android/app/src/debug/assets/dev/catalog) is what the app lists: 8 real apps, matching the inventory byte for byte. */
    @Test fun bundledDevCatalogMatchesTheInventoryAndExcludesHeldApps() {
        val dir = "android/app/src/debug/assets/dev"
        val key = repo("$dir/dev_keys.txt").readLines().first { it.isNotBlank() && !it.startsWith("#") }.trim()
        val v = Trust.verify(repo("$dir/catalog/index.json").readBytes(), repo("$dir/catalog/index.json.sig").readBytes(), listOf(key), experimentalKeyIds = setOf(Trust.keyId(unhex(key))))
        val cat = CatalogMapper.fromDoc(v.doc)
        val inv = StrictJson.parseObject(repo("candidates/inventory-rg-rotate.json").readBytes())
        @Suppress("UNCHECKED_CAST") val entries = (inv["applications"] as List<Map<String, Any?>>)
        val held = entries.filter { it["hold"] != null }
        assertEquals("exactly two entries are on hold (licence, signer)", 2, held.size)
        assertEquals(8, cat.apps.size)
        val shown = DeviceFilter.forDevice(cat, Targets.RG_ROTATE)
        assertEquals("every entry is for RG Rotate", 8, shown.size)
        for (l in shown) {
            val a = l.artifact
            assertEquals("experimental", a.level); assertTrue("the EXPERIMENTAL label comes from the artifact level (the UI), not from the text", l.app.description.isNotBlank())
            @Suppress("UNCHECKED_CAST") val e = entries.single { ((it["packages"] as List<Map<String, Any?>>)[0]["android"] as Map<String, Any?>)["package"] == a.android!!.packageName }
            assertNull("held entries must not be in the catalog", e["hold"])
            @Suppress("UNCHECKED_CAST") val p = (e["packages"] as List<Map<String, Any?>>)[0]
            assertEquals(p["sha256"], a.sha256); assertEquals(p["url"], a.url); assertEquals((p["size"] as Long), a.size)
            @Suppress("UNCHECKED_CAST") val an = p["android"] as Map<String, Any?>
            assertEquals(an["version_code"], a.android!!.versionCode); assertEquals(an["signer_sha256"], a.android!!.signerSha256)
            assertEquals(e["license"], l.app.license)
            assertTrue(a.url!!.startsWith(l.app.source + "/releases/download/"))
        }
        assertFalse(shown.any { it.app.name.contains("Pegasus", true) || it.artifact.android!!.packageName.contains("daijishou") })
        // production trust refuses the very same files
        try { Trust.verify(repo("$dir/catalog/index.json").readBytes(), repo("$dir/catalog/index.json.sig").readBytes(), Trust.PRODUCTION_KEYS); fail() } catch (e: TrustException) { /* unknown signing key */ }
    }
}
