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
import android.widget.ScrollView
import android.widget.EditText
import android.text.Editable
import android.text.TextWatcher
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import app.retrohatch.rotate.model.Discover
import app.retrohatch.rotate.model.DiscoverQuery
import app.retrohatch.rotate.model.Filter
import app.retrohatch.rotate.model.Groups
import app.retrohatch.rotate.model.Presence
import app.retrohatch.rotate.model.Sort
import android.text.TextUtils
import android.widget.Toast
import android.widget.ProgressBar
import android.widget.TextView
import java.io.File
import java.text.DateFormat
import java.util.Date
import java.util.concurrent.Executors
import app.retrohatch.rotate.DevHooks
import app.retrohatch.rotate.android.InstallEvents
import app.retrohatch.rotate.android.InstalledApp
import app.retrohatch.rotate.android.Uninstaller
import app.retrohatch.rotate.android.PmApkInspector
import app.retrohatch.rotate.android.PmPackageState
import app.retrohatch.rotate.android.SessionInstaller
import app.retrohatch.rotate.model.CatalogConfig
import app.retrohatch.rotate.model.CatalogSource
import app.retrohatch.rotate.model.CatalogStore
import app.retrohatch.rotate.model.CatalogUpdater
import app.retrohatch.rotate.model.RefreshResult
import app.retrohatch.rotate.model.RefreshStatus
import app.retrohatch.rotate.model.Downloader
import app.retrohatch.rotate.model.InstState
import app.retrohatch.rotate.model.InstallFlow
import app.retrohatch.rotate.model.DeviceFilter
import app.retrohatch.rotate.model.DeviceProfile
import app.retrohatch.rotate.model.Listing
import app.retrohatch.rotate.model.LoadedCatalog
import app.retrohatch.rotate.model.Trust

/** Everything a screen needs. */
class Ui(val host: MainActivity, val m: Metrics, val width: Int, initial: LoadedCatalog, val target: DeviceProfile, val store: CatalogStore) {
    var loaded: LoadedCatalog = initial
        private set
    /** Entries for THIS device only (device id, firmware and apk format must all match): Nano OPKs and other devices never appear. */
    val listings: List<Listing> get() = DeviceFilter.forDevice(loaded.catalog, target)
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

    private val worker = Executors.newSingleThreadExecutor()          // downloads
    private val netWorker = Executors.newSingleThreadExecutor()       // catalog refresh: never waits behind a download
    private val uiHandler = android.os.Handler(android.os.Looper.getMainLooper())
    private val flows = HashMap<String, InstallFlow>()
    private val packages = PmPackageState(host)
    private val updater = CatalogUpdater({ u, max -> Downloader(mapUrl = DevHooks::mapUrl).fetch(u, max) }, store, Trust.PRODUCTION_KEYS, DevHooks.devKeys(host))

    @Volatile var refreshing = false
        private set

    /** A new verified catalog is in place: idle install flows are rebuilt from the new entries; one that is downloading keeps going. */
    fun setCatalog(l: LoadedCatalog) { loaded = l; flows.entries.removeAll { !it.value.busy } }

    /** Fetch, verify and cache the online catalog in the background. Screens are rebuilt when it ends. A rejected or failed refresh changes nothing but the status. */
    fun refresh() {
        if (refreshing || !DevHooks.refreshEnabled) return   // debug build on real hardware: no emulator-only server, bundled catalog only
        refreshing = true
        host.rebuildAll()
        netWorker.execute {
            val r = updater.refresh()
            uiHandler.post {
                refreshing = false
                if (r is RefreshResult.Updated) host.reloadCatalog() else host.rebuildAll()
            }
        }
    }

    fun refreshStatus(): RefreshStatus? = store.status()

    /** One install flow per catalog entry, kept alive while the app runs so a download continues when the screen is left. */
    fun flow(l: Listing): InstallFlow = flows.getOrPut(l.app.id) {
        val f = InstallFlow(l, verified, File(host.filesDir, "downloads"), Downloader(mapUrl = DevHooks::mapUrl, allowedRedirectHosts = app.retrohatch.rotate.model.TrustedSources.redirectHosts(l.artifact.url)),
            PmApkInspector(host), packages, SessionInstaller(host), worker) { uiHandler.post(it) }
        f.deviceSdk = Build.VERSION.SDK_INT
        l.artifact.android?.let { a -> InstallEvents.listen(a.packageName) { e -> f.onInstallEvent(e); noteInstalledChange(rebuildTop = false) } }
        f
    }

    /** One string for "which catalog packages are installed, and which versionCode". A change is the only reason to rebuild screens after a system screen closes. */
    private fun snapshot(): String = listings.mapNotNull { it.artifact.android?.packageName }.joinToString(",") { (packages.installedVersion(it) ?: 0L).toString() }
    private var seen: String = snapshot()

    private fun noteInstalledChange(rebuildTop: Boolean) {
        val now = snapshot()
        if (now == seen) return
        seen = now
        host.rebuildAll(includeTop = rebuildTop)
    }

