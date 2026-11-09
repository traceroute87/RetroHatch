package app.retrohatch.rotate.ui

import android.app.ActivityManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.view.Gravity
import android.view.InputDevice
import android.view.View
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.Toast
import android.widget.ProgressBar
import android.widget.TextView
import java.io.File
import java.util.concurrent.Executors
import app.retrohatch.rotate.DevHooks
import app.retrohatch.rotate.android.InstallEvents
import app.retrohatch.rotate.android.PmApkInspector
import app.retrohatch.rotate.android.PmPackageState
import app.retrohatch.rotate.android.SessionInstaller
import app.retrohatch.rotate.model.CatalogSource
import app.retrohatch.rotate.model.Downloader
import app.retrohatch.rotate.model.InstState
import app.retrohatch.rotate.model.InstallFlow
import app.retrohatch.rotate.model.DeviceFilter
import app.retrohatch.rotate.model.DeviceProfile
import app.retrohatch.rotate.model.Listing
import app.retrohatch.rotate.model.LoadedCatalog
import app.retrohatch.rotate.model.Trust

/** Everything a screen needs. */
class Ui(val host: MainActivity, val m: Metrics, val width: Int, val loaded: LoadedCatalog, val target: DeviceProfile) {
    val listings: List<Listing> = DeviceFilter.forDevice(loaded.catalog, target)
    val source get() = loaded.source
    /** Not production-signed data: the bundled offline sample. */
    val preview: Boolean get() = source is CatalogSource.Preview
    /** Signed, but with the DEBUG-build fixture key. */
    val dev: Boolean get() = (source as? CatalogSource.Signed)?.dev == true
    /** Installs are possible only from a catalog whose signature verified (production key, or the DEV fixture key in debug builds). */
    val verified: Boolean get() = source is CatalogSource.Signed
    val ctx: Context get() = host
    fun push(s: Screen) = host.push(s)
    fun back() = host.back()

    private val worker = Executors.newSingleThreadExecutor()
    private val uiHandler = android.os.Handler(android.os.Looper.getMainLooper())
    private val flows = HashMap<String, InstallFlow>()
    private val packages = PmPackageState(host)

    /** One install flow per catalog entry, kept alive while the app runs so a download continues when the screen is left. */
    fun flow(l: Listing): InstallFlow = flows.getOrPut(l.app.id) {
        val f = InstallFlow(l, verified, File(host.filesDir, "downloads"), Downloader(mapUrl = DevHooks::mapUrl), PmApkInspector(host), packages,
            SessionInstaller(host), worker) { uiHandler.post(it) }
        l.artifact.android?.let { a -> InstallEvents.listen(a.packageName) { e -> f.onInstallEvent(e) } }
        f
    }

    fun installedVersion(l: Listing): Long? = l.artifact.android?.let { packages.installedVersion(it.packageName) }
}

abstract class Screen(val ui: Ui) {
    abstract val title: String
    abstract fun build(): View
    open val aLabel = "Select"
    open val bLabel = "Back"

    /** B / Back. Return true if the screen used it (e.g. to cancel a download); false = go back. */
    open fun onBack(): Boolean = false

    /** The row or button the D-pad highlight starts on (null = the first focusable). */
    open fun initialFocus(root: View): View? = null

    /** Rows that D-pad / L1 / R1 move between (in order). */
    open fun focusables(root: View): List<View> = ArrayList<View>().also { collect(root, it) }

    private fun collect(v: View, out: MutableList<View>) {
        if (v.isFocusable && v.isEnabled && v.visibility == View.VISIBLE && v.isClickable) out.add(v)
        if (v is android.view.ViewGroup) for (i in 0 until v.childCount) collect(v.getChildAt(i), out)
    }

    protected fun banner(): View =
        if (ui.dev) W.previewStrip(ui.ctx, ui.m, "DEV FIXTURE CATALOG  -  signed with a test key, not production", Pal.ACC) else W.previewStrip(ui.ctx, ui.m)

    /** Standard frame: header, optional preview strip, content, hint bar. */
    protected fun frame(content: View, showPreview: Boolean = ui.preview || ui.dev): View {
        val c = ui.ctx; val m = ui.m
        return LinearLayout(c).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Pal.BG)
            addView(W.header(c, m, title, ui.width))
            if (showPreview) addView(banner())
            addView(content)
            addView(W.hints(c, m, aLabel, bLabel, onA = { ui.host.confirm() }, onB = { ui.back() }))
        }
    }
}

