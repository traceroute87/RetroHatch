package app.retrohatch.rotate.ui

import android.app.Activity
import android.content.Context
import android.os.Bundle
import android.view.KeyEvent
import android.view.View
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.widget.FrameLayout
import app.retrohatch.rotate.DevHooks
import app.retrohatch.rotate.model.CatalogLoader
import app.retrohatch.rotate.model.LoadedCatalog
import app.retrohatch.rotate.model.Targets
import app.retrohatch.rotate.model.TrustState
import java.io.File

/**
 * Single-activity host. Screens are plain views kept on a back stack. Input:
 *   touch                       tap a row; tap A / B in the hint bar
 *   D-pad                       move the highlight (native focus search), A / Enter / D-pad centre = select
 *   B / Escape / system Back    back (on Home: leave the app)
 *   L1 / R1                     jump four rows
 */
class MainActivity : Activity() {
    private lateinit var root: FrameLayout
    private lateinit var ui: Ui
    private class Entry(val screen: Screen, val view: View, var focus: View? = null)
    private val stack = ArrayList<Entry>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val b = windowManager.currentWindowMetrics.bounds
        val side = minOf(b.width(), b.height())
        root = FrameLayout(this).apply { setBackgroundColor(Pal.BG) }
        setContentView(root)
        window.insetsController?.let { it.hide(WindowInsets.Type.systemBars()); it.systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE }
        DevHooks.init(this)
        ui = Ui(this, Metrics(side / 240f), b.width(), loadCatalog(), Targets.RG_ROTATE)
        push(HomeScreen(ui))
    }

    /** A signed catalog (app files first, then the bundled one) is used only if it verifies against the pinned key; otherwise the PREVIEW sample. */
    private fun loadCatalog(): LoadedCatalog {
        fun read(f: File) = if (f.isFile) f.readBytes() else null
        fun asset(p: String) = try { assets.open(p).use { it.readBytes() } } catch (e: java.io.IOException) { null }
        val fi = read(File(filesDir, "catalog/index.json")); val fs = read(File(filesDir, "catalog/index.json.sig"))
        val index = fi ?: asset("catalog/index.json"); val sig = if (fi != null) fs else asset("catalog/index.json.sig")
        val prefs = getSharedPreferences("trust", Context.MODE_PRIVATE)
        val st = if (prefs.contains("serial")) TrustState(prefs.getLong("serial", 0), prefs.getString("sha256", "") ?: "") else null
        val r = CatalogLoader.load(index, sig, asset("preview/index.json"), state = st, devKeys = DevHooks.devKeys(this))
        r.newState?.let { prefs.edit().putLong("serial", it.serial).putString("sha256", it.sha256).apply() }
        return r
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
