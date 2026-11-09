package app.retrohatch.rotate

import app.retrohatch.rotate.model.AndroidPackage
import app.retrohatch.rotate.model.ApkInfo
import app.retrohatch.rotate.model.ApkInspector
import app.retrohatch.rotate.model.AppEntry
import app.retrohatch.rotate.model.Artifact
import app.retrohatch.rotate.model.DownloadCancelled
import app.retrohatch.rotate.model.DownloadException
import app.retrohatch.rotate.model.Downloader
import app.retrohatch.rotate.model.IdentityCheck
import app.retrohatch.rotate.model.InstState
import app.retrohatch.rotate.model.InstallEvent
import app.retrohatch.rotate.model.InstallFlow
import app.retrohatch.rotate.model.InstallStarter
import app.retrohatch.rotate.model.Listing
import app.retrohatch.rotate.model.PackageState
import app.retrohatch.rotate.model.Sha
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.ByteArrayInputStream
import java.io.File
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.util.concurrent.Executor

/** A scripted HTTP reply; no network involved. */
class FakeConn(url: URL, val code: Int, val headers: Map<String, String>, val body: ByteArray, val onRead: (() -> Unit)? = null) : HttpURLConnection(url) {
    override fun connect() {}
    override fun disconnect() {}
    override fun usingProxy() = false
    override fun getResponseCode() = code
    override fun getHeaderField(name: String?): String? = headers.entries.firstOrNull { it.key.equals(name, true) }?.value
    override fun getInputStream(): InputStream = object : ByteArrayInputStream(body) {
        override fun read(b: ByteArray, off: Int, len: Int): Int { onRead?.invoke(); return super.read(b, off, minOf(len, 64)) }   // small reads: cancel can land mid-file
    }
}

fun sha(b: ByteArray) = MessageDigest.getInstance("SHA-256").digest(b).joinToString("") { "%02x".format(it) }

class DownloaderTest {
    @get:Rule val tmp = TemporaryFolder()
    private val body = ByteArray(5000) { (it * 7).toByte() }
    private val dl = { replies: List<(URL) -> FakeConn> ->
        val q = replies.toMutableList()
        Downloader(open = { u -> q.removeAt(0)(u) })
    }
    private fun ok(extra: Map<String, String> = emptyMap(), data: ByteArray = body) = { u: URL -> FakeConn(u, 200, mapOf("Content-Length" to data.size.toString()) + extra, data) }
    private fun go(d: Downloader, size: Long = body.size.toLong(), s: String = sha(body), cancel: () -> Boolean = { false }, url: String = "https://x.example/a.apk"): File =
        d.download(url, File(tmp.root, "a.apk"), size, s, cancel) { _, _ -> }
    private fun refuses(msg: String, f: () -> Any?) { try { f(); fail("expected: $msg") } catch (e: DownloadException) { assertTrue("'${e.message}' ~ '$msg'", e.message!!.contains(msg)) } }

    @Test fun goodDownloadIsHashedAndRenamed() {
        val f = go(dl(listOf(ok())))
        assertEquals(sha(body), Sha.ofFile(f)); assertFalse(File(tmp.root, "a.apk.part").exists())
    }

    @Test fun wrongHashIsRejectedAndNothingIsKept() {
        refuses("SHA-256 mismatch") { go(dl(listOf(ok())), s = "0".repeat(64)) }
        assertFalse(File(tmp.root, "a.apk").exists()); assertFalse(File(tmp.root, "a.apk.part").exists())
    }

    @Test fun sizeRules() {
        refuses("Size differs") { go(dl(listOf(ok())), size = 4999) }                                              // Content-Length != catalog size
        refuses("larger than the catalog") { go(dl(listOf { u -> FakeConn(u, 200, emptyMap(), body + body) }), size = 5000) }   // no Content-Length, too many bytes
        refuses("cut short") { go(dl(listOf { u -> FakeConn(u, 200, emptyMap(), body.copyOf(100)) })) }
        assertFalse(File(tmp.root, "a.apk.part").exists())
    }

    @Test fun onlyHttpsEvenThroughRedirects() {
        refuses("Only https") { go(dl(emptyList()), url = "http://x.example/a.apk") }
        refuses("Only https") { go(dl(emptyList()), url = "https://user:pw@x.example/a.apk") }
        refuses("non-https") { go(dl(listOf { u -> FakeConn(u, 302, mapOf("Location" to "http://evil.example/a.apk"), ByteArray(0)) })) }
        val f = go(dl(listOf({ u -> FakeConn(u, 302, mapOf("Location" to "https://cdn.example/b.apk"), ByteArray(0)) }, ok())))   // https -> https is fine
        assertTrue(f.isFile)
        refuses("Too many redirects") { go(dl(List(8) { { u: URL -> FakeConn(u, 302, mapOf("Location" to "https://x.example/loop"), ByteArray(0)) } })) }
    }

