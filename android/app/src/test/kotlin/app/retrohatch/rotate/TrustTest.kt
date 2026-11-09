package app.retrohatch.rotate

import app.retrohatch.rotate.model.CatalogLoader
import app.retrohatch.rotate.model.CatalogPolicy
import app.retrohatch.rotate.model.CatalogSource
import app.retrohatch.rotate.model.StrictJson
import app.retrohatch.rotate.model.Trust
import app.retrohatch.rotate.model.TrustException
import app.retrohatch.rotate.model.TrustState
import org.bouncycastle.crypto.params.Ed25519PrivateKeyParameters
import org.bouncycastle.crypto.signers.Ed25519Signer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.File
import java.security.SecureRandom
import java.util.Base64

internal fun res(name: String): ByteArray = object {}.javaClass.classLoader!!.getResourceAsStream(name)!!.readBytes()
internal fun repo(path: String): File = File("../../$path")   // unit tests run in android/app
internal fun hex(b: ByteArray) = b.joinToString("") { "%02x".format(it) }
internal fun unhex(s: String) = ByteArray(s.length / 2) { s.substring(2 * it, 2 * it + 2).toInt(16).toByte() }

/** Throwaway signing key for tests (the production private key never leaves its offline home). */
class TestKey {
    private val priv = Ed25519PrivateKeyParameters(SecureRandom())
    val pubHex: String = hex(priv.generatePublicKey().encoded)
    fun sign(index: ByteArray): ByteArray {
        val s = Ed25519Signer(); s.init(true, priv); s.update(index, 0, index.size)
        return StrictJson.canonical(mapOf("v" to 1L, "alg" to "ed25519", "key_id" to Trust.keyId(unhex(pubHex)), "sig" to Base64.getEncoder().encodeToString(s.generateSignature())))
    }
}

private fun refuses(expect: String, f: () -> Any?) {
    try { f(); fail("expected TrustException containing '$expect'") }
    catch (e: TrustException) { assertTrue("'${e.message}' should contain '$expect'", e.message!!.contains(expect)) }
}

class StrictJsonTest {
    private fun bad(s: String, what: String) = refuses(what) { StrictJson.parse(s.toByteArray()) }

    @Test fun rejectsWhatTheNanoParserRejects() {
        bad("""{"a":1,"a":2}""", "duplicate key")
        bad("""{"a":1.5}""", "disallowed number")
        bad("""{"a":1e3}""", "disallowed number")
        bad("""{"a":-1}""", "disallowed number")
        bad("""{"a":2147483648}""", "disallowed number")
        bad("""{"a":NaN}""", "disallowed number")
        bad("""{"a":Infinity}""", "disallowed number")
        bad("""{"a":01}""", "malformed")
        bad("""{"a":1} x""", "trailing")
        bad("{\"a\":\"\t\"}", "control character")
        refuses("byte order mark") { StrictJson.parse(byteArrayOf(0xEF.toByte(), 0xBB.toByte(), 0xBF.toByte(), '{'.code.toByte(), '}'.code.toByte())) }
        refuses("not UTF-8") { StrictJson.parse(byteArrayOf('"'.code.toByte(), 0xC0.toByte(), '"'.code.toByte())) }
    }

    @Test fun canonicalMatchesPython() {
        // json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=True): sorted keys, \u escapes for non-ASCII and DEL
        val doc = StrictJson.parse("""{"b":[true,false,null,2147483647],"a":"é\u007f\"\\ 😀","A":{}}""".toByteArray())
        val bs = "\\"
        val expected = "{\"A\":{},\"a\":\"" + bs + "u00e9" + bs + "u007f" + bs + "\"" + bs + bs + " " + bs + "ud83d" + bs + "ude00\",\"b\":[true,false,null,2147483647]}"
        assertEquals(expected, String(StrictJson.canonical(doc)))
    }

    @Test fun fixtureIndexIsAlreadyCanonical() {
        val raw = res("index.json")
        assertTrue(StrictJson.canonical(StrictJson.parse(raw)).contentEquals(raw))
    }
}

/** The RFC 8032 vectors the Nano's C verifier is tested with (tests/rfc8032_vectors.h): one file, read here, not copied. */
class Rfc8032Test {
    @Test fun sharedVectors() {
        val h = repo("tests/rfc8032_vectors.h").readText()
        fun arr(name: String): ByteArray = Regex("""$name\[\] = \{([^}]*)\}""").find(h)!!.groupValues[1].split(",").map { it.trim().removePrefix("0x").toInt(16).toByte() }.toByteArray()
        val n = Regex("""V(\d+)_MSGLEN (\d+)""").findAll(h).toList()
        assertTrue("vectors found", n.size >= 3)
        for (m in n) {
            val i = m.groupValues[1]; val len = m.groupValues[2].toInt()
            val pk = arr("v${i}_pk"); val msg = arr("v${i}_msg").copyOf(len); val sig = arr("v${i}_sig")
            assertTrue("RFC 8032 vector $i verifies", Trust.ed25519Verify(pk, msg, sig))
            val bad = sig.copyOf(); bad[10] = (bad[10].toInt() xor 1).toByte()
            assertFalse("tampered signature $i fails", Trust.ed25519Verify(pk, msg, bad))
            assertFalse("tampered message $i fails", Trust.ed25519Verify(pk, msg + byteArrayOf(0), sig))
        }
    }
}