class HomeScreen(ui: Ui) : Screen(ui) {
    override val title = "RetroHatch"
    override val bLabel = "Exit"

    override fun build(): View {
        val c = ui.ctx; val m = ui.m
        val root = LinearLayout(c).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(Pal.BG) }
        val bannerH = m.px(116)
        // forest from Header2.png (cropped to the banner shape, never stretched) with the logo from Retro_Hatch.png on top
        root.addView(FrameLayout(c).apply {
            layoutParams = W.lp(W.MATCH, bannerH)
            addView(ImageView(c).apply {
                setImageBitmap(Art.cropped(c, "art_forest", ui.width, bannerH, top = 0f, bottom = 0.78f, anchorY = 0.15f))
                scaleType = ImageView.ScaleType.FIT_XY
            }, FrameLayout.LayoutParams(W.MATCH, W.MATCH))
            addView(ImageView(c).apply {
                setImageBitmap(Art.fit(c, "art_logo", m.px(112), m.px(112)))
                scaleType = ImageView.ScaleType.FIT_CENTER
            }, FrameLayout.LayoutParams(W.MATCH, W.MATCH, Gravity.CENTER))
            if (ui.preview || ui.dev) addView(banner().apply { alpha = 0.92f }, FrameLayout.LayoutParams(W.MATCH, m.px(14), Gravity.TOP))
        })
        val list = LinearLayout(c).apply { orientation = LinearLayout.VERTICAL; setPadding(m.px(8), m.px(4), m.px(8), 0); layoutParams = W.lp(W.MATCH, 0, 1f) }
        list.addView(W.row(c, m, "ic_search_20", "Discover", null, 23, { ui.push(DiscoverScreen(ui)) }))
        list.addView(W.row(c, m, "ic_grid_20", "Installed", null, 23, { ui.push(InstalledScreen(ui)) }))
        list.addView(W.row(c, m, "ic_refresh_20", "Updates", null, 23, { ui.push(InstalledScreen(ui, updatesOnly = true)) }))
        list.addView(W.row(c, m, "ic_gear_20", "Settings", null, 23, { ui.push(SettingsScreen(ui)) }))
        root.addView(list)
        root.addView(W.hints(c, m, aLabel, bLabel, onA = { ui.host.confirm() }, onB = { ui.back() }))
        return root
    }
}

class DiscoverScreen(ui: Ui) : Screen(ui) {
    override val title = "Discover"

    override fun build(): View {
        val c = ui.ctx; val m = ui.m
        val content = if (ui.listings.isEmpty()) W.empty(c, m, "ic_grid_48", "No apps for ${ui.target.name} yet",
            "Nothing in the catalog is built for this device. Entries for other handhelds are hidden.")
        else {
            val col = W.column(c, m)
            ui.listings.forEach { l ->
                col.addView(W.row(c, m, "ic_package_28", l.app.name, l.app.category.replaceFirstChar { it.uppercase() } + "  -  " + l.app.developer + (if (ui.installedVersion(l) != null) "  -  installed" else ""), 42,
                    { ui.push(DetailsScreen(ui, l)) }, tile = true))
            }
            W.scroll(c, col)
        }
        return frame(content)
    }
}

class DetailsScreen(ui: Ui, private val l: Listing) : Screen(ui) {
    override val title = "App Details"
    private val flow = ui.flow(l)
    private lateinit var dyn: LinearLayout
    private lateinit var root: View
    private var shownKind: Class<*>? = null
    private var bar: ProgressBar? = null
    private var head: TextView? = null
    private var sub: TextView? = null
    private var primary: View? = null

    private fun size(n: Long?): String = when {
        n == null -> "-"
        n >= 1_048_576 -> "%.1f MB".format(n / 1_048_576.0)
        else -> "%d KB".format((n + 1023) / 1024)
    }

    override fun onBack(): Boolean { if (flow.state is InstState.Downloading) { flow.cancelDownload(); return true }; return false }
    override fun initialFocus(root: View): View? = primary?.takeIf { it.isFocusable }

