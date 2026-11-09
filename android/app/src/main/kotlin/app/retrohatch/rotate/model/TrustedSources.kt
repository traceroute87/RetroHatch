package app.retrohatch.rotate.model

/**
 * Where a catalog APK may come from. The signed catalog still pins every artifact's SHA-256, size, package, versionCode and signing certificate, and the app re-checks all of them on the
 * downloaded file, so a source never replaces integrity checks: it only decides which hosts a signed entry may point at. Android-only; the RG Nano verifier is not involved.
 *
 * Accepted sources (DEV-signed catalogs; a production policy needs a human-approved extension of the approval record, see android/README.md):
 *  - github    a release download of the entry's OWN GitHub repository (the original rule)
 *  - gitlab    a release / upload URL inside the entry's OWN gitlab.com project
 *  - codeberg  a release download of the entry's OWN codeberg.org repository
 *  - fdroid    https://f-droid.org/repo/<package>_<versionCode>.apk  (the file name must be the entry's own package and versionCode)
 *  - izzy      https://apt.izzysoft.de/fdroid/repo/<package>_<versionCode>.apk
 *  - official  a URL under a prefix pinned IN THIS CODE for one specific package (official developer download servers); never data from a catalog
 * Anything else (mirrors, shorteners, other hosts) is refused. Redirects may only stay on the source's own hosts ([redirectHosts]).
 */
object TrustedSources {
    /** package -> the one URL prefix its official developer server may serve it from. Reviewed by hand; add a line only for an official, https, stable download location. */
    private val OFFICIAL = mapOf(
        "com.retroarch.aarch64" to "https://buildbot.libretro.com/stable/",
        "org.ppsspp.ppsspp" to "https://www.ppsspp.org/files/",
    )

    private val GITHUB_HOSTS = setOf("github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com")

    /** @return the source kind that accepts this artifact, or null. [source] is the entry's `source` URL. */
    fun kind(source: String?, url: String?, pkg: String?, versionCode: Long?): String? {
        val u = url ?: return null
        if (!u.startsWith("https://") || u.any { it <= ' ' || it == '\\' || it.code >= 0x7f } || "@" in u.substringAfter("://").substringBefore("/")) return null
        if (CatalogPolicy.releaseOk(source, u)) return "github"
        val src = (source ?: "").trimEnd('/').removeSuffix(".git")
        val low = u.lowercase()
        Regex("https://gitlab\\.com/([^\\s]+/[^\\s/]+)").matchEntire(src)?.let { m ->
            val base = "https://gitlab.com/${m.groupValues[1]}".lowercase()
            if (low.startsWith("$base/-/releases/") && "/downloads/" in low || low.startsWith("$base/uploads/")) return "gitlab"
        }
        Regex("https://codeberg\\.org/([^/\\s]+)/([^/\\s]+)").matchEntire(src)?.let { m ->
            val base = "https://codeberg.org/${m.groupValues[1]}/${m.groupValues[2]}".lowercase()
            if (Regex(Regex.escape(base) + "/releases/download/[^/\\s]+/[^/\\s]+").matches(low)) return "codeberg"
        }
        if (pkg != null && versionCode != null) {
            if (u == "https://f-droid.org/repo/${pkg}_$versionCode.apk") return "fdroid"
            if (u == "https://apt.izzysoft.de/fdroid/repo/${pkg}_$versionCode.apk") return "izzy"
            val pre = OFFICIAL[pkg]
            if (pre != null && u.startsWith(pre) && u.length > pre.length && ".." !in u && "?" !in u && "#" !in u) return "official"
        }
        return null
    }

    /** The hosts a download of this URL may be redirected to (null = no restriction: not a catalog source, e.g. the local test server). */
    fun redirectHosts(url: String?): Set<String>? {
        val u = url?.lowercase() ?: return null
        val host = Regex("https://([^/]+)/").find(u)?.groupValues?.get(1) ?: return null
        return when {
            host == "github.com" -> GITHUB_HOSTS
            host == "gitlab.com" || host == "codeberg.org" || host == "f-droid.org" || host == "apt.izzysoft.de" -> setOf(host)
            OFFICIAL.values.any { u.startsWith(it) } -> setOf(host)
            else -> setOf(host)
        }
    }

    val kinds = listOf("github", "gitlab", "codeberg", "fdroid", "izzy", "official")
}