    @Test fun httpErrorsAreReported() {
        refuses("404") { go(dl(listOf { u -> FakeConn(u, 404, emptyMap(), ByteArray(0)) })) }
        refuses("HTTP 500") { go(dl(listOf { u -> FakeConn(u, 500, emptyMap(), ByteArray(0)) })) }
        refuses("Unsupported encoding") { go(dl(listOf(ok(mapOf("Content-Encoding" to "gzip"))))) }
    }

    @Test fun cancelStopsAndCleansUp() {
        var reads = 0
        val c = { u: URL -> FakeConn(u, 200, mapOf("Content-Length" to "5000"), body) { reads++ } }
        try { go(dl(listOf(c)), cancel = { reads > 3 }); fail("not cancelled") } catch (e: DownloadCancelled) { /* expected */ }
        assertFalse(File(tmp.root, "a.apk").exists()); assertFalse(File(tmp.root, "a.apk.part").exists())
    }

    @Test fun fetchIsBoundedAndHttpsOnly() {
        val doc = "{\"a\":1}".toByteArray()
        assertEquals(String(doc), String(dl(listOf { u -> FakeConn(u, 200, mapOf("Content-Length" to doc.size.toString()), doc) }).fetch("https://x.example/index.json", 100)))
        refuses("larger than allowed") { dl(listOf { u -> FakeConn(u, 200, mapOf("Content-Length" to "999"), ByteArray(0)) }).fetch("https://x.example/i", 100) }
        refuses("larger than allowed") { dl(listOf { u -> FakeConn(u, 200, emptyMap(), ByteArray(500)) }).fetch("https://x.example/i", 100) }
        refuses("non-https") { dl(listOf { u -> FakeConn(u, 301, mapOf("Location" to "http://x.example/i"), ByteArray(0)) }).fetch("https://x.example/i", 100) }
        refuses("404") { dl(listOf { u -> FakeConn(u, 404, emptyMap(), ByteArray(0)) }).fetch("https://x.example/i", 100) }
        refuses("Only https") { dl(emptyList()).fetch("http://x.example/i", 100) }
    }

    @Test fun fixtureHostMappingKeepsTheCatalogUrlSeparate() {
        var seen: URL? = null
        val d = Downloader(open = { u -> seen = u; FakeConn(u, 200, mapOf("Content-Length" to "5000"), body) }, mapUrl = { it.replace("https://github.com/retrohatch-fixture/", "https://10.0.2.2:8443/") })
        d.download("https://github.com/retrohatch-fixture/x/releases/download/v1/f.apk", File(tmp.root, "m.apk"), 5000, sha(body), { false }) { _, _ -> }
        assertEquals("https://10.0.2.2:8443/x/releases/download/v1/f.apk", seen.toString())
    }
}

class IdentityTest {
    private val want = AndroidPackage("app.x", 7, listOf("aa".repeat(32)))
    @Test fun checks() {
        assertNull(IdentityCheck.problem(ApkInfo("app.x", 7, setOf("aa".repeat(32))), want))
        assertNull(IdentityCheck.problem(ApkInfo("app.x", 7, setOf("AA".repeat(32))), want))
        assertTrue(IdentityCheck.problem(ApkInfo("app.y", 7, setOf("aa".repeat(32))), want)!!.contains("Wrong package"))
        assertTrue(IdentityCheck.problem(ApkInfo("app.x", 8, setOf("aa".repeat(32))), want)!!.contains("Wrong version"))
        assertTrue(IdentityCheck.problem(ApkInfo("app.x", 7, setOf("bb".repeat(32))), want)!!.contains("certificate"))
        assertTrue(IdentityCheck.problem(ApkInfo("app.x", 7, setOf("aa".repeat(32), "bb".repeat(32))), want)!!.contains("certificate"))   // an extra signer is not allowed
        assertTrue(IdentityCheck.problem(ApkInfo("app.x", 7, emptySet()), want)!!.contains("no signing certificate"))
        assertTrue(IdentityCheck.problem(null, want)!!.contains("Not a valid"))
    }
}

class InstallFlowTest {
    @get:Rule val tmp = TemporaryFolder()
    private val body = ByteArray(3000) { (it * 13).toByte() }
    private val pkg = AndroidPackage("app.fixture", 7, listOf("cc".repeat(32)))
    private val inline = Executor { it.run() }

    private fun listing(android: AndroidPackage? = pkg, available: Boolean = true, hash: String = sha(body)) = Listing(
        AppEntry("fx", "Fixture", "d", "dev", "https://github.com/a/b", null, "MIT", "utility", emptyList()),
        Artifact("rg-rotate", "android-12", "apk", available, if (available) null else "later", "1.0", "https://github.com/a/b/releases/download/v1/f.apk", hash, body.size.toLong(), "verified", android))

