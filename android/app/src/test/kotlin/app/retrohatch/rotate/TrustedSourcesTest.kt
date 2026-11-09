package app.retrohatch.rotate

import app.retrohatch.rotate.model.ApkInfo
import app.retrohatch.rotate.model.AndroidPackage
import app.retrohatch.rotate.model.CatalogPolicy
import app.retrohatch.rotate.model.DownloadException
import app.retrohatch.rotate.model.Downloader
import app.retrohatch.rotate.model.IdentityCheck
import app.retrohatch.rotate.model.TrustedSources
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.net.URL

/** Direct-install sources: what a signed DEV entry may point at, what is refused, redirects, and the minimum-Android check. Production keeps the GitHub-only rule. */
class TrustedSourcesTest {
    @get:Rule val tmp = TemporaryFolder()
    private fun kind(source: String, url: String, pkg: String? = "a.b", vc: Long? = 7) = TrustedSources.kind(source, url, pkg, vc)

    @Test fun acceptedSources() {
        assertEquals("github", kind("https://github.com/o/r", "https://github.com/o/r/releases/download/v1/a.apk"))
        assertEquals("gitlab", kind("https://gitlab.com/g/p", "https://gitlab.com/g/p/-/releases/v1/downloads/a.apk"))
        assertEquals("gitlab", kind("https://gitlab.com/g/sub/p", "https://gitlab.com/g/sub/p/uploads/abc123/a.apk"))
        assertEquals("codeberg", kind("https://codeberg.org/o/r", "https://codeberg.org/o/r/releases/download/v1/a.apk"))
        assertEquals("fdroid", kind("https://example.org/upstream", "https://f-droid.org/repo/a.b_7.apk"))                      // upstream page can be anywhere; the file name is the entry's own package + versionCode
        assertEquals("izzy", kind("https://example.org/upstream", "https://apt.izzysoft.de/fdroid/repo/a.b_7.apk"))
        assertEquals("official", kind("https://github.com/libretro/RetroArch", "https://buildbot.libretro.com/stable/1.22.2/android/RetroArch_aarch64.apk", "com.retroarch.aarch64", 1))
        assertEquals("official", kind("https://www.ppsspp.org/", "https://www.ppsspp.org/files/1_20_4/ppsspp.apk", "org.ppsspp.ppsspp", 1))
    }

    @Test fun refusedSources() {
        for ((src, url) in listOf(
            "https://github.com/o/r" to "https://github.com/x/y/releases/download/v1/a.apk",                    // another repository
            "https://gitlab.com/g/p" to "https://gitlab.com/other/p/-/releases/v1/downloads/a.apk",
            "https://gitlab.com/g/p" to "https://evil.example/g/p/-/releases/v1/downloads/a.apk",
            "https://codeberg.org/o/r" to "https://codeberg.org/o/other/releases/download/v1/a.apk",
            "https://example.org/u" to "https://f-droid.org/repo/other.pkg_7.apk",                              // F-Droid file of ANOTHER package
            "https://example.org/u" to "https://f-droid.org/repo/a.b_8.apk",                                    // wrong versionCode
            "https://example.org/u" to "https://f-droid.org.evil.example/repo/a.b_7.apk",
            "https://example.org/u" to "https://mirror.example/fdroid/repo/a.b_7.apk",                          // a mirror
            "https://example.org/u" to "http://f-droid.org/repo/a.b_7.apk",                                     // not https
            "https://example.org/u" to "https://user@f-droid.org/repo/a.b_7.apk",
            "https://example.org/u" to "https://apkpure.com/a.b/a.b.apk",                                       // a third-party APK site
            "https://example.org/u" to "https://buildbot.libretro.com/stable/1.22.2/android/RetroArch_aarch64.apk", // not pinned for package a.b
            "https://github.com/o/r" to "https://github.com/o/r/releases/download/v1/a.apk?x=1\\..\\",
        )) assertNull("$url", kind(src, url))
        assertNull(kind("https://x.org", "https://www.ppsspp.org/files/../evil.apk", "org.ppsspp.ppsspp", 1))
        assertNull(kind("https://x.org", "https://www.ppsspp.org/files/1_20_4/ppsspp.apk?redirect=evil", "org.ppsspp.ppsspp", 1))
        assertNull(kind("https://x.org", "https://buildbot.libretro.com/stable/a.apk", "org.ppsspp.ppsspp", 1))        // another package's pinned prefix
    }

