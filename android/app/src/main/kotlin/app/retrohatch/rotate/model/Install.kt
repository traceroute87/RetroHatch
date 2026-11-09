package app.retrohatch.rotate.model

import java.io.File
import java.util.concurrent.Executor
import java.util.concurrent.atomic.AtomicBoolean

/** What the platform says about an APK file: package, versionCode and the SHA-256 of each signing certificate (DER). */
data class ApkInfo(val packageName: String, val versionCode: Long, val signerSha256: Set<String>)

interface ApkInspector { fun inspect(file: File): ApkInfo? }
interface PackageState {
    fun installedVersion(pkg: String): Long?
    /** SHA-256 of the installed copy's signing certificates, null when unknown. Android refuses an update signed by a different key. */
    fun installedSigners(pkg: String): Set<String>? = null
}

/** Starts an Android PackageInstaller session; the result arrives later through [InstallFlow.onInstallEvent]. */
interface InstallStarter {
    fun canInstall(): Boolean
    fun openPermissionSettings()
    fun start(file: File, pkg: String): Result<Unit>
}

sealed class InstallEvent {
    object Success : InstallEvent()
    object Cancelled : InstallEvent()
    data class Failed(val message: String) : InstallEvent()
}

object IdentityCheck {
    /** null = the APK is what the signed catalog entry says; otherwise the reason it must not be installed. */
    fun problem(info: ApkInfo?, want: AndroidPackage): String? {
        if (info == null) return "Not a valid, signed APK"
        if (info.packageName != want.packageName) return "Wrong package: the APK is ${info.packageName}, the catalog says ${want.packageName}"
        if (info.versionCode != want.versionCode) return "Wrong version: the APK is versionCode ${info.versionCode}, the catalog says ${want.versionCode}"
        if (info.signerSha256.isEmpty()) return "The APK has no signing certificate"
        val allowed = want.signerSha256.map { it.lowercase() }.toSet()
        if (!allowed.containsAll(info.signerSha256.map { it.lowercase() })) return "Signing certificate does not match the catalog"
        return null
    }
}

sealed class InstState {
    data class Unavailable(val reason: String) : InstState()
    /** Nothing downloaded. [installed] = versionCode already on the device (an update is offered when it is older). */
    data class Ready(val installed: Long?) : InstState()
    data class Downloading(val done: Long, val total: Long) : InstState()
    object Verifying : InstState()
    object Downloaded : InstState()
    /** Session committed; the system's own confirmation screen is (or will be) on top. */
    object Installing : InstState()
    object NeedsPermission : InstState()
    /** The user declined in Android's installer. The verified file is kept; Install tries again. */
    object InstallCancelled : InstState()
    data class Installed(val versionCode: Long) : InstState()
    data class Failed(val message: String) : InstState()
}

/**
 * Download -> verify -> install for ONE catalog entry. Pure Kotlin (the platform pieces are interfaces), so the whole workflow is unit-tested on the JVM.
 * Nothing is installed unless: the catalog was verified (not preview), the artifact is `available` with full APK identity, the downloaded bytes have the
 * signed SHA-256 and size, the platform reports the signed package name, versionCode and signing certificate, and the user confirms in Android's installer.
 */
