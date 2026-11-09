package app.retrohatch.rotate.ui

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Typeface
import android.graphics.drawable.Drawable
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.StateListDrawable
import android.text.TextUtils
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView

/** Screen chrome and controls. All interactive controls are native Android views (focusable rows, ScrollView); art is the project's PNGs, icons are Lucide. */
object W {
    fun lp(w: Int, h: Int, weight: Float = 0f): LinearLayout.LayoutParams = LinearLayout.LayoutParams(w, h, weight)
    const val MATCH = ViewGroup.LayoutParams.MATCH_PARENT
    const val WRAP = ViewGroup.LayoutParams.WRAP_CONTENT

    /** Title bar: the forest band of Header.png (cropped, not stretched) with a back arrow (touch) and the screen title. */
    fun header(c: Context, m: Metrics, title: String, width: Int, onBack: (() -> Unit)? = null): View {
        val h = m.px(28)
        return FrameLayout(c).apply {
            layoutParams = lp(MATCH, h)
            addView(ImageView(c).apply {
                setImageBitmap(Art.cropped(c, "art_header_band", width, h, top = 219f / 793f, bottom = 650f / 793f))
                scaleType = ImageView.ScaleType.FIT_XY   // bitmap already has the exact aspect
            }, FrameLayout.LayoutParams(MATCH, MATCH))
            addView(View(c).apply { setBackgroundColor(0x80000000.toInt()) }, FrameLayout.LayoutParams(MATCH, MATCH))
            val shadow = { t: TextView -> t.setShadowLayer(m.u * 1.5f, 0f, m.u, 0xFF000000.toInt()) }
            if (onBack != null) {
                addView(icon(c, "arrow-left", m.px(13), Pal.TXT).apply {
                    setPadding(m.px(8), m.px(8), m.px(8), m.px(8)); layoutParams = FrameLayout.LayoutParams(h, h, Gravity.START)
                    isClickable = true; isFocusable = false; setOnClickListener { onBack() }   // touch only: D-pad focus belongs to the list, B goes back
                    background = StateListDrawable().apply { addState(intArrayOf(android.R.attr.state_pressed), roundRect(0x55E9A23B, m.r)) }
                }, FrameLayout.LayoutParams(h, h, Gravity.START))
                addView(text(c, title, m.title, Pal.TXT, true).apply { shadow(this); isSingleLine = true; ellipsize = TextUtils.TruncateAt.END },
                    FrameLayout.LayoutParams(MATCH, MATCH).apply { marginStart = h; marginEnd = h })
            } else addView(text(c, title, m.title, Pal.TXT, true).apply { shadow(this); gravity = Gravity.CENTER }, FrameLayout.LayoutParams(MATCH, MATCH))
        }
    }

    /** Strip that must be visible wherever catalog apps are listed while the data is not a production-signed catalog (red: PREVIEW, orange: DEV catalog). */
    fun previewStrip(c: Context, m: Metrics, label: String = "PREVIEW ONLY  -  offline sample data, not a signed catalog", color: Int = Pal.ERR): View = LinearLayout(c).apply {
        gravity = Gravity.CENTER
        orientation = LinearLayout.HORIZONTAL
        setBackgroundColor(Pal.ROW)
        layoutParams = lp(MATCH, m.px(13))
        addView(icon(c, "triangle-alert", m.px(8), color), lp(m.px(8), m.px(8)).apply { rightMargin = m.px(3) })
        addView(text(c, label, m.tiny, color, true).apply { isSingleLine = true; ellipsize = TextUtils.TruncateAt.END })
    }

    private fun badge(c: Context, m: Metrics, letter: String, color: Int): View = text(c, letter, m.small, Pal.BG, true).apply {
        gravity = Gravity.CENTER
        background = roundRect(color, m.px(9).toFloat())
        layoutParams = lp(m.px(12), m.px(12))
    }