class FixtureTrustTest {
    private val index = res("index.json")
    private val sig = res("index.json.sig")
    private val pub = String(res("PUBKEY.hex")).trim()

    @Test fun signedFixtureVerifies() {
        val v = Trust.verify(index, sig, listOf(pub))
        assertEquals(1L, v.state.serial)
        assertEquals(Trust.keyId(unhex(pub)), v.keyId)
        assertEquals("e9686982279773e4", v.keyId)
    }

    @Test fun productionKeyDoesNotTrustTheFixture() {
        refuses("unknown signing key") { Trust.verify(index, sig) }          // default = pinned production key
        refuses("no trusted key") { Trust.verify(index, sig, emptyList()) }
    }

    @Test fun everyByteOfTheIndexIsProtected() {
        for (i in index.indices step 3) {
            val t = index.copyOf(); t[i] = (t[i].toInt() xor 0x01).toByte()
            try { Trust.verify(t, sig, listOf(pub)); fail("tampered byte $i was accepted") } catch (e: TrustException) { /* expected */ }
        }
    }

    @Test fun signatureDocumentIsStrict() {
        val s = String(sig)
        refuses("unsupported signature document") { Trust.verify(index, s.replace("\"v\":1", "\"v\":2").toByteArray(), listOf(pub)) }
        refuses("unsupported signature document") { Trust.verify(index, s.replace("ed25519", "ed448").toByteArray(), listOf(pub)) }
        refuses("unsupported signature document") { Trust.verify(index, s.replace("}", ",\"x\":1}").toByteArray(), listOf(pub)) }
        refuses("unknown signing key") { Trust.verify(index, s.replace("e9686982279773e4", "0000000000000000").toByteArray(), listOf(pub)) }
        refuses("bad signature") { Trust.verify(index, s.replace("YN2V", "YN2W").toByteArray(), listOf(pub)) }
        refuses("missing index or signature") { Trust.verify(index, ByteArray(0), listOf(pub)) }
        refuses("too large") { Trust.verify(ByteArray(Trust.MAX_INDEX + 1), sig, listOf(pub)) }
    }

    @Test fun rollbackProtection() {
        val h = Trust.sha256Hex(index)
        Trust.verify(index, sig, listOf(pub), TrustState(1, h))
        refuses("rollback") { Trust.verify(index, sig, listOf(pub), TrustState(2, h)) }
        refuses("same serial, different content") { Trust.verify(index, sig, listOf(pub), TrustState(1, "0".repeat(64))) }
    }
}

/** Publish gates, exercised with documents signed by a throwaway test key. */
class PolicyTest {
    private val key = TestKey()
    private val sha = "ab".repeat(32)
    private val rotate = mapOf("schema" to 1L, "id" to "rg-rotate", "name" to "RG Rotate", "adapter" to "android-packageinstaller", "package_format" to "apk",
        "display" to mapOf("w" to 720L, "h" to 720L), "firmware" to listOf("android-12"))
    private val nano = mapOf("schema" to 1L, "id" to "rg-nano", "name" to "Nano", "adapter" to "opk-funkeyos", "package_format" to "opk", "firmware" to listOf("funkeyos-drum78"))

    private fun artifact(device: String = "rg-rotate", fw: String = "android-12", fmt: String = "apk", level: String = "verified", status: String = "available",
                         url: String = "https://github.com/acme/tool/releases/download/v1/tool.apk", extra: Map<String, Any?> = emptyMap()) =
        mapOf("device" to device, "firmware" to fw, "format" to fmt, "status" to status, "version" to "1.0", "url" to url, "sha256" to sha, "size" to 1000L,
            "compatibility" to mapOf("level" to level, "evidence" to listOf(mapOf("sha256" to sha, "date" to "2026-11-01", "tester" to "t")))) + extra

    private fun app(art: Map<String, Any?>) = mapOf("schema" to 1L, "id" to "tool", "name" to "Tool", "description" to "d", "developer" to "acme",
        "source" to "https://github.com/acme/tool", "license" to "MIT", "category" to "utility", "artifacts" to listOf(art))

    private fun approval(device: String = "rg-rotate", fw: String = "android-12", size: Long = 1000L, release: String = "https://github.com/acme/tool/releases/tag/v1") =
        mapOf("app" to "tool", "device" to device, "firmware" to fw, "sha256" to sha, "size" to size, "release" to release, "approved_by" to "me", "date" to "2026-11-02")

