package app.retrohatch.rotate.ui

import android.content.Context
import android.graphics.Typeface
import android.text.TextUtils
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/** Screen chrome and controls. All interactive controls are native Android views (Button, focusable rows, ScrollView); the art is the project's PNGs. */
object W {
    fun lp(w: Int, h: Int, weight: Float = 0f): LinearLayout.LayoutParams = LinearLayout.LayoutParams(w, h, weight)
    const val MATCH = ViewGroup.LayoutParams.MATCH_PARENT
    const val WRAP = ViewGroup.LayoutParams.WRAP_CONTENT

    /** Title bar: the forest band of Header.png (cropped, not stretched) with the screen title on a light scrim. */
    fun header(c: Context, m: Metrics, title: String, width: Int): View {
        val h = m.px(32)
        return FrameLayout(c).apply {
            layoutParams = lp(MATCH, h)
            addView(ImageView(c).apply {
                setImageBitmap(Art.cropped(c, "art_header_band", width, h, top = 219f / 793f, bottom = 650f / 793f))
                scaleType = ImageView.ScaleType.FIT_XY   // bitmap already has the exact aspect
            }, FrameLayout.LayoutParams(MATCH, MATCH))
            addView(View(c).apply { setBackgroundColor(0x66000000) }, FrameLayout.LayoutParams(MATCH, MATCH))
            addView(text(c, title, m.title, Pal.TXT, true).apply { gravity = Gravity.CENTER; setShadowLayer(m.u * 1.5f, 0f, m.u, 0xFF000000.toInt()) },
                FrameLayout.LayoutParams(MATCH, MATCH))
        }
    }

    /** Red strip that must be visible wherever catalog apps are listed while the data is not a verified signed catalog. */
    fun previewStrip(c: Context, m: Metrics): View = text(c, "PREVIEW ONLY  -  offline sample data, not a signed catalog", m.tiny, Pal.ERR, true).apply {
        gravity = Gravity.CENTER
        setBackgroundColor(Pal.ROW)
        isSingleLine = true; ellipsize = TextUtils.TruncateAt.END
        layoutParams = lp(MATCH, m.px(14))
    }

    private fun badge(c: Context, m: Metrics, letter: String, color: Int): View = text(c, letter, m.small, Pal.BG, true).apply {
        gravity = Gravity.CENTER
        background = roundRect(color, m.px(6).toFloat())
        layoutParams = lp(m.px(12), m.px(12))
    }