    /** What Android says about this entry's package (null: not installed). Needs only the manifest's launcher-activity <queries>, not QUERY_ALL_PACKAGES. */
    fun installed(l: Listing): InstalledApp? = l.artifact.android?.let { packages.info(it.packageName) }

    /** Managed = the installed copy carries the signing certificate the signed catalog names. Anything else is somebody else's build of that package name. */
    fun managed(l: Listing, a: InstalledApp): Boolean = l.artifact.android?.signerSha256?.map { it.lowercase() }?.let { want -> a.signers.any { it in want } } == true

    /** Never true for a downgrade or an equal build, and never for a copy the catalog's key cannot update. */
    fun updateAvailable(l: Listing, a: InstalledApp): Boolean = managed(l, a) && (l.artifact.android?.versionCode ?: 0L) > a.versionCode

    /** What Discover is showing (search text, category, sort, filter). Kept here so it survives opening an app and coming back. */
    var query = DiscoverQuery()

    fun presence(l: Listing): Presence = installed(l).let { a ->
        when { a == null -> Presence.NOT_INSTALLED; updateAvailable(l, a) -> Presence.UPDATE; else -> Presence.INSTALLED }
    }

    /** Catalog apps (this device, verified catalog) that are on the device. */
    fun installedListings(): List<Pair<Listing, InstalledApp>> =
        if (!verified) emptyList() else listings.filter { it.installable }.mapNotNull { l -> installed(l)?.let { l to it } }

    /** Android's own uninstall confirmation; the result is picked up in [onResume]. */
    fun uninstall(l: Listing): Boolean = l.artifact.android?.let { Uninstaller.start(host, it.packageName) } ?: false

    /** Back from an installer, uninstaller, settings or launched app: re-read what is on the device. */
    fun onResume() {
        if (snapshot() == seen) return                                    // dialog cancelled, app opened and left: nothing changed, nothing is touched (focus stays)
        flows.values.forEach { it.refresh() }                             // Details pages update themselves through their flow
        noteInstalledChange(rebuildTop = host.topScreen() !is DetailsScreen)
    }
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
        if (ui.dev) W.previewStrip(ui.ctx, ui.m, "EXPERIMENTAL DEV CATALOG  -  " + (if ((ui.source as? CatalogSource.Signed)?.cached == true) "cached" else "bundled, offline") + "  -  test key", Pal.ACC) else W.previewStrip(ui.ctx, ui.m)

        /** Standard frame: header (with a touch back arrow), optional preview strip, content, hint bar. */
    protected fun frame(content: View, showPreview: Boolean = ui.preview || ui.dev): View {
        val c = ui.ctx; val m = ui.m
        return LinearLayout(c).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Pal.BG)
            addView(W.header(c, m, title, ui.width, onBack = { ui.host.back() }))
            if (showPreview) addView(banner())
            addView(content)
            addView(W.hints(c, m, aLabel, bLabel, onA = { ui.host.confirm() }, onB = { ui.back() }))
        }
    }

    /** The screen shows state other screens change (Discover: the search / category / sort kept in Ui): rebuild it when it comes back to the front. */
    open val rebuildOnReturn = false

    /** L1 / R1: return true if this screen scrolled or moved by itself; false = the host jumps four rows. */
    open fun onShoulder(dir: Int): Boolean = false

    protected fun versionText(v: String?, code: Long?) = v?.let { "v$it" } ?: code?.let { "code $it" } ?: "-"
    protected fun size(n: Long?): String = when {
        n == null -> "-"
        n >= 1_048_576 -> "%.1f MB".format(n / 1_048_576.0)
        else -> "%d KB".format((n + 1023) / 1024)
    }
}

class HomeScreen(ui: Ui) : Screen(ui) {
    override val title = "RetroHatch"
    override val bLabel = "Exit"

