package app.retrohatch.rotate.android

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import app.retrohatch.rotate.model.ApkInfo
import app.retrohatch.rotate.model.ApkInspector
import app.retrohatch.rotate.model.InstallEvent
import app.retrohatch.rotate.model.InstallStarter
import app.retrohatch.rotate.model.PackageState
import java.io.File
import java.security.MessageDigest

/** Reads package name, versionCode and signing certificates out of an APK with the platform parser (which also verifies the APK signature). */
class PmApkInspector(private val ctx: Context) : ApkInspector {
    @Suppress("DEPRECATION")
    override fun inspect(file: File): ApkInfo? {
        val pi = try { ctx.packageManager.getPackageArchiveInfo(file.path, PackageManager.GET_SIGNING_CERTIFICATES) } catch (e: Exception) { null } ?: return null
        val signers = pi.signingInfo?.apkContentsSigners ?: return null
        val sha = signers.map { sig -> MessageDigest.getInstance("SHA-256").digest(sig.toByteArray()).joinToString("") { "%02x".format(it) } }.toSet()
        return ApkInfo(pi.packageName ?: return null, pi.longVersionCode, sha)
    }
}

/** Installed versions. Needs QUERY_ALL_PACKAGES (declared in the manifest) because the catalog's package names are not known at build time. */
class PmPackageState(private val ctx: Context) : PackageState {
    override fun installedVersion(pkg: String): Long? = try { ctx.packageManager.getPackageInfo(pkg, 0).longVersionCode } catch (e: PackageManager.NameNotFoundException) { null }
}

/** Result of installer sessions, delivered to whoever registered (the UI thread). */
object InstallEvents {
    private val main = Handler(Looper.getMainLooper())
    private val listeners = HashMap<String, (InstallEvent) -> Unit>()
    fun listen(pkg: String, l: (InstallEvent) -> Unit) { listeners[pkg] = l }
    fun post(pkg: String, e: InstallEvent) { main.post { listeners[pkg]?.invoke(e) } }
}

/**
 * Standard Android PackageInstaller session: the system shows its own "Do you want to install this app?" screen and the user decides.
 * No silent install, no root, no installer-permission tricks. The app needs REQUEST_INSTALL_PACKAGES and the user's "Install unknown apps" switch for RetroHatch.
 */
class SessionInstaller(private val ctx: Context) : InstallStarter {
    override fun canInstall(): Boolean = ctx.packageManager.canRequestPackageInstalls()

    override fun openPermissionSettings() {
        ctx.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${ctx.packageName}")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    override fun start(file: File, pkg: String): Result<Unit> = try {
        val pi = ctx.packageManager.packageInstaller
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
        params.setAppPackageName(pkg)
        params.setSize(file.length())
        if (Build.VERSION.SDK_INT >= 31) params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_REQUIRED)
        val id = pi.createSession(params)
        pi.openSession(id).use { session ->
            file.inputStream().use { ins -> session.openWrite("base.apk", 0, file.length()).use { out -> ins.copyTo(out); session.fsync(out) } }
            val cb = Intent(ctx, InstallResultReceiver::class.java).setPackage(ctx.packageName).putExtra(InstallResultReceiver.EXTRA_PKG, pkg)
            // mutable: the system adds the status extras to this intent
            val pending = PendingIntent.getBroadcast(ctx, id, cb, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE)
            session.commit(pending.intentSender)
        }
        Result.success(Unit)
    } catch (e: Exception) {
        Result.failure(Exception("Could not start the installer: ${e.message ?: e.javaClass.simpleName}"))
    }
}

class InstallResultReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val pkg = intent.getStringExtra(EXTRA_PKG) ?: return
        val status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)
        val msg = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE)
        when (status) {
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                @Suppress("DEPRECATION") val confirm = intent.getParcelableExtra<Intent>(Intent.EXTRA_INTENT)
                if (confirm != null) context.startActivity(confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))   // Android's own confirmation screen
            }
            PackageInstaller.STATUS_SUCCESS -> InstallEvents.post(pkg, InstallEvent.Success)
            PackageInstaller.STATUS_FAILURE_ABORTED -> InstallEvents.post(pkg, InstallEvent.Cancelled)        // the user declined (or abandoned) in the installer
            PackageInstaller.STATUS_FAILURE_CONFLICT -> InstallEvents.post(pkg, InstallEvent.Failed("Conflicts with an installed app of the same name signed by someone else"))
            PackageInstaller.STATUS_FAILURE_INCOMPATIBLE -> InstallEvents.post(pkg, InstallEvent.Failed("Not compatible with this device"))
            PackageInstaller.STATUS_FAILURE_STORAGE -> InstallEvents.post(pkg, InstallEvent.Failed("Not enough storage"))
            PackageInstaller.STATUS_FAILURE_BLOCKED -> InstallEvents.post(pkg, InstallEvent.Failed("Blocked by the system" + (msg?.let { ": $it" } ?: "")))
            else -> InstallEvents.post(pkg, InstallEvent.Failed("Install failed" + (msg?.let { ": $it" } ?: "")))
        }
    }

    companion object { const val EXTRA_PKG = "app.retrohatch.rotate.PKG" }
}