    override fun build(): View {
        val c = ui.ctx; val m = ui.m
        val a = l.artifact
        val col = W.column(c, m, 6)
        col.addView(LinearLayout(c).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            layoutParams = W.lp(W.MATCH, W.WRAP).apply { bottomMargin = m.px(4) }
            addView(FrameLayout(c).apply {
                background = roundRect(Pal.ROW, m.px(6).toFloat())
                addView(icon(c, "ic_package_28", m.px(28), Pal.TXT), FrameLayout.LayoutParams(m.px(28), m.px(28), Gravity.CENTER))
            }, W.lp(m.px(40), m.px(40)).apply { rightMargin = m.px(7) })
            addView(LinearLayout(c).apply {
                orientation = LinearLayout.VERTICAL
                addView(text(c, l.app.name, m.title, Pal.TXT, true).apply { isSingleLine = true; ellipsize = android.text.TextUtils.TruncateAt.END })
                addView(text(c, "by ${l.app.developer}", m.small, Pal.TXT2))
            }, W.lp(0, W.WRAP, 1f))
        })
        // state and the action button come first so they are on screen without scrolling; the description follows
        dyn = LinearLayout(c).apply { orientation = LinearLayout.VERTICAL }
        col.addView(dyn, W.lp(W.MATCH, W.WRAP))
        col.addView(text(c, l.app.description, m.body, Pal.TXT).apply { setPadding(0, m.px(2), 0, m.px(5)); setLineSpacing(0f, 1.05f) }, W.lp(W.MATCH, W.WRAP))
        col.addView(W.table(c, m, listOf(
            "Version" to (a.version ?: "-"), "Device" to ui.target.name,
            "Package" to (a.android?.let { "${it.packageName}  (code ${it.versionCode})" } ?: a.format.uppercase()),
            "License" to l.app.license.let { if (it == "unknown") "Unknown" else it }, "Size" to size(a.size))))
        if (l.app.source.startsWith("https://") && !l.app.source.contains(".invalid") && !l.app.source.contains("retrohatch-fixture")) {
            col.addView(W.row(c, m, "ic_info_20", "Website", null, 24, {
                try { ui.host.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(l.app.source))) }
                catch (e: Exception) { Toast.makeText(ui.ctx, "No browser available", Toast.LENGTH_SHORT).show() }
            }))
        }
        root = frame(W.scroll(c, col))
        flow.onChange = { s -> render(s) }
        flow.refresh()
        render(flow.state)
        return root
    }

    private fun pct(s: InstState.Downloading) = if (s.total > 0) (100 * s.done / s.total).toInt().coerceIn(0, 100) else 0

    private fun render(s: InstState) {
        val c = ui.ctx; val m = ui.m
        if (s is InstState.Downloading && shownKind == InstState.Downloading::class.java && bar != null) {   // progress tick: no rebuild, the focus stays
            bar!!.progress = pct(s); head?.text = "Downloading  ${pct(s)}%"; sub?.text = "${size(s.done)} of ${size(s.total)}"
            return
        }
        val hadFocus = ui.host.currentFocus.let { it != null && isInside(dyn, it) }
        shownKind = s.javaClass
        dyn.removeAllViews(); bar = null
        val (title, detail, color) = when (s) {
            is InstState.Unavailable -> Triple(if (ui.preview) "Preview only" else "Not available", s.reason, if (ui.preview) Pal.ERR else Pal.TXT)
            is InstState.Ready ->
                if (s.installed != null) Triple("Update available", "Installed code ${s.installed}; the signed catalog has ${l.artifact.android!!.versionCode}. ${size(l.artifact.size)}.", Pal.ACC)
                else Triple("Ready to download", "Verified build for ${ui.target.name}, ${size(l.artifact.size)}. It is checked against the signed SHA-256 before anything is installed.", Pal.TXT)
            is InstState.Downloading -> Triple("Downloading  ${pct(s)}%", "${size(s.done)} of ${size(s.total)}", Pal.ACC)
            InstState.Verifying -> Triple("Verifying", "Checking size, SHA-256, package name and signing certificate.", Pal.ACC)
            InstState.Downloaded -> Triple("Ready to install", "SHA-256, package and signing certificate match the catalog. Android will ask you to confirm.", Pal.GREEN)
            InstState.Installing -> Triple("Waiting for Android", "Confirm in the system installer screen.", Pal.ACC)
            InstState.NeedsPermission -> Triple("Allow installs", "Turn on \"Allow from this source\" for RetroHatch in Android's settings, come back, and press Install.", Pal.ACC)
            InstState.InstallCancelled -> Triple("Install cancelled", "You declined in Android's installer. Nothing was installed.", Pal.TXT)
            is InstState.Installed -> Triple("Installed", "Version code ${s.versionCode} is on this device.", Pal.GREEN)
            is InstState.Failed -> Triple("Error", s.message, Pal.ERR)
        }
        dyn.addView(LinearLayout(c).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = roundRect(Pal.CARD, m.px(5).toFloat(), Pal.LINE, 1)
            setPadding(m.px(8), m.px(5), m.px(8), m.px(5))
            layoutParams = W.lp(W.MATCH, W.WRAP).apply { bottomMargin = m.px(4) }
            val ic = when (s) {
                is InstState.Installed -> "ic_check_20"; is InstState.Failed -> "ic_alert_48"
                is InstState.Downloading, InstState.Verifying, InstState.Installing -> "ic_download_20"; else -> "ic_lock_24"
            }
            addView(icon(c, ic, m.px(24), color), W.lp(m.px(24), m.px(24)).apply { rightMargin = m.px(7) })
            addView(LinearLayout(c).apply {
                orientation = LinearLayout.VERTICAL
                head = text(c, title, m.body, color, true)
                sub = text(c, detail, m.small, Pal.TXT2).apply { setPadding(0, m.px(1), 0, 0) }
                addView(head); addView(sub)
                if (s is InstState.Downloading) { bar = W.progress(c, m, pct(s)); addView(bar) }
            }, W.lp(0, W.WRAP, 1f))
        })
        primary = null
        when (s) {
            is InstState.Unavailable -> primary = W.button(c, m, if (ui.preview) "Install unavailable (preview)" else "Install unavailable", false) {}
            is InstState.Ready -> primary = W.button(c, m, if (s.installed != null) "Update" else "Download", true) { flow.primary() }
            is InstState.Downloading -> {
                dyn.addView(W.button(c, m, "Downloading...", false) {})
                primary = W.button(c, m, "Cancel download", true, primary = false) { flow.cancelDownload() }
            }
            InstState.Verifying -> primary = W.button(c, m, "Verifying...", false) {}
            InstState.Downloaded, InstState.InstallCancelled, InstState.NeedsPermission -> primary = W.button(c, m, "Install", true) { flow.primary() }
            InstState.Installing -> primary = W.button(c, m, "Installing...", false) {}
            is InstState.Installed -> {
                val launch = ui.ctx.packageManager.getLaunchIntentForPackage(l.artifact.android!!.packageName)
                if (launch != null) {
                    dyn.addView(W.button(c, m, "Installed", false) {})
                    primary = W.button(c, m, "Open", true, primary = false) { try { ui.host.startActivity(launch) } catch (e: Exception) { } }
                } else primary = W.button(c, m, "Installed", false) {}
            }
            is InstState.Failed -> primary = W.button(c, m, if (s.message == "Download cancelled") "Download again" else "Try again", true) { flow.primary() }
        }
        dyn.addView(primary)
        root.findViewWithTag<TextView>("label:B")?.text = if (s is InstState.Downloading) "Cancel" else "Back"
        if (hadFocus || !ui.host.isTouchMode()) primary?.takeIf { it.isFocusable }?.requestFocus()
    }

    private fun isInside(parent: View, v: View): Boolean {
        var p: android.view.ViewParent? = v.parent
        while (p != null) { if (p === parent) return true; p = p.parent }
        return false
    }
}

