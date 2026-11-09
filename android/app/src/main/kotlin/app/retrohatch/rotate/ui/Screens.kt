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
import app.retrohatch.rotate.model.CatalogSource
import app.retrohatch.rotate.model.DeviceFilter
import app.retrohatch.rotate.model.DeviceProfile
import app.retrohatch.rotate.model.Listing
import app.retrohatch.rotate.model.LoadedCatalog
import app.retrohatch.rotate.model.Trust

/** Everything a screen needs. */
class Ui(val host: MainActivity, val m: Metrics, val width: Int, val loaded: LoadedCatalog, val target: DeviceProfile) {
    val listings: List<Listing> = DeviceFilter.forDevice(loaded.catalog, target)
    val preview: Boolean get() = loaded.source is CatalogSource.Preview
    val ctx: Context get() = host
    fun push(s: Screen) = host.push(s)
    fun back() = host.back()
}

abstract class Screen(val ui: Ui) {
    abstract val title: String
    abstract fun build(): View
    open val aLabel = "Select"
    open val bLabel = "Back"

    /** Rows that D-pad / L1 / R1 move between (in order). */
    open fun focusables(root: View): List<View> = ArrayList<View>().also { collect(root, it) }

    private fun collect(v: View, out: MutableList<View>) {
        if (v.isFocusable && v.isEnabled && v.visibility == View.VISIBLE && v.isClickable) out.add(v)
        if (v is android.view.ViewGroup) for (i in 0 until v.childCount) collect(v.getChildAt(i), out)
    }

    /** Standard frame: header, optional preview strip, content, hint bar. */
    protected fun frame(content: View, showPreview: Boolean = ui.preview): View {
        val c = ui.ctx; val m = ui.m
        return LinearLayout(c).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Pal.BG)
            addView(W.header(c, m, title, ui.width))
            if (showPreview) addView(W.previewStrip(c, m))
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
            if (ui.preview) addView(W.previewStrip(c, m).apply { alpha = 0.92f }, FrameLayout.LayoutParams(W.MATCH, m.px(14), Gravity.TOP))
        })
        val list = LinearLayout(c).apply { orientation = LinearLayout.VERTICAL; setPadding(m.px(8), m.px(4), m.px(8), 0); layoutParams = W.lp(W.MATCH, 0, 1f) }
        list.addView(W.row(c, m, "ic_search_20", "Discover", null, 23, { ui.push(DiscoverScreen(ui)) }))
        list.addView(W.row(c, m, "ic_grid_20", "Installed", null, 23, { ui.push(InstalledScreen(ui)) }))
        list.addView(W.row(c, m, "ic_refresh_20", "Updates", null, 23, { ui.push(UpdatesScreen(ui)) }))
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
                col.addView(W.row(c, m, "ic_package_28", l.app.name, l.app.category.replaceFirstChar { it.uppercase() } + "  -  " + l.app.developer, 42,
                    { ui.push(DetailsScreen(ui, l)) }, tile = true))
            }
            W.scroll(c, col)
        }
        return frame(content)
    }
}

class DetailsScreen(ui: Ui, private val l: Listing) : Screen(ui) {
    override val title = "App Details"

    private fun size(n: Long?): String = when {
        n == null -> "-"
        n >= 1_048_576 -> "%.1f MB".format(n / 1_048_576.0)
        else -> "%d KB".format((n + 1023) / 1024)
    }

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
        col.addView(text(c, l.app.description, m.body, Pal.TXT).apply { setPadding(0, m.px(2), 0, m.px(5)); setLineSpacing(0f, 1.05f) }, W.lp(W.MATCH, W.WRAP))

        // status panel (the Nano's "Not available" card)
        val reason = when {
            ui.preview -> "Preview sample. This entry comes from offline sample data, not a signed catalog."
            !a.available -> a.unavailableReason ?: "A verified build for ${ui.target.name} is not available yet."
            else -> "Verified build for ${ui.target.name}. Installing arrives in the next milestone."
        }
        col.addView(LinearLayout(c).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = roundRect(Pal.CARD, m.px(5).toFloat(), Pal.LINE, 1)
            setPadding(m.px(8), m.px(5), m.px(8), m.px(5))
            layoutParams = W.lp(W.MATCH, W.WRAP).apply { bottomMargin = m.px(4) }
            addView(icon(c, "ic_lock_24", m.px(24), if (ui.preview || !a.available) Pal.TXT2 else Pal.GREEN), W.lp(m.px(24), m.px(24)).apply { rightMargin = m.px(7) })
            addView(LinearLayout(c).apply {
                orientation = LinearLayout.VERTICAL
                addView(text(c, if (ui.preview) "Preview only" else if (a.available) "Verified" else "Not available", m.body, if (ui.preview) Pal.ERR else Pal.TXT, true))
                addView(text(c, reason, m.small, Pal.TXT2).apply { setPadding(0, m.px(1), 0, 0) })
            }, W.lp(0, W.WRAP, 1f))
        })
        col.addView(W.table(c, m, listOf(
            "Version" to (a.version ?: "-"), "Device" to ui.target.name, "Package" to a.format.uppercase(),
            "License" to l.app.license.let { if (it == "unknown") "Unknown" else it }, "Size" to size(a.size))))
        if (l.app.source.startsWith("https://") && !l.app.source.contains(".invalid")) {
            col.addView(W.row(c, m, "ic_info_20", "Website", null, 24, {
                try { ui.host.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(l.app.source))) }
                catch (e: Exception) { Toast.makeText(ui.ctx, "No browser available", Toast.LENGTH_SHORT).show() }
            }))
        }
        col.addView(W.button(c, m, if (l.installable && !ui.preview) "Install (arrives in M2)" else "Install unavailable", enabled = false) {})
        return frame(W.scroll(c, col))
    }
}

class InstalledScreen(ui: Ui) : Screen(ui) {
    override val title = "Installed"
    override fun build() = frame(W.empty(ui.ctx, ui.m, "ic_grid_48", "No installed applications",
        "Installing apps from RetroHatch arrives in the next milestone."), showPreview = false)
}

class UpdatesScreen(ui: Ui) : Screen(ui) {
    override val title = "Updates"
    override fun build() = frame(W.empty(ui.ctx, ui.m, "ic_refresh_48", "No updates available",
        "Nothing is installed through RetroHatch yet."), showPreview = false)
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
            "Source" to when (src) { is CatalogSource.Signed -> "Signed catalog"; is CatalogSource.Preview -> "PREVIEW sample (unsigned)" },
            "Trust" to when (src) { is CatalogSource.Signed -> "serial ${src.serial}, key ${src.keyId}"; is CatalogSource.Preview -> src.reason },
            "Pinned key id" to Trust.keyId(Trust.PRODUCTION_KEY_HEX.chunked(2).map { it.toInt(16).toByte() }.toByteArray()),
            "Entries" to "$total in catalog",
            "For ${ui.target.name}" to "${ui.listings.size}",
            "Hidden" to "${DeviceFilter.hiddenCount(ui.loaded.catalog, ui.target)} for other devices",
        )
    }

    private fun trustNote() = if (ui.preview) "Only a catalog signed by the pinned production key is shown as real. Until one is published, apps shown here are labelled PREVIEW and cannot be installed."
    else null

    private fun aboutRows() = listOf(
        "App" to "RetroHatch for ${ui.target.name}", "Version" to "0.1.0-m1", "Scope" to "Browse only; install arrives in M2",
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