    /** A / B hint bar. Touch: tap A to activate the highlighted row, B to go back. Keys: A = confirm, B = back. */
    fun hints(c: Context, m: Metrics, aLabel: String, bLabel: String, onA: () -> Unit, onB: () -> Unit): View = LinearLayout(c).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        layoutParams = lp(MATCH, m.px(22))
        setPadding(m.px(10), 0, m.px(10), 0)
        fun pill(letter: String, color: Int, label: String, go: () -> Unit) = LinearLayout(c).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(m.px(4), m.px(2), m.px(6), m.px(2))
            addView(badge(c, m, letter, color))
            addView(text(c, label, m.body, Pal.TXT).apply { setPadding(m.px(4), 0, 0, 0) })
            isClickable = true
            isFocusable = false     // D-pad focus belongs to the list; A/B are hardware buttons here
            setOnClickListener { go() }
        }
        addView(pill("A", Pal.GREEN, aLabel, onA))
        addView(View(c), lp(0, 1, 1f))
        addView(pill("B", Pal.ACC, bLabel, onB))
    }

    /** Focusable list row: [icon] title / subtitle  >   Highlighted orange when focused or pressed. */
    fun row(c: Context, m: Metrics, iconName: String?, title: String, subtitle: String?, heightNano: Int, onClick: () -> Unit, enabled: Boolean = true,
            titleSize: Float = m.body, tile: Boolean = false): View = LinearLayout(c).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        background = rowBackground(m)
        setPadding(m.px(5), 0, m.px(5), 0)
        layoutParams = lp(MATCH, m.px(heightNano)).apply { bottomMargin = m.px(2) }
        dpadFocusable()
        isEnabled = enabled
        if (iconName != null) {
            val sz = if (tile) m.px(heightNano - 10) else m.px(20)
            val ic = icon(c, iconName, if (tile) m.px(28) else m.px(20), if (enabled) Pal.TXT else Pal.DIS, follow = !tile)   // tile icons stay cream on their dark tile
            if (tile) addView(FrameLayout(c).apply {
                isDuplicateParentStateEnabled = true
                background = roundRect(Pal.ROW, m.px(4).toFloat())
                addView(ic, FrameLayout.LayoutParams(m.px(28), m.px(28), Gravity.CENTER))
            }, lp(sz, sz).apply { rightMargin = m.px(6) })
            else addView(ic, lp(m.px(20), m.px(20)).apply { rightMargin = m.px(7) })
        }
        val col = LinearLayout(c).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER_VERTICAL; isDuplicateParentStateEnabled = true }
        col.addView(text(c, title, titleSize, Pal.TXT, true).apply {
            setTextColor(focusTint(if (enabled) Pal.TXT else Pal.DIS)); isDuplicateParentStateEnabled = true; isSingleLine = true; ellipsize = TextUtils.TruncateAt.END
        })
        if (subtitle != null) col.addView(text(c, subtitle, m.small, Pal.TXT2).apply {
            setTextColor(focusTint(Pal.TXT2)); isDuplicateParentStateEnabled = true; isSingleLine = true; ellipsize = TextUtils.TruncateAt.END
        })
        addView(col, lp(0, WRAP, 1f))
        addView(icon(c, "ic_chevron_16", m.px(16), Pal.TXT2, follow = true))
        setOnClickListener { if (isEnabled) onClick() }
    }

    fun scroll(c: Context, content: View): ScrollView = ScrollView(c).apply {
        isFillViewport = true
        isVerticalScrollBarEnabled = false
        isFocusable = true                      // lets the D-pad scroll a page that has no focusable rows
        descendantFocusability = ViewGroup.FOCUS_AFTER_DESCENDANTS
        defaultFocusHighlightEnabled = false
        layoutParams = lp(MATCH, 0, 1f)
        addView(content, ViewGroup.LayoutParams(MATCH, WRAP))
    }

    fun column(c: Context, m: Metrics, pad: Int = 4): LinearLayout = LinearLayout(c).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(m.px(pad), m.px(4), m.px(pad), m.px(4))
    }

    /** Key/value card (Device Information, details). */
    fun table(c: Context, m: Metrics, rows: List<Pair<String, String>>): View = LinearLayout(c).apply {
        orientation = LinearLayout.VERTICAL
        background = roundRect(Pal.CARD, m.px(5).toFloat(), Pal.LINE, 1)
        setPadding(m.px(8), m.px(4), m.px(8), m.px(4))
        layoutParams = lp(MATCH, WRAP).apply { bottomMargin = m.px(4) }
        rows.forEachIndexed { i, (k, v) ->
            addView(LinearLayout(c).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(0, m.px(3), 0, m.px(3))
                addView(text(c, k, m.body, Pal.TXT2), lp(m.px(70), WRAP))
                addView(text(c, v, m.body, Pal.TXT).apply { gravity = Gravity.START or Gravity.CENTER_VERTICAL }, lp(0, WRAP, 1f))
            })
            if (i < rows.size - 1) addView(View(c).apply { setBackgroundColor(Pal.LINE) }, lp(MATCH, 1))
        }
    }

    /** Centered empty state with one of the Nano's large icons (same pattern as the Nano's Installed / Updates screens). */
    fun empty(c: Context, m: Metrics, iconName: String, title: String, body: String): View = LinearLayout(c).apply {
        orientation = LinearLayout.VERTICAL
        gravity = Gravity.CENTER
        layoutParams = lp(MATCH, 0, 1f)
        setPadding(m.px(16), 0, m.px(16), 0)
        addView(icon(c, iconName, m.px(48), Pal.GREEN), lp(m.px(48), m.px(48)).apply { bottomMargin = m.px(8) })
        addView(text(c, title, m.title, Pal.TXT, true).apply { gravity = Gravity.CENTER }, lp(MATCH, WRAP))
        addView(text(c, body, m.body, Pal.TXT2).apply { gravity = Gravity.CENTER; setPadding(0, m.px(4), 0, 0) }, lp(MATCH, WRAP))
    }

    /** Native Button, orange when usable, flat grey when not. */
    fun button(c: Context, m: Metrics, label: String, enabled: Boolean, onClick: () -> Unit): Button = Button(c).apply {
        text = label
        isAllCaps = false
        setTextSize(android.util.TypedValue.COMPLEX_UNIT_PX, m.body)
        typeface = Typeface.create("sans-serif-medium", Typeface.BOLD)
        isEnabled = enabled
        setTextColor(if (enabled) Pal.ONACC else Pal.DIS)
        stateListAnimator = null
        background = if (enabled) roundRect(Pal.ACC, m.px(5).toFloat()) else roundRect(Pal.CARD, m.px(5).toFloat(), Pal.LINE, 1)
        layoutParams = lp(MATCH, m.px(26)).apply { topMargin = m.px(4) }
        isFocusable = true
        setOnClickListener { onClick() }
    }
}
