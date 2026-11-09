package app.retrohatch.rotate

import app.retrohatch.rotate.model.CatalogMapper
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

/**
 * The mixed Nano-OPK + Android-APK index in tests/trust_fixture_android was built and SIGNED BY THE PYTHON TOOLS (tests/make_android_fixture.py).
 * These tests prove the Kotlin verifier agrees with tools/trust.py on it, field by field.
 */
class AndroidCatalogTest {
    private val dir = "tests/trust_fixture_android/signed"
    private val index = repo("$dir/index.json").readBytes()
    private val sig = repo("$dir/index.json.sig").readBytes()
    private val pub = repo("$dir/PUBKEY.hex").readText().trim()

    @Test fun pythonSignedMixedCatalogVerifiesInKotlin() {
        val v = Trust.verify(index, sig, listOf(pub))
        val cat = CatalogMapper.fromDoc(v.doc)
        assertEquals(setOf("examplepad", "fixtureapk"), cat.apps.map { it.id }.toSet())
        val apk = cat.apps.single { it.id == "fixtureapk" }.artifacts.single()
        assertEquals("app.retrohatch.fixture", apk.android!!.packageName)
        assertEquals(7L, apk.android!!.versionCode)
        assertEquals(1, apk.android!!.signerSha256.size)
    }

    @Test fun rotateSeesOnlyTheApkAndNanoOpkIsHidden() {
        val cat = CatalogMapper.fromDoc(Trust.verify(index, sig, listOf(pub)).doc)
        val shown = DeviceFilter.forDevice(cat, Targets.RG_ROTATE)
        assertEquals(listOf("fixtureapk"), shown.map { it.app.id })
        assertTrue(shown.single().installable)
        assertEquals(1, DeviceFilter.hiddenCount(cat, Targets.RG_ROTATE))
    }

    @Test fun productionKeyDoesNotTrustIt() {
        try { Trust.verify(index, sig); fail() } catch (e: TrustException) { assertTrue(e.message!!.contains("unknown signing key")) }
    }

    private fun mutated(f: (MutableMap<String, Any?>, MutableMap<String, Any?>) -> Unit): String? {
        @Suppress("UNCHECKED_CAST") val doc = deepCopy(StrictJson.parseObject(index)) as MutableMap<String, Any?>
        @Suppress("UNCHECKED_CAST") val apps = doc["apps"] as List<MutableMap<String, Any?>>
        @Suppress("UNCHECKED_CAST") val apk = (apps.single { it["id"] == "fixtureapk" }["artifacts"] as List<MutableMap<String, Any?>>).single()
        @Suppress("UNCHECKED_CAST") val opk = (apps.single { it["id"] == "examplepad" }["artifacts"] as List<MutableMap<String, Any?>>).single()
        f(apk, opk)
        return app.retrohatch.rotate.model.CatalogPolicy.check(doc)
    }

    @Suppress("UNCHECKED_CAST")
    private fun deepCopy(v: Any?): Any? = when (v) {
        is Map<*, *> -> LinkedHashMap<String, Any?>().also { m -> (v as Map<String, Any?>).forEach { (k, x) -> m[k] = deepCopy(x) } }
        is List<*> -> ArrayList<Any?>().also { l -> v.forEach { l.add(deepCopy(it)) } }
        else -> v
    }

    @Suppress("UNCHECKED_CAST")
    private fun android(a: MutableMap<String, Any?>) = a["android"] as MutableMap<String, Any?>

    @Test fun policyMatchesTheTrustToolsOnApkFields() {
        assertNull(mutated { _, _ -> })
        val bad = listOf<(MutableMap<String, Any?>, MutableMap<String, Any?>) -> Unit>(
            { a, _ -> a.remove("android") }, { a, _ -> android(a).remove("package") }, { a, _ -> android(a).remove("signer_sha256") },
            { a, _ -> android(a)["package"] = "nodots" }, { a, _ -> android(a)["package"] = "app.1bad" }, { a, _ -> android(a)["package"] = "a." + "b".repeat(254) },
            { a, _ -> android(a)["package"] = "app..x" }, { a, _ -> android(a)["package"] = "app.x." }, { a, _ -> android(a)["version_code"] = 0L },
            { a, _ -> android(a)["version_code"] = "7" }, { a, _ -> android(a)["signer_sha256"] = emptyList<String>() },
            { a, _ -> android(a)["signer_sha256"] = listOf("AB".repeat(32)) }, { a, _ -> android(a)["signer_sha256"] = listOf("ab".repeat(32), "ab".repeat(32)) },
            { a, _ -> android(a)["signer_sha256"] = (0 until 9).map { "%064x".format(it) } }, { a, _ -> android(a)["extra"] = 1L },
            { a, _ -> a["install"] = mapOf("dest_name" to "x.opk") }, { a, _ -> a["url"] = "https://example.com/f.apk" },
            { _, o -> o["android"] = mapOf("package" to "a.b", "version_code" to 1L, "signer_sha256" to listOf("0".repeat(64))) }, { _, o -> o.remove("install") },
            { a, _ -> a["format"] = "opk" },
        )
        bad.forEachIndexed { i, f -> assertTrue("case $i must be rejected", mutated(f) != null) }
        assertNull(mutated { a, _ -> android(a)["version_code"] = 2147483647L })
        assertNull(mutated { a, _ -> android(a)["signer_sha256"] = (0 until 8).map { "%064x".format(it) } })
    }

    @Test fun tamperedSignedIndexIsRejected() {
        for (i in index.indices step 17) {
            val t = index.copyOf(); t[i] = (t[i].toInt() xor 1).toByte()
            try { Trust.verify(t, sig, listOf(pub)); fail("byte $i accepted") } catch (e: TrustException) { assertFalse(e.message.isNullOrEmpty()) }
        }
    }
}