    override fun build(): View {
        val c = ui.ctx; val m = ui.m
        val root = LinearLayout(c).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(Pal.BG) }
        val bannerH = m.px(104)
        // forest from Header2.png (cropped to the banner shape, never stretched) with the logo from Retro_Hatch.png on top
        root.addView(FrameLayout(c).apply {
            layoutParams = W.lp(W.MATCH, bannerH)
            addView(ImageView(c).apply {
                setImageBitmap(Art.cropped(c, "art_forest", ui.width, bannerH, top = 0f, bottom = 0.78f, anchorY = 0.15f))
                scaleType = ImageView.ScaleType.FIT_XY
            }, FrameLayout.LayoutParams(W.MATCH, W.MATCH))
            addView(ImageView(c).apply {
                setImageBitmap(Art.fit(c, "art_logo", m.px(95), m.px(95)))
                scaleType = ImageView.ScaleType.FIT_CENTER
            }, FrameLayout.LayoutParams(W.MATCH, m.px(95), Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL))   // sits below the experimental strip, never under it
            if (ui.preview || ui.dev) addView(banner().apply { alpha = 0.94f }, FrameLayout.LayoutParams(W.MATCH, m.px(13), Gravity.TOP))
        })
        val inst = ui.installedListings(); val upd = inst.count { (l, a) -> ui.updateAvailable(l, a) }
        val list = LinearLayout(c).apply { orientation = LinearLayout.VERTICAL; setPadding(m.px(8), m.px(5), m.px(8), 0); layoutParams = W.lp(W.MATCH, 0, 1f) }
        list.addView(W.row(c, m, "compass", "Discover", null, 25, { ui.push(DiscoverScreen(ui)) }, trailing = ui.listings.size.takeIf { it > 0 }?.toString()))
        list.addView(W.row(c, m, "layout-grid", "Installed", null, 25, { ui.push(InstalledScreen(ui)) }, trailing = inst.size.takeIf { it > 0 }?.toString()))
        list.addView(W.row(c, m, "refresh-cw", "Updates", null, 25, { ui.push(InstalledScreen(ui, updatesOnly = true)) }, status = if (upd > 0) "$upd new" to Pal.ACC else null))
        list.addView(W.row(c, m, "settings", "Settings", null, 25, { ui.push(SettingsScreen(ui)) }))
        root.addView(list)
        root.addView(W.hints(c, m, aLabel, bLabel, onA = { ui.host.confirm() }, onB = { ui.back() }))
        return root
    }
}

/** One app row (Discover, search results): tile with the real icon when installed, name, short description, an Installed / Update chip. */
internal fun appRow(ui: Ui, l: Listing, onOpen: () -> Unit): View {
    val c = ui.ctx; val m = ui.m
    val inst = ui.installed(l)
    val status = when {
        inst == null -> if (l.app.external != null) "External" to Pal.TXT2 else null
        ui.managed(l, inst) && ui.updateAvailable(l, inst) -> "Update" to Pal.ACC
        ui.managed(l, inst) -> "Installed" to Pal.GREEN
        else -> "Installed" to Pal.TXT2
    }
    return W.row(c, m, null, l.app.name, l.app.description.ifBlank { Groups.label(Groups.of(l.app)) }, 36, onOpen, leading = W.tile(c, m, m.px(24), inst?.icon), status = status)
}

/** Browse: a toolbar (Search, Category, Sort / Filter), one line saying what is shown, then the app rows. The query lives in [Ui] so it survives opening an app and coming back. */
class DiscoverScreen(ui: Ui) : Screen(ui) {
    override val title = "Discover"
    override val rebuildOnReturn = true
    private var firstRow: View? = null
    override fun initialFocus(root: View): View? = firstRow

    override fun build(): View {
        val c = ui.ctx; val m = ui.m
        val all = ui.listings
        val q = ui.query
        val shown = Discover.apply(all, q, ui::presence)
        val bar = LinearLayout(c).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(m.px(6), m.px(2), m.px(6), 0)
            layoutParams = W.lp(W.MATCH, W.WRAP)
            fun add(b: View, i: Int) = addView(b, (b.layoutParams as LinearLayout.LayoutParams).also { if (i > 0) it.leftMargin = m.px(4) })
            add(W.button(c, m, if (q.text.isBlank()) "Search" else "\"${q.text.trim()}\"", true, W.Kind.SECONDARY, "search", weight = 1.15f) { ui.push(SearchScreen(ui)) }, 0)
            add(W.button(c, m, if (q.group == null) "Category" else Groups.label(q.group), true, W.Kind.SECONDARY, "layout-grid", weight = 1.2f) { ui.push(CategoryScreen(ui)) }, 1)
            add(W.button(c, m, "Sort", true, W.Kind.SECONDARY, "arrow-up-down", weight = 0.75f) { ui.push(OptionsScreen(ui)) }, 2)
            if (q.active) add(W.button(c, m, "", true, W.Kind.SECONDARY, "x", weight = 0.001f) { ui.query = DiscoverQuery(sort = q.sort); ui.host.rebuildAll() }.also { (it.layoutParams as LinearLayout.LayoutParams).width = m.px(29) }, 3)
        }
        val col = W.column(c, m)
        col.addView(text(c, Discover.summary(q, shown.size, all.size), m.tiny, Pal.TXT2).apply { setPadding(m.px(2), 0, 0, m.px(3)) }, W.lp(W.MATCH, W.WRAP))
        firstRow = null
        if (all.isEmpty()) col.addView(W.empty(c, m, "package-open", "No apps for ${ui.target.name} yet", "Nothing in the catalog is built for this device. Entries for other handhelds are hidden."), W.lp(W.MATCH, W.WRAP))
        else if (shown.isEmpty()) {
            col.addView(W.empty(c, m, "search", "No matching apps", "Nothing matches the current search and filters. Try fewer words or another category.", compact = true))
            col.addView(W.button(c, m, "Clear search and filters", true, W.Kind.PRIMARY, "x") { ui.query = DiscoverQuery(); ui.host.rebuildAll() })
        } else shown.forEach { l -> col.addView(appRow(ui, l) { ui.push(DetailsScreen(ui, l)) }.also { if (firstRow == null) firstRow = it }) }
        val body = LinearLayout(c).apply { orientation = LinearLayout.VERTICAL; layoutParams = W.lp(W.MATCH, 0, 1f); addView(bar); addView(W.scroll(c, col)) }
        return frame(body)
    }
}

