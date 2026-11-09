package app.retrohatch.rotate.ui

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Rect
import android.graphics.Typeface
import android.graphics.drawable.BitmapDrawable
import android.graphics.drawable.Drawable
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.StateListDrawable
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.widget.ImageView
import android.widget.TextView

/** Sunset Ember palette: the exact values of ui/rh_ui.c (the Nano UI). */
object Pal {
    const val BG = 0xFF171B19.toInt()
    const val CARD = 0xFF272721.toInt()
    const val ROW = 0xFF35352B.toInt()
    const val TXT = 0xFFFFF0D2.toInt()
    const val TXT2 = 0xFFB9B3A3.toInt()
    const val ACC = 0xFFE9A23B.toInt()
    const val ONACC = 0xFF35251D.toInt()
    const val GREEN = 0xFF82A779.toInt()
    const val LINE = 0xFF494638.toInt()
    const val DIS = 0xFF77786E.toInt()
    const val ERR = 0xFFE87555.toInt()
}

/**
 * The Nano UI is 240x240 and RG Rotate is 720x720: exactly 3x. Every size below is in "Nano pixels" and multiplied by [u], so the
 * Android layout keeps the Nano proportions (header 32, rows 42, hint bar 24 ...) on this screen and scales on other screens.
 */
class Metrics(val u: Float) {
    fun px(nano: Float): Int = Math.round(nano * u)
    fun px(nano: Int): Int = px(nano.toFloat())
    val body get() = 10.5f * u
    val title get() = 12f * u
    val small get() = 8f * u
    val tiny get() = 7f * u
}

/** The reused PNG artwork (res/drawable-nodpi, byte-identical copies of the project files). */
object Art {
    private val cache = HashMap<String, Bitmap>()

    private fun load(ctx: Context, name: String): Bitmap = cache.getOrPut("raw:$name") {
        val id = ctx.resources.getIdentifier(name, "drawable", ctx.packageName)
        val o = BitmapFactory.Options().apply { inScaled = false }
        BitmapFactory.decodeResource(ctx.resources, id, o) ?: throw IllegalStateException("missing art $name")
    }

    /** Halve repeatedly (box-ish) before the last bilinear step: large artwork stays sharp when it is shrunk a lot. */
    fun scaled(src: Bitmap, w: Int, h: Int): Bitmap {
        var b = src
        while (b.width / 2 >= w && b.height / 2 >= h) b = Bitmap.createScaledBitmap(b, b.width / 2, b.height / 2, true)
        return if (b.width == w && b.height == h) b else Bitmap.createScaledBitmap(b, w, h, true)
    }

    /** Crop `fx..` (fractions of the source) to the aspect of w x h without stretching, then scale to w x h. */
    fun cropped(ctx: Context, name: String, w: Int, h: Int, left: Float = 0f, top: Float = 0f, right: Float = 1f, bottom: Float = 1f, anchorY: Float = 0.5f): Bitmap =
        cache.getOrPut("crop:$name:$w:$h:$left:$top:$right:$bottom:$anchorY") {
            val s = load(ctx, name)
            val r = Rect((s.width * left).toInt(), (s.height * top).toInt(), (s.width * right).toInt(), (s.height * bottom).toInt())
            val want = w.toFloat() / h
            var cw = r.width(); var ch = r.height()
            if (cw.toFloat() / ch > want) cw = (ch * want).toInt() else ch = (cw / want).toInt()
            val x = r.left + (r.width() - cw) / 2
            val y = r.top + ((r.height() - ch) * anchorY).toInt()
            scaled(Bitmap.createBitmap(s, x, y, cw, ch), w, h)
        }

    /** A whole image fitted inside w x h (aspect kept). */
    fun fit(ctx: Context, name: String, w: Int, h: Int): Bitmap = cache.getOrPut("fit:$name:$w:$h") {
        val s = load(ctx, name)
        val k = minOf(w.toFloat() / s.width, h.toFloat() / s.height)
        scaled(s, maxOf(1, (s.width * k).toInt()), maxOf(1, (s.height * k).toInt()))
    }

    /** The Nano's white alpha-mask icons, drawn without smoothing so the pixel edges stay crisp (integer scale on RG Rotate). */
    fun icon(ctx: Context, name: String): BitmapDrawable {
        val d = BitmapDrawable(ctx.resources, load(ctx, name))
        d.isFilterBitmap = false
        return d
    }
}

fun roundRect(fill: Int, radius: Float, stroke: Int = 0, strokePx: Int = 0): GradientDrawable =
    GradientDrawable().apply { setColor(fill); cornerRadius = radius; if (strokePx > 0) setStroke(strokePx, stroke) }

/** Row background: card normally, accent when focused (D-pad) or pressed (touch), like the Nano's highlighted row. */
fun rowBackground(m: Metrics): StateListDrawable {
    val r = m.px(4).toFloat()
    return StateListDrawable().apply {
        addState(intArrayOf(android.R.attr.state_focused), roundRect(Pal.ACC, r))
        addState(intArrayOf(android.R.attr.state_pressed), roundRect(Pal.ACC, r))
        addState(intArrayOf(-android.R.attr.state_enabled), roundRect(Pal.CARD, r, Pal.LINE, 1))
        addState(intArrayOf(), roundRect(Pal.CARD, r, Pal.LINE, maxOf(1, m.px(0.5f))))
    }
}

fun focusTint(normal: Int): ColorStateList = ColorStateList(
    arrayOf(intArrayOf(android.R.attr.state_focused), intArrayOf(android.R.attr.state_pressed), intArrayOf()),
    intArrayOf(Pal.ONACC, Pal.ONACC, normal),
)

fun text(ctx: Context, s: CharSequence, sizePx: Float, color: Int = Pal.TXT, bold: Boolean = false): TextView = TextView(ctx).apply {
    text = s
    setTextSize(TypedValue.COMPLEX_UNIT_PX, sizePx)
    setTextColor(color)
    typeface = if (bold) Typeface.create("sans-serif-medium", Typeface.BOLD) else Typeface.create("sans-serif", Typeface.NORMAL)
    includeFontPadding = false
    gravity = Gravity.START or Gravity.CENTER_VERTICAL
}

fun icon(ctx: Context, name: String, sizePx: Int, tint: Int? = null, follow: Boolean = false): ImageView = ImageView(ctx).apply {
    setImageDrawable(Art.icon(ctx, name))
    scaleType = ImageView.ScaleType.FIT_CENTER
    if (tint != null) imageTintList = if (follow) focusTint(tint) else ColorStateList.valueOf(tint)
    if (follow) isDuplicateParentStateEnabled = true
    layoutParams = android.widget.LinearLayout.LayoutParams(sizePx, sizePx)
}

fun View.dpadFocusable() { isFocusable = true; isFocusableInTouchMode = false; isClickable = true }