/** Catalog apps (for this device) that are on the device. [updatesOnly]: only those older than the signed catalog's versionCode. */
class InstalledScreen(ui: Ui, private val updatesOnly: Boolean = false) : Screen(ui) {
    override val title = if (updatesOnly) "Updates" else "Installed"
    override fun build(): View {
        val c = ui.ctx; val m = ui.m
        val rows = ui.listings.filter { it.installable && ui.verified }.mapNotNull { l ->
            val inst = ui.installedVersion(l) ?: return@mapNotNull null
            val want = l.artifact.android!!.versionCode
            if (updatesOnly == (inst < want)) Triple(l, inst, want) else null
        }
        val content = if (rows.isEmpty()) {
            if (updatesOnly) W.empty(c, m, "ic_refresh_48", "No updates available", "All of your applications are up to date.")
            else W.empty(c, m, "ic_grid_48", "No installed applications", "You haven't installed any applications with RetroHatch yet.")
        } else {
            val col = W.column(c, m)
            rows.forEach { (l, inst, want) ->
                col.addView(W.row(c, m, "ic_package_28", l.app.name, if (updatesOnly) "code $inst  ->  $want" else "Installed  -  code $inst", 42, { ui.push(DetailsScreen(ui, l)) }, tile = true))
            }
            W.scroll(c, col)
        }
        return frame(content, showPreview = false)
    }
}