    @Test fun policyAcceptsTheSourcesOnlyInDevSignedCatalogs() {
        fun doc(url: String, source: String) = mapOf("format" to 1L, "serial" to 5L, "generated" to "2026-11-09",
            "devices" to listOf(mapOf("schema" to 1L, "id" to "rg-rotate", "name" to "RG Rotate", "adapter" to "android-packageinstaller", "package_format" to "apk", "display" to mapOf("w" to 720L, "h" to 720L), "firmware" to listOf("android-12"))),
            "apps" to listOf(mapOf("schema" to 1L, "id" to "tool", "name" to "Tool", "description" to "d", "developer" to "x", "source" to source, "license" to "MIT", "category" to "application",
                "artifacts" to listOf(mapOf("device" to "rg-rotate", "firmware" to "android-12", "format" to "apk", "status" to "available", "version" to "1", "url" to url, "sha256" to "ab".repeat(32), "size" to 10L,
                    "compatibility" to mapOf("level" to "experimental"), "android" to mapOf("package" to "a.b", "version_code" to 7L, "signer_sha256" to listOf("cd".repeat(32))))))),
            "approvals" to emptyList<Any?>(), "revoked" to emptyList<Any?>())
        val fd = doc("https://f-droid.org/repo/a.b_7.apk", "https://example.org/tool")
        assertNull(CatalogPolicy.check(fd, allowExperimental = true))
        assertTrue(CatalogPolicy.check(fd, allowExperimental = false)!!.contains("not publishable"))                  // production: experimental level AND github-only
        assertTrue(CatalogPolicy.check(doc("https://f-droid.org/repo/other_7.apk", "https://example.org/tool"), allowExperimental = true)!!.contains("trusted source"))
        assertTrue(CatalogPolicy.check(doc("https://mirror.example/a.apk", "https://github.com/o/r"), allowExperimental = true)!!.contains("trusted source"))
        assertNull(CatalogPolicy.check(doc("https://github.com/o/r/releases/download/v1/a.apk", "https://github.com/o/r"), allowExperimental = true))
    }

    @Test fun redirectsStayOnTheSourcesOwnHosts() {
        assertEquals(setOf("f-droid.org"), TrustedSources.redirectHosts("https://f-droid.org/repo/a.b_7.apk"))
        assertTrue("objects.githubusercontent.com" in TrustedSources.redirectHosts("https://github.com/o/r/releases/download/v1/a.apk")!!)
        val body = ByteArray(3000) { (it * 7).toByte() }
        fun dl(hosts: Set<String>?, next: String) = Downloader(open = { u: URL ->
            if (u.path == "/repo/a.b_7.apk") FakeConn(u, 302, mapOf("Location" to next), ByteArray(0)) else FakeConn(u, 200, mapOf("Content-Length" to "3000"), body)
        }, allowedRedirectHosts = hosts)
        val sha = sha(body)
        dl(setOf("f-droid.org"), "https://f-droid.org/repo/other/a.apk").download("https://f-droid.org/repo/a.b_7.apk", File(tmp.root, "ok.apk"), 3000, sha, { false }) { _, _ -> }      // same host: fine
        try { dl(setOf("f-droid.org"), "https://evil.example/a.apk").download("https://f-droid.org/repo/a.b_7.apk", File(tmp.root, "bad.apk"), 3000, sha, { false }) { _, _ -> }; fail("redirect to another host") }
        catch (e: DownloadException) { assertTrue(e.message, e.message!!.contains("unexpected host")) }
        assertTrue(!File(tmp.root, "bad.apk").exists())
    }

    @Test fun minimumAndroidVersionIsChecked() {
        val want = AndroidPackage("a.b", 7, listOf("cc".repeat(32)))
        val ok = ApkInfo("a.b", 7, setOf("cc".repeat(32)), 30)
        assertNull(IdentityCheck.problem(ok, want, 31))
        assertTrue(IdentityCheck.problem(ApkInfo("a.b", 7, setOf("cc".repeat(32)), 33), want, 31)!!.contains("API 33"))
        assertNull(IdentityCheck.problem(ApkInfo("a.b", 7, setOf("cc".repeat(32))), want, 31))                           // unknown minSdk: Android decides
        assertTrue(IdentityCheck.problem(ApkInfo("a.b", 7, setOf("dd".repeat(32)), 30), want, 31)!!.contains("certificate"))   // a changed signing identity is still refused
    }
}