    private fun doc(art: Map<String, Any?> = artifact(), approvals: List<Any?> = listOf(approval()), devices: List<Any?> = listOf(rotate), revoked: List<Any?> = emptyList()) =
        mapOf("format" to 1L, "serial" to 1L, "generated" to "2026-11-09", "devices" to devices, "apps" to listOf(app(art)), "approvals" to approvals, "revoked" to revoked)

    private fun verify(d: Map<String, Any?>) { val b = StrictJson.canonical(d); Trust.verify(b, key.sign(b), listOf(key.pubHex)) }

    @Test fun validAndroidEntryVerifies() = verify(doc())

    @Test fun gates() {
        refuses("no human approval") { verify(doc(approvals = emptyList())) }
        refuses("approval does not match") { verify(doc(approvals = listOf(approval(size = 5)))) }
        refuses("approval does not match") { verify(doc(approvals = listOf(approval(release = "https://github.com/acme/tool/releases/tag/v2")))) }
        refuses("matches no published artifact") { verify(doc(approvals = listOf(approval(), approval(fw = "android-13")))) }
        refuses("not publishable") { verify(doc(art = artifact(level = "community"))) }
        refuses("only available") { verify(doc(art = artifact(status = "unavailable"))) }
        refuses("not a release download") { verify(doc(art = artifact(url = "https://example.com/tool.apk"))) }
        refuses("revoked") { verify(doc(revoked = listOf(mapOf("app" to "tool", "sha256" to sha, "reason" to "bad")))) }
        refuses("format != device package_format") { verify(doc(art = artifact(fmt = "opk", extra = mapOf("install" to mapOf("dest_name" to "tool.opk"))))) }
        refuses("unknown device") { verify(doc(art = artifact(device = "rg-nano"))) }
        refuses("not on device") { verify(doc(art = artifact(fw = "android-99"), approvals = listOf(approval(fw = "android-99")))) }
        refuses("unexpected") { verify(doc() + ("extra" to 1L)) }
        refuses("serial must be") { verify(doc() + ("serial" to 0L)) }
    }

    @Test fun nanoEntriesKeepTheirOpkRules() {
        val nanoArt = artifact("rg-nano", "funkeyos-drum78", "opk", url = "https://github.com/acme/tool/releases/download/v1/tool.opk", extra = mapOf("install" to mapOf("dest_name" to "tool.opk")))
        verify(doc(art = nanoArt, approvals = listOf(approval("rg-nano", "funkeyos-drum78")), devices = listOf(nano, rotate)))
        refuses("destination") { verify(doc(art = nanoArt + ("install" to mapOf("dest_name" to "tool.bin")), approvals = listOf(approval("rg-nano", "funkeyos-drum78")), devices = listOf(nano))) }
        refuses("no install.dest_name") { verify(doc(art = nanoArt - "install", approvals = listOf(approval("rg-nano", "funkeyos-drum78")), devices = listOf(nano))) }
    }

    @Test fun policyHelperAcceptsNullForSoundIndex() { assertNull(CatalogPolicy.check(doc())); assertNotNull(CatalogPolicy.check(doc(approvals = emptyList()))) }
}

class LoaderTest {
    private val preview = repo("android/app/src/main/assets/preview/index.json").readBytes()
    private val fixIndex = res("index.json"); private val fixSig = res("index.json.sig")

    @Test fun noSignedCatalogMeansPreview() {
        val r = CatalogLoader.load(null, null, preview)
        val src = r.source as CatalogSource.Preview
        assertTrue(src.reason.contains("No signed Android catalog"))
        assertTrue(r.catalog.apps.isNotEmpty())
    }

    @Test fun aSignedCatalogThatDoesNotVerifyIsNeverShown() {
        // the fixture is genuinely signed, but not by the pinned production key
        val r = CatalogLoader.load(fixIndex, fixSig, preview)
        assertTrue((r.source as CatalogSource.Preview).reason.contains("unknown signing key"))
        assertFalse("fixture content must not leak into the preview", r.catalog.apps.any { it.id == "examplepad" })
        assertNull(r.newState)
    }

    @Test fun verifiedCatalogIsLabelledSigned() {
        val r = CatalogLoader.load(fixIndex, fixSig, preview, trusted = listOf(String(res("PUBKEY.hex")).trim()))
        val s = r.source as CatalogSource.Signed
        assertEquals(1L, s.serial)
        assertTrue(r.catalog.apps.any { it.id == "examplepad" })
        assertEquals(1L, r.newState!!.serial)
    }

    @Test fun missingSignatureIsRejected() {
        val r = CatalogLoader.load(fixIndex, null, preview, trusted = listOf(String(res("PUBKEY.hex")).trim()))
        assertTrue(r.source is CatalogSource.Preview)
    }

    @Test fun pinnedKeyIsTheProductionKey() {
        val f = repo("catalog/production.pub")
        if (f.isFile) assertEquals(f.readText().trim(), Trust.PRODUCTION_KEY_HEX)   // the file is committed separately from the Nano work
        assertEquals(32, unhex(Trust.PRODUCTION_KEY_HEX).size)
    }
}