    class Env(var installed: Long? = null, var info: ApkInfo? = null, var canInstall: Boolean = true, var signers: Set<String>? = null) {
        var started = 0; var settings = 0; var startFails: String? = null
        val packages = object : PackageState { override fun installedVersion(pkg: String) = installed; override fun installedSigners(pkg: String) = signers }
        val inspector = object : ApkInspector { override fun inspect(file: File) = info }
        val starter = object : InstallStarter {
            override fun canInstall() = canInstall
            override fun openPermissionSettings() { settings++ }
            override fun start(file: File, pkg: String): Result<Unit> { started++; return startFails?.let { Result.failure(Exception(it)) } ?: Result.success(Unit) }
        }
    }

    private fun flow(env: Env, l: Listing = listing(), verified: Boolean = true, data: ByteArray = body, cancelAfter: Int = -1): InstallFlow {
        var reads = 0
        val dl = Downloader(open = { u -> FakeConn(u, 200, mapOf("Content-Length" to data.size.toString()), data) { reads++; if (cancelAfter >= 0 && reads > cancelAfter) throw DownloadCancelled() } })
        return InstallFlow(l, verified, File(tmp.root, "dl"), dl, env.inspector, env.packages, env.starter, inline) { it.run() }
    }

    private val goodInfo get() = ApkInfo("app.fixture", 7, setOf("cc".repeat(32)))

    @Test fun happyPathDownloadVerifyInstall() {
        val env = Env(info = goodInfo); val f = flow(env)
        assertEquals(InstState.Ready(null), f.state)
        f.primary(); assertEquals(InstState.Downloaded, f.state)
        f.primary(); assertEquals(InstState.Installing, f.state); assertEquals(1, env.started)
        env.installed = 7; f.onInstallEvent(InstallEvent.Success)
        assertEquals(InstState.Installed(7), f.state)
        assertEquals(0, File(tmp.root, "dl").listFiles()!!.size)               // the verified APK is removed after a successful install
    }

    @Test fun badHashNeverReachesTheInstaller() {
        val env = Env(info = goodInfo); val f = flow(env, data = body.copyOf().also { it[10] = 1 })
        f.primary()
        assertTrue((f.state as InstState.Failed).message.contains("SHA-256 mismatch"))
        assertEquals(0, env.started); assertEquals(0, File(tmp.root, "dl").listFiles()!!.size)
    }

    @Test fun wrongPackageSignerOrVersionNeverReachesTheInstaller() {
        for ((info, what) in listOf(ApkInfo("app.other", 7, setOf("cc".repeat(32))) to "Wrong package", ApkInfo("app.fixture", 7, setOf("dd".repeat(32))) to "certificate",
                                    ApkInfo("app.fixture", 6, setOf("cc".repeat(32))) to "Wrong version", null to "Not a valid")) {
            val env = Env(info = info); val f = flow(env)
            f.primary()
            assertTrue(what, (f.state as InstState.Failed).message.contains(what))
            f.primary()                                                        // retry downloads again, fails the same way
            assertEquals(0, env.started); assertEquals(0, File(tmp.root, "dl").listFiles()?.size ?: 0)
        }
    }

    @Test fun userCancelInTheInstallerKeepsTheVerifiedFile() {
        val env = Env(info = goodInfo); val f = flow(env)
        f.primary(); f.primary(); f.onInstallEvent(InstallEvent.Cancelled)
        assertEquals(InstState.InstallCancelled, f.state)
        f.primary(); assertEquals(2, env.started)                              // Install again works without downloading again
    }

    @Test fun installerFailureIsShown() {
        val env = Env(info = goodInfo); val f = flow(env)
        f.primary(); f.primary(); f.onInstallEvent(InstallEvent.Failed("Conflicts with an installed app"))
        assertEquals(InstState.Failed("Conflicts with an installed app"), f.state)
        val env2 = Env(info = goodInfo).also { it.startFails = "boom" }; val f2 = flow(env2)
        f2.primary(); f2.primary(); assertEquals(InstState.Failed("boom"), f2.state)
    }

    @Test fun missingInstallPermissionOpensTheSystemSettingsNotABypass() {
        val env = Env(info = goodInfo, canInstall = false); val f = flow(env)
        f.primary(); f.primary()
        assertEquals(InstState.NeedsPermission, f.state); assertEquals(1, env.settings); assertEquals(0, env.started)
        env.canInstall = true; f.primary(); assertEquals(1, env.started)
    }