class SettingsScreen(ui: Ui) : Screen(ui) {
    override val title = "Settings"
    override fun build(): View {
        val c = ui.ctx; val m = ui.m
        val col = W.column(c, m, 8)
        col.addView(W.row(c, m, "ic_phone_20", "Device Information", null, 28, { ui.push(InfoScreen(ui, "Device Information", deviceRows(), null)) }))
        col.addView(W.row(c, m, "ic_database_20", "Catalog Status", null, 28, { ui.push(InfoScreen(ui, "Catalog Status", catalogRows(), trustNote())) }))
        col.addView(W.row(c, m, "ic_info_20", "About RetroHatch", null, 28, { ui.push(InfoScreen(ui, "About", aboutRows(), null)) }))
        return frame(W.scroll(c, col), showPreview = false)
    }

    private fun deviceRows(): List<Pair<String, String>> {
        val wb = ui.host.windowManager.maximumWindowMetrics.bounds
        val am = ui.ctx.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val mi = ActivityManager.MemoryInfo().also { am.getMemoryInfo(it) }
        val dpad = InputDevice.getDeviceIds().toList().mapNotNull { InputDevice.getDevice(it) }.any { (it.sources and InputDevice.SOURCE_DPAD) == InputDevice.SOURCE_DPAD }
        return listOf(
            "Device" to "${Build.MANUFACTURER} ${Build.MODEL}".trim(),
            "Profile" to "${ui.target.id} (${ui.target.packageFormat.uppercase()})",
            "OS" to "Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})",
            "Arch" to (Build.SUPPORTED_ABIS.firstOrNull() ?: "?"),
            "Display" to "${wb.width()} x ${wb.height()}",
            "Memory" to "${mi.totalMem / 1_048_576} MB",
            "D-pad" to if (dpad) "detected" else "not detected",
        )
    }

    private fun catalogRows(): List<Pair<String, String>> {
        val src = ui.loaded.source
        val total = ui.loaded.catalog.apps.size
        return listOf(
            "Source" to when (src) { is CatalogSource.Signed -> if (src.dev) "DEV fixture catalog (test key)" else "Signed catalog"; is CatalogSource.Preview -> "PREVIEW sample (unsigned)" },
            "Trust" to when (src) { is CatalogSource.Signed -> "serial ${src.serial}, key ${src.keyId}"; is CatalogSource.Preview -> src.reason },
            "Pinned key id" to Trust.keyId(Trust.PRODUCTION_KEY_HEX.chunked(2).map { it.toInt(16).toByte() }.toByteArray()),
            "Entries" to "$total in catalog",
            "For ${ui.target.name}" to "${ui.listings.size}",
            "Hidden" to "${DeviceFilter.hiddenCount(ui.loaded.catalog, ui.target)} for other devices",
        )
    }

    private fun trustNote() = if (ui.preview) "Only a catalog signed by the pinned production key is shown as real. Until one is published, apps shown here are labelled PREVIEW and cannot be installed."
    else if (ui.dev) "DEBUG build: catalogs signed with the DEV fixture key are accepted and shown as DEV. Release builds trust only the production key." else null

    private fun aboutRows() = listOf(
        "App" to "RetroHatch for ${ui.target.name}", "Version" to "0.2.0-m2", "Install" to "Download, verify, then the Android installer",
        "Trust" to "Same Ed25519 signing key and catalog format as RetroHatch for RG Nano",
    )
}

class InfoScreen(ui: Ui, override val title: String, private val rows: List<Pair<String, String>>, private val note: String?) : Screen(ui) {
    override fun build(): View {
        val c = ui.ctx; val m = ui.m
        val col = W.column(c, m, 8)
        col.addView(W.table(c, m, rows))
        if (note != null) col.addView(text(c, note, m.small, Pal.TXT2).apply { setPadding(m.px(2), m.px(2), m.px(2), 0) }, W.lp(W.MATCH, W.WRAP))
        return frame(W.scroll(c, col), showPreview = false)
    }
}