/** Category browsing: only categories that hold apps, each with its count. */
class CategoryScreen(ui: Ui) : Screen(ui) {
    override val title = "Categories"
    private val icons = mapOf("games" to "gamepad-2", "emulators" to "cpu", "ports" to "package-open", "utilities" to "wrench", "media" to "music", "themes-launchers" to "palette")
    override fun build(): View {
        val c = ui.ctx; val m = ui.m
        val col = W.column(c, m, 8)
        val groups = Discover.groups(ui.listings)
        col.addView(W.row(c, m, "layout-grid", "All apps", null, 27, { choose(null) }, trailing = ui.listings.size.toString()))
        groups.forEach { (id, label, n) -> col.addView(W.row(c, m, icons[id] ?: "package", label, null, 27, { choose(id) }, trailing = n.toString())) }
        return frame(W.scroll(c, col), showPreview = false)
    }
    private fun choose(g: String?) { ui.query = ui.query.copy(group = g); ui.back(); ui.host.rebuildAll() }
}

/** Sort and filter: tap an option to apply it; the checkmark moves. */
class OptionsScreen(ui: Ui) : Screen(ui) {
    override val title = "Sort and filter"
    override fun build(): View {
        val c = ui.ctx; val m = ui.m
        val col = W.column(c, m, 8)
        col.addView(W.section(c, m, "Sort by"))
        Sort.values().forEach { s -> col.addView(W.row(c, m, if (ui.query.sort == s) "check" else "circle", s.label, null, 23, { ui.query = ui.query.copy(sort = s); ui.host.rebuildAll() }, chevron = false)) }
        col.addView(W.section(c, m, "Show"))
        Filter.values().forEach { f -> col.addView(W.row(c, m, if (ui.query.filter == f) "check" else "circle", f.label, null, 23, { ui.query = ui.query.copy(filter = f); ui.host.rebuildAll() }, chevron = false)) }
        return frame(W.scroll(c, col), showPreview = false)
    }
}

/** Search by app name, description, developer or tag. Typing needs the on-screen keyboard (touch); the results update as you type and open like any other row. */
class SearchScreen(ui: Ui) : Screen(ui) {
    override val title = "Search"
    private var box: EditText? = null
    override fun initialFocus(root: View): View? = box
    override fun focusables(root: View): List<View> = super.focusables(root)

    override fun build(): View {
        val c = ui.ctx; val m = ui.m
        val results = LinearLayout(c).apply { orientation = LinearLayout.VERTICAL; setPadding(m.px(6), m.px(3), m.px(6), m.px(4)) }
        fun refresh(t: String) {
            results.removeAllViews()
            val hits = Discover.apply(ui.listings, DiscoverQuery(text = t), ui::presence)
            if (t.isBlank()) results.addView(text(c, "Type a name, a developer or a word like emulator, music or 2fa.", m.small, Pal.TXT2).apply { setPadding(m.px(4), m.px(6), m.px(4), 0); gravity = Gravity.START })
            else if (hits.isEmpty()) results.addView(text(c, "No apps match \"${t.trim()}\".", m.body, Pal.TXT2).apply { setPadding(m.px(4), m.px(6), m.px(4), 0); gravity = Gravity.START })
            else hits.forEach { l -> results.addView(appRow(ui, l) { ui.query = ui.query.copy(text = t.trim()); ui.push(DetailsScreen(ui, l)) }) }
        }
        val field = EditText(c).apply {
            setText(ui.query.text); setSelection(text.length)
            hint = "Search apps"
            setHintTextColor(Pal.DIS); setTextColor(Pal.TXT); setTextSize(android.util.TypedValue.COMPLEX_UNIT_PX, m.body)
            isSingleLine = true; imeOptions = EditorInfo.IME_ACTION_SEARCH; inputType = android.text.InputType.TYPE_CLASS_TEXT
            background = roundRect(Pal.CARD, m.r, Pal.ACC, 3)
            setPadding(m.px(8), 0, m.px(8), 0)
            layoutParams = W.lp(W.MATCH, m.px(29)).apply { setMargins(m.px(6), m.px(4), m.px(6), 0) }
            addTextChangedListener(object : TextWatcher {
                override fun afterTextChanged(s: Editable?) { val t = s?.toString().orEmpty(); ui.query = ui.query.copy(text = t); refresh(t) }
                override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, d: Int) {}
                override fun onTextChanged(s: CharSequence?, a: Int, b: Int, d: Int) {}
            })
            setOnEditorActionListener { v, _, _ -> (ui.ctx.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager).hideSoftInputFromWindow(v.windowToken, 0); true }
        }
        box = field
        refresh(ui.query.text)
        val body = LinearLayout(c).apply { orientation = LinearLayout.VERTICAL; layoutParams = W.lp(W.MATCH, 0, 1f); addView(field); addView(W.scroll(c, results)) }
        return frame(body, showPreview = false)
    }
}

