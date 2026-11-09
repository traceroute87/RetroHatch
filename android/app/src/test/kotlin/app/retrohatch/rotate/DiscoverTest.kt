package app.retrohatch.rotate

import app.retrohatch.rotate.model.AppEntry
import app.retrohatch.rotate.model.Artifact
import app.retrohatch.rotate.model.CatalogMapper
import app.retrohatch.rotate.model.CatalogPolicy
import app.retrohatch.rotate.model.Discover
import app.retrohatch.rotate.model.DiscoverQuery
import app.retrohatch.rotate.model.Filter
import app.retrohatch.rotate.model.Groups
import app.retrohatch.rotate.model.Listing
import app.retrohatch.rotate.model.Presence
import app.retrohatch.rotate.model.Sort
import app.retrohatch.rotate.model.DeviceFilter
import app.retrohatch.rotate.model.Targets
import app.retrohatch.rotate.model.ExternalListing
import app.retrohatch.rotate.model.StrictJson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** Discover: search, categories (only non-empty ones), sort, filters, summary line. */
class DiscoverTest {
    private fun l(id: String, name: String, desc: String, dev: String, group: String?, tags: List<String> = emptyList(), released: String? = null, added: String? = null,
                  level: String = "experimental", category: String = "application") = Listing(
        AppEntry(id, name, desc, dev, "https://github.com/$dev/$id", null, "MIT", category, emptyList(), null, emptyList(), group, tags, released, added),
        Artifact("rg-rotate", "android-12", "apk", true, null, "1", "https://github.com/$dev/$id/releases/download/v1/a.apk", "ab".repeat(32), 1000, level, null))

    private val all = listOf(
        l("lemuroid", "Lemuroid", "All in one emulator", "Swordfish90", "emulators", listOf("libretro", "retro"), "2026-04-21", "2026-11-01"),
        l("melonds", "melonDS", "Nintendo DS emulator", "rafaelvcaetano", "emulators", listOf("nintendo-ds"), "2026-05-06", "2026-11-09"),
        l("newpipe", "NewPipe", "Streaming front-end", "TeamNewPipe", "media", listOf("youtube"), "2026-11-07", "2026-11-05"),
        l("aegis", "Aegis", "2FA authenticator", "beemdevelopment", "utilities", listOf("2fa", "otp"), "2026-09-06", "2026-11-09", level = "verified"),
        l("blips", "Blips", "A puzzle game", "joyrider3774", "games", emptyList(), null, null),
    )
    private val none = { _: Listing -> Presence.NOT_INSTALLED }
    private fun names(q: DiscoverQuery, p: (Listing) -> Presence = none) = Discover.apply(all, q, p).map { it.app.name }

    @Test fun searchMatchesNameDescriptionDeveloperAndTags() {
        assertEquals(listOf("Lemuroid"), names(DiscoverQuery(text = "lemu")))
        assertEquals(listOf("Lemuroid", "melonDS"), names(DiscoverQuery(text = "emulator")))               // description
        assertEquals(listOf("NewPipe"), names(DiscoverQuery(text = "teamnewpipe")))                          // developer
        assertEquals(listOf("Aegis"), names(DiscoverQuery(text = "otp")))                                    // tag
        assertEquals(listOf("Aegis"), names(DiscoverQuery(text = "  2FA  authenticator ")))                 // all words, any case, extra spaces
        assertEquals(emptyList<String>(), names(DiscoverQuery(text = "emulator youtube")))                   // every word must match
        assertEquals(5, names(DiscoverQuery(text = "   ")).size)                                             // blank = everything
    }

    @Test fun onlyNonEmptyCategoriesInFixedOrder() {
        assertEquals(listOf("games", "emulators", "utilities", "media"), Discover.groups(all).map { it.first })
        assertEquals(listOf(1, 2, 1, 1), Discover.groups(all).map { it.third })
        assertEquals(listOf("emulators"), Discover.groups(all.filter { it.app.group == "emulators" }).map { it.first })
        assertEquals(listOf("Lemuroid", "melonDS"), names(DiscoverQuery(group = "emulators")))
        assertEquals(emptyList<String>(), names(DiscoverQuery(group = "ports")))                              // a category nobody holds shows nothing
    }

    @Test fun catalogWithoutGroupFallsBackToTheSignedCategory() {
        assertEquals("themes-launchers", Groups.of(l("x", "X", "", "d", null, category = "launcher").app))
        assertEquals("ports", Groups.of(l("x", "X", "", "d", null, category = "port").app))
        assertEquals("utilities", Groups.of(l("x", "X", "", "d", null).app))
        assertEquals("Themes & Launchers", Groups.label("themes-launchers"))
    }

    @Test fun sorting() {
        assertEquals(listOf("Aegis", "Blips", "Lemuroid", "melonDS", "NewPipe"), names(DiscoverQuery()))                              // case-insensitive A to Z
        assertEquals(listOf("NewPipe", "Aegis", "melonDS", "Lemuroid", "Blips"), names(DiscoverQuery(sort = Sort.UPDATED)))            // no date: last
        assertEquals(listOf("Aegis", "melonDS", "NewPipe", "Lemuroid", "Blips"), names(DiscoverQuery(sort = Sort.ADDED)))              // same date: A to Z
    }

