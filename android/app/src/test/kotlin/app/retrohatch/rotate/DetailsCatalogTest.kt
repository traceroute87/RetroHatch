package app.retrohatch.rotate

import app.retrohatch.rotate.model.CatalogMapper
import app.retrohatch.rotate.model.CatalogPolicy
import app.retrohatch.rotate.model.StrictJson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** Optional long_description / features: read for the Details page, validated by the device policy, and the bundled DEV catalog really carries them. */
class DetailsCatalogTest {
    private val rotate = mapOf("schema" to 1L, "id" to "rg-rotate", "name" to "RG Rotate", "adapter" to "android-packageinstaller", "package_format" to "apk",
        "display" to mapOf("w" to 720L, "h" to 720L), "firmware" to listOf("android-12"))

    private fun app(extra: Map<String, Any?> = emptyMap()): Map<String, Any?> {
        val art = mapOf("device" to "rg-rotate", "firmware" to "android-12", "format" to "apk", "status" to "available", "version" to "1.0",
            "url" to "https://github.com/acme/tool/releases/download/v1/t.apk", "sha256" to "ab".repeat(32), "size" to 1000L, "compatibility" to mapOf("level" to "experimental"),
            "android" to mapOf("package" to "app.acme.tool", "version_code" to 3L, "signer_sha256" to listOf("cd".repeat(32))))
        return mapOf("schema" to 1L, "id" to "tool", "name" to "Tool", "description" to "Short.", "developer" to "acme", "source" to "https://github.com/acme/tool",
            "license" to "GPL-3.0", "category" to "application", "artifacts" to listOf(art)) + extra
    }

    private fun doc(a: Map<String, Any?>) = mapOf("format" to 1L, "serial" to 5L, "generated" to "2026-11-09", "devices" to listOf(rotate), "apps" to listOf(a),
        "approvals" to emptyList<Any?>(), "revoked" to emptyList<Any?>())

    private fun problem(extra: Map<String, Any?>) = CatalogPolicy.check(doc(app(extra)), allowExperimental = true)

    @Test fun absentFieldsStayValidAndMapToNothing() {
        assertNull(problem(emptyMap()))
        val a = CatalogMapper.fromDoc(doc(app())).apps.single()
        assertNull(a.longDescription); assertEquals(emptyList<String>(), a.features)
    }

    @Test fun presentFieldsAreMapped() {
        val extra = mapOf("long_description" to "One.\n\nTwo.", "features" to listOf("A", "B"))
        assertNull(problem(extra))
        val a = CatalogMapper.fromDoc(doc(app(extra))).apps.single()
        assertEquals("One.\n\nTwo.", a.longDescription); assertEquals(listOf("A", "B"), a.features)
    }

    @Test fun badValuesAreRejected() {
        assertTrue(problem(mapOf("long_description" to ""))!!.contains("long_description"))
        assertTrue(problem(mapOf("long_description" to "x".repeat(2001)))!!.contains("long_description"))
        assertTrue(problem(mapOf("long_description" to 5L))!!.contains("long_description"))
        assertTrue(problem(mapOf("features" to emptyList<String>()))!!.contains("features"))
        assertTrue(problem(mapOf("features" to List(9) { "f" }))!!.contains("features"))
        assertTrue(problem(mapOf("features" to listOf("ok", "")))!!.contains("features"))
        assertTrue(problem(mapOf("features" to listOf("x".repeat(121))))!!.contains("features"))
        assertTrue(problem(mapOf("features" to "not a list"))!!.contains("features"))
        assertTrue(problem(mapOf("unknown_field" to "x"))!!.contains("wrong fields"))          // everything else stays strict
    }

    @Test fun theBundledDevCatalogCarriesProfessionalText() {
        val f = File("src/debug/assets/dev/catalog/index.json")
        val apps = CatalogMapper.fromDoc(StrictJson.parseObject(f.readBytes())).apps
        val hand = setOf("aegis", "droidify", "gallery", "lemuroid", "materialfiles", "melonds", "newpipe", "obtainium")
        assertTrue("the eight hand-written apps stay", apps.map { it.id }.containsAll(hand))
        for (a in apps) {
            assertTrue("${a.id} short description", a.description.length in 15..300 && !a.description.contains("EXPERIMENTAL") && !a.description.contains("not approved"))
            if (a.id in hand) {
                assertTrue("${a.id} long description", (a.longDescription ?: "").length in 200..2000)
                assertTrue("${a.id} features", a.features.size in 3..8)
            }
        }
    }
}