/** An app-store page: hero, what's happening / what you can do, then Overview, Features, App information and Compatibility (each only with real content). */
class DetailsScreen(ui: Ui, private val l: Listing) : Screen(ui) {
    override val title = "App Details"
    private val flow = ui.flow(l)
    private lateinit var dyn: LinearLayout
    private lateinit var root: View
    private var scroller: ScrollView? = null
    private var shownKind: Class<*>? = null
    private var bar: ProgressBar? = null
    private var head: TextView? = null
    private var sub: TextView? = null
    private var primary: View? = null
    private var hero: FrameLayout? = null
    private var heroKey: Any? = null
    private var lastWanted: String? = null

    override fun onBack(): Boolean { if (flow.state is InstState.Downloading) { flow.cancelDownload(); return true }; return false }
    override fun initialFocus(root: View): View? = primary?.takeIf { it.isFocusable }
    override fun onShoulder(dir: Int): Boolean { val s = scroller ?: return false; s.smoothScrollBy(0, dir * (s.height * 3 / 4)); return true }

    override fun build(): View {
        val c = ui.ctx; val m = ui.m
        val a = l.artifact
        val inst = ui.installed(l)
        val col = W.column(c, m, 8)
        // hero: icon, name, developer, then the facts people look at first
        col.addView(LinearLayout(c).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            layoutParams = W.lp(W.MATCH, W.WRAP).apply { bottomMargin = m.px(3) }
            addView(FrameLayout(c).also { hero = it; heroKey = inst?.versionCode; it.addView(W.tile(c, m, m.px(40), inst?.icon)) }, W.lp(m.px(40), m.px(40)).apply { rightMargin = m.px(8) })
            addView(LinearLayout(c).apply {
                orientation = LinearLayout.VERTICAL
                addView(text(c, l.app.name, m.big, Pal.TXT, true).apply { isSingleLine = true; ellipsize = TextUtils.TruncateAt.END })
                addView(text(c, "by ${l.app.developer}", m.small, Pal.TXT2).apply { setPadding(0, m.px(1), 0, m.px(3)); isSingleLine = true; ellipsize = TextUtils.TruncateAt.END })
                addView(LinearLayout(c).apply {
                    orientation = LinearLayout.HORIZONTAL
                    fun chip(t: String, color: Int) = addView(W.chip(c, m, t, color), W.lp(W.WRAP, W.WRAP).apply { rightMargin = m.px(3) })
                    a.version?.let { chip("v$it", Pal.TXT2) }
                    if (a.size != null) chip(size(a.size), Pal.TXT2)
                    if (l.app.external != null) chip("EXTERNAL LISTING", Pal.ACC) else if (a.level != "verified") chip("EXPERIMENTAL", Pal.ACC)
                })
            }, W.lp(0, W.WRAP, 1f))
        })
        // state and the actions come first so they are on screen without scrolling
        dyn = LinearLayout(c).apply { orientation = LinearLayout.VERTICAL }
        col.addView(dyn, W.lp(W.MATCH, W.WRAP))

        col.addView(W.section(c, m, "Overview"))
        col.addView(W.paragraphs(c, m, listOfNotNull(l.app.description.takeIf { it.isNotBlank() }, l.app.longDescription).joinToString("\n\n").ifBlank { "No description is available." }, firstBold = l.app.longDescription != null))

        if (l.app.features.isNotEmpty()) { col.addView(W.section(c, m, "Features")); col.addView(W.bullets(c, m, l.app.features)) }

