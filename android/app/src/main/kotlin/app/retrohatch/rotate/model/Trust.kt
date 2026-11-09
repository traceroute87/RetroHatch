package app.retrohatch.rotate.model

import org.bouncycastle.crypto.params.Ed25519PublicKeyParameters
import org.bouncycastle.crypto.signers.Ed25519Signer
import java.security.MessageDigest
import java.util.Base64

/** Newest index accepted so far (rollback protection), same shape as the Nano's catalog.state. */
data class TrustState(val serial: Long, val sha256: String)

class Verified(val doc: Map<String, Any?>, val state: TrustState, val keyId: String, val warnings: List<String>)

/**
 * Signed-catalog verification: a port of tools/trust.py `verify` (the order of checks is the same, fail closed).
 * The signature only says "the key holder published this"; approvals, hashes and release URLs are re-checked by [CatalogPolicy].
 */
object Trust {
    const val MAX_INDEX = 256 * 1024
    const val MAX_SIG = 4096

    /** Production catalog signing key, PUBLIC half (catalog/production.pub). The private half exists only offline. */
    const val PRODUCTION_KEY_HEX = "98ed5db6fa72fb6fb3645a1789028936316820c0bdca0f4de05a21e06ca18120"
    val PRODUCTION_KEYS = listOf(PRODUCTION_KEY_HEX)

    fun sha256Hex(b: ByteArray): String = MessageDigest.getInstance("SHA-256").digest(b).joinToString("") { "%02x".format(it) }

    fun keyId(pub: ByteArray): String = sha256Hex(pub).substring(0, 16)

    private fun unhex(h: String): ByteArray {
        if (h.length % 2 != 0 || !h.all { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }) throw IllegalArgumentException("hex")
        return ByteArray(h.length / 2) { h.substring(2 * it, 2 * it + 2).toInt(16).toByte() }
    }

    /** Raw Ed25519 check. Used by [verify] and by the RFC 8032 vector tests. */
    fun ed25519Verify(pub: ByteArray, message: ByteArray, sig: ByteArray): Boolean {
        if (pub.size != 32 || sig.size != 64) return false
        val v = Ed25519Signer()
        v.init(false, Ed25519PublicKeyParameters(pub, 0))
        v.update(message, 0, message.size)
        return v.verifySignature(sig)
    }

    fun verify(index: ByteArray, sigDoc: ByteArray, trusted: List<String> = PRODUCTION_KEYS, state: TrustState? = null): Verified {
        if (trusted.isEmpty()) throw TrustException("no trusted key configured")
        if (index.isEmpty() || sigDoc.isEmpty()) throw TrustException("missing index or signature")
        if (index.size > MAX_INDEX || sigDoc.size > MAX_SIG) throw TrustException("index or signature too large")
        val s = StrictJson.parse(sigDoc) as? Map<*, *> ?: throw TrustException("unsupported signature document")
        if (s.keys != setOf("v", "alg", "key_id", "sig") || s["v"] != 1L || s["alg"] != "ed25519") throw TrustException("unsupported signature document")
        val sigB64 = s["sig"] as? String
        val kid = s["key_id"] as? String
        if (sigB64 == null || kid == null) throw TrustException("unsupported signature document")
        val sig: ByteArray
        val keys: Map<String, ByteArray>
        try {
            sig = Base64.getDecoder().decode(sigB64)
            if (Base64.getEncoder().encodeToString(sig) != sigB64) throw IllegalArgumentException("non-canonical base64")
            keys = trusted.map { unhex(it) }.associateBy { keyId(it) }
        } catch (e: IllegalArgumentException) {
            throw TrustException("malformed signature or key")
        }
        if (sig.size != 64) throw TrustException("malformed signature")
        val pub = keys[kid] ?: throw TrustException("unknown signing key")
        if (!ed25519Verify(pub, index, sig)) throw TrustException("bad signature")
        val doc = StrictJson.parseObject(index)                      // parse only after the signature holds
        if (!StrictJson.canonical(doc).contentEquals(index)) throw TrustException("index is not in canonical form")
        CatalogPolicy.check(doc)?.let { throw TrustException("signed index violates policy: $it") }
        val h = sha256Hex(index)
        val serial = doc["serial"] as Long
        if (state != null) {
            if (serial < state.serial) throw TrustException("rollback: serial $serial < ${state.serial}")
            if (serial == state.serial && h != state.sha256) throw TrustException("same serial, different content")
        }
        return Verified(doc, TrustState(serial, h), kid, emptyList())
    }
}
