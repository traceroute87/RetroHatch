package app.retrohatch.rotate.ui

import android.app.Activity
import android.os.Bundle
import android.view.KeyEvent
import android.view.View
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.widget.FrameLayout
import app.retrohatch.rotate.DevHooks
import app.retrohatch.rotate.android.FileCatalogStore
import app.retrohatch.rotate.model.CatalogRepository
import app.retrohatch.rotate.model.Trust
import app.retrohatch.rotate.model.LoadedCatalog
import app.retrohatch.rotate.model.Targets
import java.io.File

/**
 * Single-activity host. Screens are plain views kept on a back stack. Input:
 *   touch                       tap a row; tap A / B in the hint bar
 *   D-pad                       move the highlight (native focus search), A / Enter / D-pad centre = select
 *   B / Escape / system Back    back (on Home: leave the app)
 *   L1 / R1                     jump four rows (App Details: scroll a page)
 */
class MainActivity : Activity() {
    private lateinit var root: FrameLayout
    private lateinit var ui: Ui
    private class Entry(val screen: Screen, var view: View, var focus: View? = null)
    private val stack = ArrayList<Entry>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val b = windowManager.currentWindowMetrics.bounds
        val side = minOf(b.width(), b.height())
        root = FrameLayout(this).apply { setBackgroundColor(Pal.BG) }
        setContentView(root)
        window.insetsController?.let { it.hide(WindowInsets.Type.systemBars()); it.systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE }
        DevHooks.init(this)
        ui = Ui(this, Metrics(side / 240f), b.width(), loadCatalog(), Targets.RG_ROTATE, store)
        push(HomeScreen(ui))
        if (savedInstanceState == null) ui.refresh()   // once per start: fetch, verify, cache; on any failure the cached catalog stays
    }

    private val store by lazy { FileCatalogStore(this) }

    private var resumed = false
    /** Back from Android's installer / uninstaller / permission screen or from a launched app: re-read the device (installed versions, Open, Uninstall). */
    override fun onResume() {
        super.onResume()
        if (resumed && ::ui.isInitialized) ui.onResume()
        resumed = true
    }

    /**
     * The best catalog we can VERIFY: the last valid online one from the cache (production or, in debug builds, DEV), else a bundled signed snapshot,
     * else the PREVIEW sample. Everything is verified again against the pinned keys and the rollback state on every start.
     */
    private fun loadCatalog(): LoadedCatalog {
        fun asset(p: String) = try { assets.open(p).use { it.readBytes() } } catch (e: java.io.IOException) { null }
        val bi = asset("catalog/index.json"); val bs = asset("catalog/index.json.sig")
        val di = asset("dev/catalog/index.json"); val ds = asset("dev/catalog/index.json.sig")   // debug builds only (src/debug/assets)
        return CatalogRepository.load(store, Trust.PRODUCTION_KEYS, DevHooks.devKeys(this), if (bi != null && bs != null) Pair(bi, bs) else null, asset("preview/index.json"),
            if (di != null && ds != null) Pair(di, ds) else null)
    }

    /** A refresh stored a new verified catalog. */
    fun reloadCatalog() { ui.setCatalog(loadCatalog()); rebuildAll() }

    /** Rebuild every screen on the stack from the current state (catalog, refresh status) and put the highlight back where it was. */
    fun rebuildAll() {
        if (stack.isEmpty()) return
        val top = stack.last()
        val idx = focusables().indexOf(currentFocus)
        stack.forEach { e ->
            val v = e.screen.build()
            if (e === top) { root.removeView(e.view); root.addView(v, FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT)) }
            e.view = v; e.focus = null
        }
        top.view.post { if (!top.view.isInTouchMode) (focusables().getOrNull(maxOf(idx, 0)) ?: focusables().firstOrNull())?.requestFocus() }
    }

    fun push(s: Screen) {
        stack.lastOrNull()?.let { it.focus = currentFocus; root.removeView(it.view) }
        val v = s.build()
        stack.add(Entry(s, v))
        root.addView(v, FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT))
        v.post { if (!v.isInTouchMode) focusFirst() }
    }

    fun isTouchMode(): Boolean = root.isInTouchMode

    fun back() {
        if (stack.lastOrNull()?.screen?.onBack() == true) return
        if (stack.size <= 1) { finish(); return }
        val gone = stack.removeAt(stack.size - 1)
        root.removeView(gone.view)
        val e = stack.last()
        root.addView(e.view, FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT))
        e.view.post { if (!e.view.isInTouchMode) (e.focus ?: focusables().firstOrNull())?.requestFocus() }
    }

    /** The A button / hint-bar A: activate the highlighted row (or the first one). */
    fun confirm() { (currentFocus ?: focusables().firstOrNull())?.performClick() }

    private fun focusables(): List<View> = stack.lastOrNull()?.let { it.screen.focusables(it.view) } ?: emptyList()
    private fun focusFirst() {
        val e = stack.lastOrNull() ?: return
        (e.screen.initialFocus(e.view) ?: focusables().firstOrNull())?.requestFocus()
    }

    private fun jump(dir: Int) {
        if (stack.lastOrNull()?.screen?.onShoulder(dir) == true) return
        val f = focusables(); if (f.isEmpty()) return
        val i = f.indexOf(currentFocus).let { if (it < 0) 0 else it }
        f[(i + dir * 4).coerceIn(0, f.size - 1)].requestFocus()
    }

    override fun dispatchKeyEvent(e: KeyEvent): Boolean {
        val k = e.keyCode
        val up = e.action == KeyEvent.ACTION_UP
        when (k) {
            KeyEvent.KEYCODE_BUTTON_B, KeyEvent.KEYCODE_ESCAPE, KeyEvent.KEYCODE_BACK -> { if (up) back(); return true }
            KeyEvent.KEYCODE_BUTTON_A -> { if (up) confirm(); return true }
            KeyEvent.KEYCODE_BUTTON_L1, KeyEvent.KEYCODE_PAGE_UP -> { if (up) jump(-1); return true }
            KeyEvent.KEYCODE_BUTTON_R1, KeyEvent.KEYCODE_PAGE_DOWN -> { if (up) jump(1); return true }
            KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_DPAD_DOWN, KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_RIGHT -> {
                if (currentFocus == null && e.action == KeyEvent.ACTION_DOWN) { focusFirst(); if (currentFocus != null) return true }
            }
        }
        return super.dispatchKeyEvent(e)
    }
}