        col.addView(W.section(c, m, "App information"))
        val info = ArrayList<Pair<String, String>>(); val icons = ArrayList<String?>()
        fun add(k: String, v: String?, ic: String) { info.add(k to (v ?: "Unavailable")); icons.add(ic) }
        add("Developer", l.app.developer.ifBlank { null }, "user")
        add("Version", a.version?.let { v -> a.android?.let { "$v  (code ${it.versionCode})" } ?: v }, "tag")
        add("Download size", a.size?.let { size(it) }, "hard-drive")
        add("License", l.app.license.takeIf { it != "unknown" }, "scale")
        a.android?.let { add("Package", it.packageName, "package") }
        col.addView(W.table(c, m, info, icons))
        if (l.app.source.startsWith("https://") && !l.app.source.contains(".invalid") && !l.app.source.contains("retrohatch-fixture")) {
            col.addView(W.row(c, m, "code", "Source repository", l.app.source.removePrefix("https://"), 25, {
                try { ui.host.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(l.app.source))) }
                catch (e: Exception) { Toast.makeText(ui.ctx, "No browser available", Toast.LENGTH_SHORT).show() }
            }))
        }

        col.addView(W.section(c, m, "Compatibility"))
        val exp = a.level != "verified"
        val ext = l.app.external
        col.addView(W.table(c, m, listOf(
            "Device" to "${ui.target.name}, ${a.firmware.replace("android-", "Android ")}",
            "Status" to if (ext != null) "External listing: RetroHatch does not install this app" else if (exp) "Experimental: not approved or tested on ${ui.target.name}" else "Verified for ${ui.target.name}",
            "Checks" to if (ext != null) "Nothing is downloaded or verified by RetroHatch. Check the listing's licence and requirements yourself." else "SHA-256, package and signer are verified before install"),
            listOf("smartphone", if (ext != null) "external-link" else if (exp) "triangle-alert" else "shield-check", "shield-check")))

        root = frame(W.scroll(c, col).also { scroller = it })
        flow.autoInstall = true
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
        val wanted = (ui.host.currentFocus?.takeIf { isInside(dyn, it) }?.tag as? String) ?: lastWanted   // read BEFORE the old buttons are removed (removing them moves focus away)
        shownKind = s.javaClass
        dyn.removeAllViews(); bar = null
        val inst = ui.installed(l)
        if (inst?.versionCode != heroKey) {                                   // installed, updated or uninstalled: show the app's real icon (or the package icon) now
            heroKey = inst?.versionCode
            hero?.let { h -> h.removeAllViews(); h.addView(W.tile(c, m, m.px(40), inst?.icon)) }
        }
        val managed = inst != null && ui.managed(l, inst)
        val ver = inst?.let { versionText(it.versionName, it.versionCode) } ?: "-"
        // (icon, title, detail, colour)
        val st: List<Any> = when (s) {
            is InstState.Unavailable -> if (l.app.external != null) listOf("external-link", "External listing", l.app.external!!.reason + (l.app.external!!.price?.let { "  Price: $it." } ?: ""), Pal.TXT)
                else listOf(if (ui.preview) "triangle-alert" else "info", if (ui.preview) "Preview only" else "Not available", s.reason, if (ui.preview) Pal.ERR else Pal.TXT)
            is InstState.Ready ->
                if (s.installed != null) listOf("circle-arrow-up", "Update available", "Installed $ver (code ${s.installed}), the catalog has ${versionText(l.artifact.version, l.artifact.android?.versionCode)} (code ${l.artifact.android?.versionCode}). ${size(l.artifact.size)}.", Pal.ACC)
                else listOf("download", "Ready to install", "Checked against the signed SHA-256, package name and signing certificate before Android is asked to install.", Pal.TXT)
            is InstState.Downloading -> listOf("download", "Downloading  ${pct(s)}%", "${size(s.done)} of ${size(s.total)}", Pal.ACC)
            InstState.Verifying -> listOf("shield-check", "Verifying", "Checking size, SHA-256, package name and signing certificate.", Pal.ACC)
            InstState.Downloaded -> listOf("shield-check", "Verified", "SHA-256, package and signing certificate match the catalog. Android will ask you to confirm.", Pal.GREEN)
            InstState.Installing -> listOf("loader-circle", "Waiting for Android", "Confirm in the system installer screen.", Pal.ACC)
            InstState.NeedsPermission -> listOf("lock", "Allow installs", "Turn on \"Allow from this source\" for RetroHatch in Android's settings, come back, and press Install.", Pal.ACC)
            InstState.InstallCancelled -> listOf("info", "Install cancelled", "You declined in Android's installer. Nothing was installed.", Pal.TXT)
            is InstState.Installed ->
                if (managed || inst == null) listOf("circle-check", "Installed", "Version $ver is on this device. You have the newest version in the catalog.", Pal.GREEN)
                else listOf("info", "Installed from another source", "Version $ver is on this device but is not signed with the catalog's key, so RetroHatch cannot update it.", Pal.TXT)
            is InstState.Failed -> listOf("triangle-alert", "Error", s.message, Pal.ERR)
        }
        val color = st[3] as Int
        dyn.addView(LinearLayout(c).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = roundRect(Pal.CARD, m.r, if (s is InstState.Failed) Pal.ERR else Pal.LINE, 2)
            setPadding(m.px(8), m.px(6), m.px(8), m.px(6))
            layoutParams = W.lp(W.MATCH, W.WRAP).apply { topMargin = m.px(3); bottomMargin = m.px(3) }
            addView(icon(c, st[0] as String, m.px(14), color), W.lp(m.px(14), m.px(14)).apply { rightMargin = m.px(8) })
            addView(LinearLayout(c).apply {
                orientation = LinearLayout.VERTICAL
                head = text(c, st[1] as String, m.body, color, true)
                sub = text(c, st[2] as String, m.small, Pal.TXT2).apply { setPadding(0, m.px(1), 0, 0); setLineSpacing(0f, 1.08f); gravity = Gravity.START }
                addView(head); addView(sub)
                if (s is InstState.Downloading) { bar = W.progress(c, m, pct(s)); addView(bar) }
            }, W.lp(0, W.WRAP, 1f))
        })
        // actions: Install / Update / Cancel / Try again by state, then Open and Uninstall whenever the app is on the device and nothing is in flight
        val acts = ArrayList<View>()
        val busy = s is InstState.Downloading || s === InstState.Verifying || s === InstState.Installing
        val updating = inst != null && (s is InstState.Ready || s === InstState.Downloaded || s === InstState.NeedsPermission || s === InstState.InstallCancelled)
        when (s) {
            is InstState.Unavailable -> l.app.external?.let { x ->
                acts.add(W.button(c, m, "Open ${x.label}".take(26), true, iconName = "external-link", weight = 1f) {
                    try { ui.host.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(x.url))) } catch (e: Exception) { Toast.makeText(ui.ctx, "No browser available", Toast.LENGTH_SHORT).show() }
                })
            } ?: acts.add(W.button(c, m, "Not available", false, iconName = "circle-x", weight = 1f) {})
            is InstState.Ready -> acts.add(W.button(c, m, if (s.installed != null) "Update" else "Install", true, iconName = if (s.installed != null) "circle-arrow-up" else "download", weight = 1f) { flow.primary() })
            is InstState.Downloading -> acts.add(W.button(c, m, "Cancel download", true, W.Kind.SECONDARY, "x", weight = 1f) { flow.cancelDownload() })
            InstState.Verifying -> acts.add(W.button(c, m, "Verifying...", false, iconName = "shield-check", weight = 1f) {})
            InstState.Installing -> acts.add(W.button(c, m, "Installing...", false, iconName = "loader-circle", weight = 1f) {})
            InstState.Downloaded, InstState.InstallCancelled, InstState.NeedsPermission ->
                acts.add(W.button(c, m, if (updating) "Update" else "Install", true, iconName = if (updating) "circle-arrow-up" else "package-plus", weight = 1f) { flow.primary() })
            is InstState.Installed -> {}
            is InstState.Failed -> acts.add(W.button(c, m, if (s.message == "Download cancelled") "Download again" else "Try again", true, iconName = "refresh-cw", weight = 1f) { flow.primary() })
        }
        if (inst != null && !busy) {
            inst.launch?.let { intent ->
                acts.add(W.button(c, m, "Open", true, if (acts.isEmpty()) W.Kind.PRIMARY else W.Kind.SECONDARY, "external-link", weight = 1f) {
                    try { ui.host.startActivity(intent) } catch (e: Exception) { Toast.makeText(ui.ctx, "Could not open the app", Toast.LENGTH_SHORT).show() }
                })
            }
            if (!inst.system) acts.add(W.button(c, m, "Uninstall", true, W.Kind.DANGER, "trash-2", weight = 1f) {
                if (!ui.uninstall(l)) Toast.makeText(ui.ctx, "Could not open Android's uninstall screen", Toast.LENGTH_SHORT).show()
            })
        }
        // stable keys so the selected action can be found again after the state (and the buttons) changed
        val keys = acts.indices.map { i -> if (i == 0 && s !is InstState.Installed) "main" else null }.toMutableList()
        acts.forEachIndexed { i, b -> b.tag = keys[i] ?: (b as? LinearLayout)?.let { ll -> (ll.getChildAt(ll.childCount - 1) as? TextView)?.text?.toString()?.lowercase() } }
        primary = acts.firstOrNull { it.tag == wanted && it.isFocusable } ?: acts.firstOrNull { it.isFocusable }
        if (acts.isNotEmpty()) dyn.addView(LinearLayout(c).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = W.lp(W.MATCH, W.WRAP)
            acts.forEachIndexed { i, b -> addView(b, (b.layoutParams as LinearLayout.LayoutParams).also { if (i > 0) it.leftMargin = m.px(5) }) }
        })
        if (inst != null && !inst.system && !busy)
            dyn.addView(text(c, "Uninstall removes the app and may delete its data. Android asks you to confirm; nothing is removed silently.", m.tiny, Pal.TXT2).apply {
                setPadding(m.px(2), m.px(2), m.px(2), 0); gravity = Gravity.START
            }, W.lp(W.MATCH, W.WRAP))
        root.findViewWithTag<TextView>("label:B")?.text = if (s is InstState.Downloading) "Cancel" else "Back"
        lastWanted = primary?.tag as? String
        if (hadFocus || !ui.host.isTouchMode()) primary?.requestFocus()
    }

    private fun isInside(parent: View, v: View): Boolean {
        var p: android.view.ViewParent? = v.parent
        while (p != null) { if (p === parent) return true; p = p.parent }
        return false
    }
}

