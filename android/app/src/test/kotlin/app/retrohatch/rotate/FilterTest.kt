package app.retrohatch.rotate

import app.retrohatch.rotate.model.Artifact
import app.retrohatch.rotate.model.AppEntry
import app.retrohatch.rotate.model.Catalog
import app.retrohatch.rotate.model.CatalogMapper
import app.retrohatch.rotate.model.DeviceFilter
import app.retrohatch.rotate.model.StrictJson
import app.retrohatch.rotate.model.Targets
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FilterTest {
    private val rotate = Targets.RG_ROTATE
    private fun art(device: String, fw: String, fmt: String, available: Boolean = false) =
        Artifact(device, fw, fmt, available, "r", "1", null, null, null, "untested")
    private fun app(id: String, vararg a: Artifact) = AppEntry(id, id, "d", "dev", "https://x", null, "MIT", "other", a.toList())

    private fun previewCatalog(): Catalog = CatalogMapper.fromDoc(StrictJson.parseObject(repo("android/app/src/main/assets/preview/index.json").readBytes()))

    @Test fun nanoOpksNeverReachAndroid() {
        val cat = Catalog(emptyList(), listOf(
            app("nano-only", art("rg-nano", "funkeyos-drum78", "opk", true)),
            app("mislabelled-device", art("rg-nano", "android-12", "apk")),            // wrong device id
            app("mislabelled-format", art("rg-rotate", "android-12", "opk", true)),    // right device, but an OPK
            app("wrong-firmware", art("rg-rotate", "funkeyos-drum78", "apk")),
            app("good", art("rg-rotate", "android-12", "apk")),
        ))
        val shown = DeviceFilter.forDevice(cat, rotate)
        assertEquals(listOf("good"), shown.map { it.app.id })
        assertEquals(4, DeviceFilter.hiddenCount(cat, rotate))
    }

    @Test fun anAppWithBothBuildsShowsOnlyTheAndroidOne() {
        val cat = Catalog(emptyList(), listOf(app("both", art("rg-nano", "funkeyos-drum78", "opk", true), art("rg-rotate", "android-12", "apk"))))
        val l = DeviceFilter.forDevice(cat, rotate).single()
        assertEquals("rg-rotate", l.artifact.device); assertEquals("apk", l.artifact.format)
    }

    @Test fun previewSampleHidesRealNanoEntriesAndOffersNoPackage() {
        val cat = previewCatalog()
        assertTrue("the preview contains real Nano entries to prove they are hidden", cat.apps.any { it.id == "kishmish-nano" } && cat.apps.any { it.id == "tarafi" })
        val shown = DeviceFilter.forDevice(cat, rotate)
        assertEquals(4, shown.size)
        assertFalse(shown.any { it.app.id == "kishmish-nano" || it.app.id == "tarafi" })
        for (l in shown) {   // no invented downloads: samples have no URL, no hash, are unavailable and not installable
            assertEquals("apk", l.artifact.format); assertFalse(l.installable)
            assertEquals(null, l.artifact.url); assertEquals(null, l.artifact.sha256)
            assertTrue(l.app.description.startsWith("PREVIEW SAMPLE"))
        }
        assertEquals(2, DeviceFilter.hiddenCount(cat, rotate))
    }

    @Test fun targetProfileMatchesTheSharedCatalogDeviceFile() {
        val d = CatalogMapper.fromDoc(mapOf("devices" to listOf(StrictJson.parseObject(repo("catalog/devices/rg-rotate.json").readBytes())))).devices.single()
        assertEquals(Targets.RG_ROTATE, d)
        assertEquals(listOf(720, 720), listOf(d.width, d.height))
    }
}
