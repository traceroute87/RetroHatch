package app.retrohatch.rotate

import android.content.Context

/** Release build: no DEV keys, no URL rewriting. (The debug build has the fixture seams; see src/debug.) */
object DevHooks {
    const val ENABLED = false
    fun init(ctx: Context) {}
    fun devKeys(ctx: Context): List<String> = emptyList()
    fun mapUrl(url: String): String = url
}