    @Test fun filters() {
        val p = { x: Listing -> when (x.app.id) { "lemuroid" -> Presence.INSTALLED; "aegis" -> Presence.UPDATE; else -> Presence.NOT_INSTALLED } }
        assertEquals(listOf("Aegis", "Lemuroid"), names(DiscoverQuery(filter = Filter.INSTALLED), p))        // an app with an update is installed too
        assertEquals(listOf("Blips", "melonDS", "NewPipe"), names(DiscoverQuery(filter = Filter.NOT_INSTALLED), p))
        assertEquals(listOf("Aegis"), names(DiscoverQuery(filter = Filter.UPDATES), p))
        assertEquals(listOf("Aegis"), names(DiscoverQuery(filter = Filter.VERIFIED), p))
        assertEquals(listOf("Lemuroid"), names(DiscoverQuery(text = "retro", group = "emulators", filter = Filter.INSTALLED), p))      // they combine
    }

    @Test fun externalListingsAndTheInstallableFilter() {
        val ext = Listing(AppEntry("paid", "Paid Emu", "Store only", "dev", "https://example.org", null, "proprietary", "application", emptyList(), null, emptyList(), "emulators", emptyList(), null, "2026-11-09",
            ExternalListing("Google Play", "https://play.google.com/x", "Paid.")), Artifact("rg-rotate", "android-12", "apk", false, "External listing: Paid.", null, null, null, null, "external", null))
        val mix = all + ext
        fun n(q: DiscoverQuery) = Discover.apply(mix, q, none).map { it.app.name }
        assertEquals(listOf("Paid Emu"), n(DiscoverQuery(filter = Filter.EXTERNAL)))
        assertEquals(false, n(DiscoverQuery(filter = Filter.NOT_INSTALLED)).contains("Paid Emu"))               // "not installed" means installable but not installed yet
        assertEquals(false, ext.installable)
        assertEquals(listOf("Paid Emu"), n(DiscoverQuery(text = "paid")))
        assertEquals(setOf("emulators", "media", "utilities", "games"), Discover.groups(mix).map { it.first }.toSet())
    }

    @Test fun summaryAndActive() {
        assertFalse(DiscoverQuery().active); assertTrue(DiscoverQuery(text = "a").active); assertTrue(DiscoverQuery(group = "media").active)
        assertFalse(DiscoverQuery(sort = Sort.ADDED).active)                                                  // a sort alone is not a filter
        assertEquals("5 apps  -  A to Z", Discover.summary(DiscoverQuery(), 5, 5))
        assertEquals("2 of 5  -  Emulators  -  Installed  -  \"gb\"  -  Newly added", Discover.summary(DiscoverQuery("gb", "emulators", Sort.ADDED, Filter.INSTALLED), 2, 5))
    }

    @Test fun bundledDevCatalogIsOrganised() {
        val cat = CatalogMapper.fromDoc(StrictJson.parseObject(File("src/debug/assets/dev/catalog/index.json").readBytes()))
        val all = DeviceFilter.forDevice(cat, Targets.RG_ROTATE)
        assertTrue("a curated catalog of 100+ apps", all.size >= 100)
        assertTrue(all.all { it.app.group != null && it.app.added != null && it.app.description.isNotBlank() })
        assertEquals("every group holds apps", Groups.ORDER.map { it.first }, Discover.groups(all).map { it.first })
        val ext = all.filter { it.app.external != null }; val inst = all.filter { it.app.external == null }
        assertTrue(ext.isNotEmpty() && inst.size >= 60)
        assertTrue("an external listing can never be installed", ext.none { it.installable || it.artifact.url != null || it.artifact.sha256 != null || it.artifact.available })
        assertTrue("every installable entry has the full identity", inst.all { it.installable && it.artifact.android != null && it.artifact.android!!.signerSha256.isNotEmpty() })
        assertTrue(ext.all { it.app.external!!.url.startsWith("https://") && it.app.external!!.reason.isNotBlank() })
        // schema-level checks of the new fields
        val base = mapOf("schema" to 1L, "id" to "t", "name" to "T", "description" to "d", "developer" to "x", "source" to "https://github.com/x/t", "license" to "MIT", "category" to "application")
        fun problem(extra: Map<String, Any?>): String? = CatalogPolicy.check(mapOf("format" to 1L, "serial" to 1L, "generated" to "2026-11-09", "devices" to emptyList<Any?>(),
            "apps" to listOf(base + extra + ("artifacts" to emptyList<Any?>())), "approvals" to emptyList<Any?>(), "revoked" to emptyList<Any?>()), allowExperimental = true)
        assertTrue(problem(mapOf("group" to "movies"))!!.contains("bad group"))
        assertTrue(problem(mapOf("tags" to listOf("Bad Tag")))!!.contains("bad tags"))
        assertTrue(problem(mapOf("added" to "yesterday"))!!.contains("bad added"))
        assertTrue(problem(mapOf("released" to "2026-1-1"))!!.contains("bad released"))
    }
}