/** Catalog apps (for this device) that are on the device, with Android's real version and icon. [updatesOnly]: only managed apps older than the signed catalog. */
class InstalledScreen(ui: Ui, private val updatesOnly: Boolean = false) : Screen(ui) {
    override val title = if (updatesOnly) "Updates" else "Installed"
    override fun build(): View {
        val c = ui.ctx; val m = ui.m
        val rows = ui.installedListings().filter { (l, a) -> !updatesOnly || ui.updateAvailable(l, a) }
        val content = if (rows.isEmpty()) {
            if (updatesOnly) W.empty(c, m, "circle-check-big", "No updates available", "All of your applications are up to date.", Pal.GREEN)
            else W.empty(c, m, "package-open", "No installed applications", "Apps you install from Discover appear here, with their installed version.")
        } else {
            val col = W.column(c, m)
            rows.forEach { (l, a) ->
                val have = versionText(a.versionName, a.versionCode)
                val managed = ui.managed(l, a); val upd = ui.updateAvailable(l, a)
                val sub = when {
                    upd -> "$have  ->  ${versionText(l.artifact.version, l.artifact.android?.versionCode)}"
                    !managed -> "$have  -  installed from another source"
                    a.system -> "$have  -  system app"
                    else -> "$have  -  up to date"
                }
                col.addView(W.row(c, m, null, l.app.name, sub, 36, { ui.push(DetailsScreen(ui, l)) }, leading = W.tile(c, m, m.px(24), a.icon),
                    status = if (upd) "Update" to Pal.ACC else if (!managed) "Other source" to Pal.TXT2 else null))
            }
            W.scroll(c, col)
        }
        return frame(content, showPreview = false)
    }
}