    /** A / B hint bar. Touch: tap A to activate the highlighted row, B to go back. Keys: A = confirm, B = back. */
    fun hints(c: Context, m: Metrics, aLabel: String, bLabel: String, onA: () -> Unit, onB: () -> Unit): View = LinearLayout(c).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        layoutParams = lp(MATCH, m.px(20))
        setBackgroundColor(0xFF1E211F.toInt())
        setPadding(m.px(8), 0, m.px(8), 0)
        fun pill(letter: String, color: Int, label: String, go: () -> Unit) = LinearLayout(c).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(m.px(3), m.px(2), m.px(6), m.px(2))
            addView(badge(c, m, letter, color))
            addView(text(c, label, m.small, Pal.TXT).apply { setPadding(m.px(4), 0, 0, 0); tag = "label:$letter" })
            isClickable = true
            isFocusable = false     // D-pad focus belongs to the list; A/B are hardware buttons here
            setOnClickListener { go() }
        }
        addView(pill("A", Pal.GREEN, aLabel, onA))
        addView(View(c), lp(0, 1, 1f))
        addView(pill("B", Pal.ACC, bLabel, onB))
    }

    /** Small rounded label. [follow]: inside a focusable row, so it turns dark on the amber highlight. */
    fun chip(c: Context, m: Metrics, label: String, color: Int, follow: Boolean = false, filled: Boolean = false): TextView = text(c, label, m.tiny, color, true).apply {
        gravity = Gravity.CENTER
        isSingleLine = true
        setPadding(m.px(4), m.px(1.5f), m.px(4), m.px(1.5f))
        val stroke = maxOf(2, m.px(0.7f))
        background = if (filled) roundRect(color, m.px(2.5f).toFloat()).also { setTextColor(Pal.BG) }
        else if (follow) StateListDrawable().apply {
            addState(intArrayOf(android.R.attr.state_focused), roundRect(0, m.px(2.5f).toFloat(), Pal.ONACC, stroke))
            addState(intArrayOf(android.R.attr.state_pressed), roundRect(0, m.px(2.5f).toFloat(), Pal.ONACC, stroke))
            addState(intArrayOf(), roundRect(0, m.px(2.5f).toFloat(), color, stroke))
        } else roundRect(0, m.px(2.5f).toFloat(), color, stroke)
        if (follow && !filled) { setTextColor(focusTint(color)); isDuplicateParentStateEnabled = true }
    }

    /** Rounded square holding an app's icon (the installed app's real icon when Android has it, otherwise the Lucide package). */
    fun tile(c: Context, m: Metrics, sizePx: Int, real: Drawable?): View = FrameLayout(c).apply {
        isDuplicateParentStateEnabled = true
        background = roundRect(Pal.ROW, m.rs * sizePx / m.px(36))
        val inner = (sizePx * 0.72f).toInt()
        if (real != null) addView(ImageView(c).apply { setImageDrawable(real); scaleType = ImageView.ScaleType.FIT_CENTER }, FrameLayout.LayoutParams(inner, inner, Gravity.CENTER))
        else addView(icon(c, "package", (sizePx * 0.55f).toInt(), Pal.TXT2), FrameLayout.LayoutParams((sizePx * 0.55f).toInt(), (sizePx * 0.55f).toInt(), Gravity.CENTER))
    }

    /**
     * Focusable list row: [leading icon or tile] title (+ pill) / subtitle, then a status chip, a trailing text or a chevron. Highlighted amber when focused or pressed.
     * [leading] replaces the icon (app tiles).
     */
    fun row(c: Context, m: Metrics, iconName: String?, title: String, subtitle: String?, heightNano: Int, onClick: () -> Unit, enabled: Boolean = true,
            titleSize: Float = m.body, leading: View? = null, pill: String? = null, status: Pair<String, Int>? = null, trailing: String? = null, chevron: Boolean = true): View = LinearLayout(c).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        background = rowBackground(m)
        setPadding(m.px(6), 0, m.px(6), 0)
        layoutParams = lp(MATCH, m.px(heightNano)).apply { bottomMargin = m.px(3) }
        dpadFocusable()
        isEnabled = enabled
        if (leading != null) addView(leading, lp(m.px(heightNano - 12), m.px(heightNano - 12)).apply { rightMargin = m.px(7) })
        else if (iconName != null) addView(icon(c, iconName, m.px(13), if (enabled) Pal.ACC else Pal.DIS, follow = true), lp(m.px(13), m.px(13)).apply { leftMargin = m.px(2); rightMargin = m.px(8) })
        val col = LinearLayout(c).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER_VERTICAL; isDuplicateParentStateEnabled = true }
        val head = LinearLayout(c).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; isDuplicateParentStateEnabled = true }
        head.addView(text(c, title, titleSize, Pal.TXT, true).apply {
            setTextColor(focusTint(if (enabled) Pal.TXT else Pal.DIS)); isDuplicateParentStateEnabled = true; isSingleLine = true; ellipsize = TextUtils.TruncateAt.END
        }, lp(WRAP, WRAP))
        if (pill != null) head.addView(chip(c, m, pill, Pal.ACC, follow = true), lp(WRAP, WRAP).apply { leftMargin = m.px(5) })
        col.addView(head, lp(WRAP, WRAP))
        if (subtitle != null) col.addView(text(c, subtitle, m.small, Pal.TXT2).apply {
            setTextColor(focusTint(Pal.TXT2)); isDuplicateParentStateEnabled = true; isSingleLine = true; ellipsize = TextUtils.TruncateAt.END; setPadding(0, m.px(1), 0, 0)
        })
        addView(col, lp(0, WRAP, 1f))
        if (status != null) addView(chip(c, m, status.first, status.second, follow = true), lp(WRAP, WRAP).apply { leftMargin = m.px(4) })
        else if (trailing != null) addView(text(c, trailing, m.small, Pal.TXT2, true).apply { setTextColor(focusTint(Pal.TXT2)); isDuplicateParentStateEnabled = true }, lp(WRAP, WRAP).apply { leftMargin = m.px(4) })
        if (chevron) addView(icon(c, "chevron-right", m.px(11), Pal.TXT2, follow = true), lp(m.px(11), m.px(11)).apply { leftMargin = m.px(3) })
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

    fun column(c: Context, m: Metrics, pad: Int = 6): LinearLayout = LinearLayout(c).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(m.px(pad), m.px(5), m.px(pad), m.px(6))
    }

    /** Section heading: small amber caps and a hairline. Only added when the section has real content. */
    fun section(c: Context, m: Metrics, title: String): View = LinearLayout(c).apply {
        orientation = LinearLayout.VERTICAL
        layoutParams = lp(MATCH, WRAP).apply { topMargin = m.px(7); bottomMargin = m.px(3) }
        addView(text(c, title.uppercase(), m.small, Pal.ACC, true).apply { letterSpacing = 0.08f })
        addView(View(c).apply { setBackgroundColor(Pal.LINE) }, lp(MATCH, 2).apply { topMargin = m.px(2) })
    }

    fun card(c: Context, m: Metrics): LinearLayout = LinearLayout(c).apply {
        orientation = LinearLayout.VERTICAL
        background = roundRect(Pal.CARD, m.r, Pal.LINE, 2)
        setPadding(m.px(8), m.px(4), m.px(8), m.px(4))
        layoutParams = lp(MATCH, WRAP).apply { bottomMargin = m.px(3) }
    }

    /** Key/value card (App information, Device Information ...). Each line may carry a Lucide icon. */
    fun table(c: Context, m: Metrics, rows: List<Pair<String, String>>, icons: List<String?> = emptyList()): View = card(c, m).apply {
        rows.forEachIndexed { i, (k, v) ->
            addView(LinearLayout(c).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(0, m.px(4), 0, m.px(4))
                icons.getOrNull(i)?.let { addView(icon(c, it, m.px(10), Pal.TXT2), lp(m.px(10), m.px(10)).apply { rightMargin = m.px(6) }) }
                addView(text(c, k, m.small, Pal.TXT2), lp(m.px(62), WRAP))
                addView(text(c, v, m.body * 0.95f, Pal.TXT).apply { gravity = Gravity.START or Gravity.CENTER_VERTICAL }, lp(0, WRAP, 1f))
            })
            if (i < rows.size - 1) addView(View(c).apply { setBackgroundColor(Pal.LINE) }, lp(MATCH, 1))
        }
    }

    /** Feature list: a check mark and a line each. */
    fun bullets(c: Context, m: Metrics, items: List<String>): View = card(c, m).apply {
        items.forEach { s ->
            addView(LinearLayout(c).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.TOP
                setPadding(0, m.px(3), 0, m.px(3))
                addView(icon(c, "circle-check", m.px(9), Pal.GREEN), lp(m.px(9), m.px(9)).apply { rightMargin = m.px(6); topMargin = m.px(1) })
                addView(text(c, s, m.read, Pal.TXT).apply { gravity = Gravity.START }, lp(0, WRAP, 1f))
            })
        }
    }

    /** Body text: one TextView per paragraph so spacing stays even. */
    fun paragraphs(c: Context, m: Metrics, textBlock: String, firstBold: Boolean = false): View = LinearLayout(c).apply {
        orientation = LinearLayout.VERTICAL
        layoutParams = lp(MATCH, WRAP)
        textBlock.split("\n\n").filter { it.isNotBlank() }.forEachIndexed { i, p ->
            addView(text(c, p.trim(), m.read, Pal.TXT, bold = i == 0 && firstBold).apply {
                gravity = Gravity.START; setLineSpacing(0f, 1.12f); setPadding(m.px(2), 0, m.px(2), m.px(5))
            }, lp(MATCH, WRAP))
        }
    }

    /** Centered empty state with a large Lucide icon. */
    fun empty(c: Context, m: Metrics, iconName: String, title: String, body: String, color: Int = Pal.TXT2, compact: Boolean = false): View = LinearLayout(c).apply {
        orientation = LinearLayout.VERTICAL
        gravity = Gravity.CENTER
        layoutParams = if (compact) lp(MATCH, WRAP) else lp(MATCH, 0, 1f)
        val icon = if (compact) m.px(20) else m.px(36)
        setPadding(m.px(18), if (compact) m.px(10) else 0, m.px(18), m.px(8))
        addView(icon(c, iconName, icon, color), lp(icon, icon).apply { bottomMargin = m.px(if (compact) 5 else 8) })
        addView(text(c, title, if (compact) m.body else m.title, Pal.TXT, true).apply { gravity = Gravity.CENTER }, lp(MATCH, WRAP))
        addView(text(c, body, if (compact) m.small else m.body * 0.9f, Pal.TXT2).apply { gravity = Gravity.CENTER; setPadding(0, m.px(4), 0, 0); setLineSpacing(0f, 1.1f) }, lp(MATCH, WRAP))
    }

    enum class Kind { PRIMARY, SECONDARY, DANGER }

    /**
     * Button: Lucide icon + label, centered. PRIMARY amber, SECONDARY card, DANGER card with a coral label. D-pad focus fills it amber (coral for DANGER) with a cream ring;
     * flat grey when disabled. A plain focusable view: the whole button is the touch target.
     */
    fun button(c: Context, m: Metrics, label: String, enabled: Boolean, kind: Kind = Kind.PRIMARY, iconName: String? = null, weight: Float = 0f, onClick: () -> Unit): View = LinearLayout(c).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER
        val r = m.r
        val ring = maxOf(3, m.px(1.2f))
        val base = when (kind) { Kind.PRIMARY -> Pal.ACC; else -> Pal.ROW }
        val fg = when { !enabled -> Pal.DIS; kind == Kind.PRIMARY -> Pal.ONACC; kind == Kind.DANGER -> Pal.ERR; else -> Pal.TXT }
        val focusFill = if (kind == Kind.DANGER) Pal.ERR else if (kind == Kind.PRIMARY) Pal.ACC_HI else Pal.ACC
        background = if (!enabled) roundRect(Pal.CARD, r, Pal.LINE, 2) else StateListDrawable().apply {
            addState(intArrayOf(android.R.attr.state_focused), roundRect(focusFill, r, Pal.TXT, ring))
            addState(intArrayOf(android.R.attr.state_pressed), roundRect(focusFill, r))
            addState(intArrayOf(), roundRect(base, r, if (kind == Kind.PRIMARY) base else Pal.LINE, 2))
        }
        val tint = if (enabled && kind != Kind.PRIMARY) focusTint(fg) else if (enabled) focusTint(fg) else ColorStateList.valueOf(fg)
        if (iconName != null) addView(ImageView(c).apply {
            setImageDrawable(lucide(c, iconName)); imageTintList = tint; isDuplicateParentStateEnabled = true
        }, lp(m.px(12), m.px(12)).apply { rightMargin = m.px(5) })
        addView(text(c, label, m.body, fg, true).apply { setTextColor(tint); isDuplicateParentStateEnabled = true; isSingleLine = true; ellipsize = TextUtils.TruncateAt.END; gravity = Gravity.CENTER })
        layoutParams = lp(if (weight > 0f) 0 else MATCH, m.px(29), weight).apply { topMargin = m.px(3); bottomMargin = m.px(3) }
        setPadding(m.px(6), 0, m.px(6), 0)
        isEnabled = enabled
        isFocusable = enabled; isFocusableInTouchMode = false; isClickable = enabled
        if (enabled) setOnClickListener { onClick() }
    }

    /** Native horizontal ProgressBar in the accent colour. */
    fun progress(c: Context, m: Metrics, percent: Int): ProgressBar = ProgressBar(c, null, android.R.attr.progressBarStyleHorizontal).apply {
        max = 100; progress = percent
        progressTintList = ColorStateList.valueOf(Pal.ACC)
        progressBackgroundTintList = ColorStateList.valueOf(Pal.ROW)
        layoutParams = lp(MATCH, m.px(4)).apply { topMargin = m.px(4); bottomMargin = m.px(2) }
    }
}