class InstallFlow(
    val listing: Listing, private val catalogVerified: Boolean, private val dir: File,
    private val downloader: Downloader, private val inspector: ApkInspector, private val packages: PackageState, private val starter: InstallStarter,
    private val worker: Executor, private val main: (Runnable) -> Unit,
) {
    @Volatile var state: InstState = InstState.Ready(null); private set
    var onChange: (InstState) -> Unit = {}
    /** UI: after a verified download go straight on to Android's installer (the system still asks the user to confirm). Off in the unit tests. */
    @Volatile var autoInstall = false
    private val cancel = AtomicBoolean(false)
    private val art get() = listing.artifact
    private val android get() = art.android
    private var file: File? = null

    private fun set(s: InstState) { state = s; main(Runnable { onChange(s) }) }

    init { refresh() }

    /** Re-read what is on the device (call when the screen opens or after the installer returns). */
    fun refresh() {
        if (state is InstState.Downloading || state is InstState.Verifying || state is InstState.Installing) return
        val a = android
        state = when {
            !catalogVerified -> InstState.Unavailable("Preview data: this is not a signed catalog, so nothing can be installed.")
            !listing.installable || a == null -> InstState.Unavailable(art.unavailableReason ?: "A verified build for this device is not available yet.")
            else -> {
                val inst = packages.installedVersion(a.packageName)
                val have = if (inst != null && inst < a.versionCode) packages.installedSigners(a.packageName) else null
                when {
                    inst != null && inst >= a.versionCode -> InstState.Installed(inst)   // never offered again: no downgrade, no reinstall of the same build
                    have != null && have.isNotEmpty() && have.none { it in a.signerSha256.map { s -> s.lowercase() } } ->
                        InstState.Unavailable("The installed copy is signed by a different developer key, so Android would refuse this update. Uninstall it first.")
                    (state is InstState.Downloaded || state is InstState.InstallCancelled || state is InstState.NeedsPermission) && file?.isFile == true -> state   // keep what the user last saw while the verified file is still there
                    else -> InstState.Ready(inst)
                }
            }
        }
        main(Runnable { onChange(state) })
    }

    val busy get() = state.let { it is InstState.Downloading || it is InstState.Verifying || it is InstState.Installing }

    /** The one button: Download / Install / retry. */
    fun primary() {
        when (val s = state) {
            is InstState.Ready, is InstState.Failed -> download()
            is InstState.Downloaded, is InstState.NeedsPermission, is InstState.InstallCancelled -> install()
            else -> {}
        }
    }

    fun cancelDownload() { if (state is InstState.Downloading) cancel.set(true) }

    private fun target(): File = File(dir, "${android!!.packageName}-${android!!.versionCode}-${art.sha256!!.take(12)}.apk")

    private fun download() {
        val a = android ?: return; val url = art.url ?: return; val sha = art.sha256 ?: return; val size = art.size ?: return
        if (!catalogVerified) return
        cancel.set(false)
        set(InstState.Downloading(0, size))
        worker.execute {
            try {
                val dest = target()
                if (dest.isFile && Sha.ofFile(dest) == sha) { file = dest }   // an earlier verified download is reused
                else {
                    dest.delete()
                    downloader.download(url, dest, size, sha, { cancel.get() }) { d, t -> state = InstState.Downloading(d, t); main(Runnable { onChange(state) }) }
                    file = dest
                }
                set(InstState.Verifying)
                val problem = IdentityCheck.problem(inspector.inspect(file!!), a)
                if (problem != null) { file!!.delete(); file = null; set(InstState.Failed(problem)); return@execute }
                set(InstState.Downloaded)
                if (autoInstall) install()
            } catch (e: DownloadCancelled) {
                set(InstState.Failed("Download cancelled"))
            } catch (e: DownloadException) {
                set(InstState.Failed(e.message ?: "Download failed"))
            } catch (e: Exception) {
                set(InstState.Failed("Download failed: ${e.javaClass.simpleName}"))
            }
        }
    }

    private fun install() {
        val a = android ?: return; val f = file ?: return
        if (!f.isFile) { set(InstState.Failed("The downloaded file is gone; download it again")); return }
        packages.installedVersion(a.packageName)?.let { if (it >= a.versionCode) { set(InstState.Installed(it)); return } }   // never downgrade or reinstall the same build
        if (!starter.canInstall()) { set(InstState.NeedsPermission); starter.openPermissionSettings(); return }
        set(InstState.Installing)
        // re-check right before handing the file to the system: size, hash and identity (the file lives in app-private storage, but this is cheap)
        worker.execute {
            val problem = when {
                f.length() != art.size -> "The downloaded file changed on disk"
                Sha.ofFile(f) != art.sha256 -> "The downloaded file changed on disk"
                else -> IdentityCheck.problem(inspector.inspect(f), a)
            }
            if (problem != null) { f.delete(); file = null; set(InstState.Failed(problem)); return@execute }
            starter.start(f, a.packageName).onFailure { set(InstState.Failed(it.message ?: "Could not start the installer")) }
        }
    }

    /** Result of the system installer for this entry's session. */
    fun onInstallEvent(e: InstallEvent) {
        val a = android ?: return
        when (e) {
            InstallEvent.Success -> {
                file?.delete(); file = null
                set(InstState.Installed(packages.installedVersion(a.packageName) ?: a.versionCode))
            }
            InstallEvent.Cancelled -> set(if (file?.isFile == true) InstState.InstallCancelled else InstState.Ready(packages.installedVersion(a.packageName)))
            is InstallEvent.Failed -> set(InstState.Failed(e.message))
        }
    }
}