class SettingsScreen(ui: Ui) : Screen(ui) {
    override val title = "Settings"

    private fun when_(st: RefreshStatus) = DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT).format(Date(st.atMs))

    override fun build(): View {
        val c = ui.ctx; val m = ui.m
        val col = W.column(c, m, 8)
        val st = ui.refreshStatus()
        val sub = if (ui.refreshing) "Refreshing..." else st?.text ?: "Not refreshed yet"
        val online = DevHooks.refreshEnabled
        col.addView(W.row(c, m, if (online) "wifi" else "wifi-off", "Refresh Catalog", if (online) sub else "Off: this build uses its bundled experimental catalog", 30, { ui.refresh() }, enabled = online && !ui.refreshing))
        col.addView(W.row(c, m, "database", "Catalog Status", null, 30, { ui.push(InfoScreen(ui, "Catalog Status", { catalogRows() }, { trustNote() })) }))
        col.addView(W.row(c, m, "smartphone", "Device Information", null, 30, { ui.push(InfoScreen(ui, "Device Information", { deviceRows() }, { null })) }))
        col.addView(W.row(c, m, "info", "About RetroHatch", null, 30, { ui.push(InfoScreen(ui, "About", { aboutRows() }, { null })) }))
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
        val st = ui.refreshStatus()
        return listOf(
            "Source" to when (src) {
                is CatalogSource.Signed -> (if (src.dev) "DEV fixture catalog" else "Signed catalog") + if (src.cached) " (cached)" else " (bundled)"
                is CatalogSource.Preview -> "PREVIEW sample (unsigned)"
            },
            "Trust" to when (src) { is CatalogSource.Signed -> "serial ${src.serial}, key ${src.keyId}"; is CatalogSource.Preview -> src.reason },
            "Refresh" to (if (!DevHooks.refreshEnabled) "off: debug build on hardware, bundled experimental catalog only" else if (ui.refreshing) "in progress..." else st?.let { "${when_(it)}: ${it.text}" } ?: "never"),
            "Online" to if (DevHooks.refreshEnabled) DevHooks.mapUrl(CatalogConfig.BASE).removePrefix("https://") else "not used (no catalog published)",
            "Pinned key" to Trust.keyId(Trust.PRODUCTION_KEY_HEX.chunked(2).map { it.toInt(16).toByte() }.toByteArray()),
            "Entries" to "$total in catalog",
            "For ${ui.target.name}" to "${ui.listings.size}",
            "Hidden" to "${DeviceFilter.hiddenCount(ui.loaded.catalog, ui.target)} for other devices",
        )
    }

    private fun trustNote() = if (ui.preview) "Only a catalog signed by the pinned production key is shown as real. Until one is published, apps shown here are labelled PREVIEW and cannot be installed."
    else if (ui.dev) "DEBUG build: catalogs signed with the DEV fixture key are accepted and shown as DEV; their cache and rollback state are kept apart from production. Release builds trust only the production key." else null

    private fun aboutRows() = listOf(
        "App" to "RetroHatch for ${ui.target.name}", "Version" to "0.4.0", "Catalog" to "Online, signed, cached for offline use",
        "Install" to "Download, verify, then the Android installer",
        "Trust" to "Same Ed25519 signing key and catalog format as RetroHatch for RG Nano",
    )
}

class InfoScreen(ui: Ui, override val title: String, private val rows: () -> List<Pair<String, String>>, private val note: () -> String?) : Screen(ui) {
    override fun build(): View {
        val c = ui.ctx; val m = ui.m
        val col = W.column(c, m, 8)
        col.addView(W.table(c, m, rows()))
        note()?.let { n -> col.addView(text(c, n, m.small, Pal.TXT2).apply { setPadding(m.px(2), m.px(3), m.px(2), 0); gravity = Gravity.START; setLineSpacing(0f, 1.08f) }, W.lp(W.MATCH, W.WRAP)) }
        return frame(W.scroll(c, col), showPreview = false)
    }
}
