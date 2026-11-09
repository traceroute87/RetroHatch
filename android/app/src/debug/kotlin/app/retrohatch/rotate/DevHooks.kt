package app.retrohatch.rotate

import android.content.Context

/**
 * DEBUG BUILDS ONLY (src/debug). Test-fixture seams that do not exist in the release build (src/release has inert versions):
 *  - [devKeys]: public key(s) of the throw-away DEV catalog signing key (assets/dev/dev_keys.txt). A catalog they verify is labelled DEV in the UI.
 *  - [mapUrl]: rewrites the fixture release URLs (https://github.com/retrohatch-fixture/...) to the local HTTPS test server. The catalog still names and
 *    verifies the GitHub URL; only the connection goes elsewhere. The server's certificate is checked against the DEV CA (res/raw/dev_ca.pem), which only the
 *    debug network-security-config trusts.
 */
object DevHooks {
    const val ENABLED = true
    private var map: List<Pair<String, String>> = emptyList()

    fun init(ctx: Context) {
        map = read(ctx, "dev/url_map.txt").mapNotNull { l -> l.split("=", limit = 2).takeIf { it.size == 2 }?.let { it[0].trim() to it[1].trim() } }
    }

    fun devKeys(ctx: Context): List<String> = read(ctx, "dev/dev_keys.txt").map { it.trim().lowercase() }.filter { Regex("[0-9a-f]{64}").matches(it) }

    fun mapUrl(url: String): String = map.firstOrNull { url.startsWith(it.first) }?.let { it.second + url.removePrefix(it.first) } ?: url

    private fun read(ctx: Context, p: String): List<String> =
        try { ctx.assets.open(p).bufferedReader().readLines().filter { it.isNotBlank() && !it.startsWith("#") } } catch (e: java.io.IOException) { emptyList() }
}