    @Test fun downloadCancelIsReportedAndLeavesNothing() {
        val env = Env(info = goodInfo); val f = flow(env, cancelAfter = 2)
        f.primary()
        assertEquals(InstState.Failed("Download cancelled"), f.state)
        assertEquals(0, File(tmp.root, "dl").listFiles()?.count { it.name.endsWith(".part") || it.name.endsWith(".apk") } ?: 0)
    }

    @Test fun previewOrIncompleteEntriesCannotBeInstalled() {
        val env = Env(info = goodInfo)
        val f = flow(env, verified = false); assertTrue(f.state is InstState.Unavailable); f.primary(); assertEquals(0, env.started)
        assertTrue(flow(env, l = listing(android = null)).state is InstState.Unavailable)
        assertTrue(flow(env, l = listing(available = false)).state is InstState.Unavailable)
    }

    @Test fun installedAndUpdateStates() {
        assertEquals(InstState.Installed(7), flow(Env(installed = 7)).state)
        assertEquals(InstState.Installed(9), flow(Env(installed = 9)).state)           // never downgrades
        assertEquals(InstState.Ready(3), flow(Env(installed = 3)).state)                // older installed: update offered
    }
}


/** Managed apps: update safety (signer, downgrade), one-tap install, and the state the user last saw surviving a return from Android's screens. */
class ManagedAppsTest {
    @get:Rule val tmp = TemporaryFolder()
    private val body = ByteArray(3000) { (it * 13).toByte() }
    private val pkg = AndroidPackage("app.fixture", 7, listOf("cc".repeat(32)))
    private val good = ApkInfo("app.fixture", 7, setOf("cc".repeat(32)))
    private val listing = Listing(AppEntry("fx", "Fixture", "d", "dev", "https://github.com/a/b", null, "MIT", "utility", emptyList()),
        Artifact("rg-rotate", "android-12", "apk", true, null, "1.0", "https://github.com/a/b/releases/download/v1/f.apk", sha(body), body.size.toLong(), "verified", pkg))

    private fun flow(env: InstallFlowTest.Env, auto: Boolean = false): InstallFlow {
        val dl = Downloader(open = { u -> FakeConn(u, 200, mapOf("Content-Length" to body.size.toString()), body) })
        return InstallFlow(listing, true, File(tmp.root, "dl"), dl, env.inspector, env.packages, env.starter, { it.run() }) { it.run() }.also { it.autoInstall = auto }
    }

    @Test fun oneTapInstallGoesStraightToAndroidsInstaller() {
        val env = InstallFlowTest.Env(info = good); val f = flow(env, auto = true)
        f.primary()
        assertEquals(InstState.Installing, f.state); assertEquals(1, env.started)       // the system still asks the user to confirm
    }

    @Test fun oneTapInstallStopsAtThePermissionScreen() {
        val env = InstallFlowTest.Env(info = good, canInstall = false); val f = flow(env, auto = true)
        f.primary()
        assertEquals(InstState.NeedsPermission, f.state); assertEquals(1, env.settings); assertEquals(0, env.started)
    }

    @Test fun updateIsOfferedOnlyForTheSameSigningKey() {
        assertEquals(InstState.Ready(3), flow(InstallFlowTest.Env(installed = 3, signers = setOf("cc".repeat(32)))).state)
        assertEquals(InstState.Ready(3), flow(InstallFlowTest.Env(installed = 3, signers = null)).state)                       // unknown: Android decides
        val s = flow(InstallFlowTest.Env(installed = 3, signers = setOf("dd".repeat(32)))).state
        assertTrue(s is InstState.Unavailable && s.reason.contains("different developer key"))
    }

    @Test fun neverDowngradesNeverReinstallsTheSameBuild() {
        for (have in listOf(7L, 9L)) {
            val env = InstallFlowTest.Env(installed = have, info = good); val f = flow(env)
            assertEquals(InstState.Installed(have), f.state); f.primary(); assertEquals(0, env.started)
        }
    }

    @Test fun anAppThatArrivesAfterTheDownloadIsNotInstalledOver() {
        val env = InstallFlowTest.Env(info = good); val f = flow(env)
        f.primary(); assertEquals(InstState.Downloaded, f.state)
        env.installed = 9                                                                     // installed from elsewhere in the meantime
        f.primary(); assertEquals(InstState.Installed(9), f.state); assertEquals(0, env.started)
    }

    @Test fun cancelStateSurvivesReturningFromAndroidsScreens() {
        val env = InstallFlowTest.Env(info = good); val f = flow(env)
        f.primary(); f.primary(); f.onInstallEvent(InstallEvent.Cancelled)
        f.refresh(); assertEquals(InstState.InstallCancelled, f.state)                        // what the activity's onResume does
        env.installed = 7; f.refresh(); assertEquals(InstState.Installed(7), f.state)         // installed meanwhile: that wins
    }
}
