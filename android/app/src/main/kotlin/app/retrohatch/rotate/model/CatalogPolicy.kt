package app.retrohatch.rotate.model

/**
 * Publish gates for a signed index: a port of tools/trust.py `check_index` (+ the cross-file rules of tools/validate.py) for the
 * parts the Android client needs. Same limits, same patterns, same approval/revocation matching. [check] returns the first
 * error or null.
 *
 * Differences from the Nano verifier, on purpose:
 *  - `install.dest_name` rules (".opk", Nano protected names) apply to `opk` artifacts only; they are the Nano engine's business.
 *  - `apk` artifacts have no extra policy fields yet (package name, versionCode, signer-certificate SHA-256). tools/trust.py
 *    cannot build such an index today, so no signed Android catalog can exist until M2 adds them on both sides.
 */
object CatalogPolicy {
    private const val FORMAT = 1L
    private const val MAX_TOKENS = 8192
    private const val MAX_DEPTH = 12
    private const val MAX_ITEMS = 256
    private const val MAX_DEVICES = 16
    private val TOP = setOf("format", "serial", "generated", "devices", "apps", "approvals", "revoked")
    private val SHA = Regex("[0-9a-f]{64}")
    private val DATE = Regex("\\d{4}-\\d{2}-\\d{2}")
    private val ID = Regex("[a-z0-9][a-z0-9-]{0,63}")
    private val URLISH = Regex("https://[\\x21\\x23-\\x5b\\x5d-\\x7e]+")
    private val DEST = Regex("[A-Za-z0-9._-]{1,64}")
    private val APPROVAL_KEYS = setOf("app", "device", "firmware", "sha256", "size", "release", "approved_by", "date")
    private val DEVICE_KEYS = setOf("schema", "id", "name", "adapter", "package_format", "display", "firmware", "notes")
    private val APP_KEYS = setOf("schema", "id", "name", "description", "developer", "website", "source", "license", "category", "artifacts", "long_description", "features", "group", "tags", "released", "added")
    private val ART_KEYS = setOf("device", "firmware", "format", "status", "unavailable_reason", "version", "url", "sha256", "size", "install", "android", "compatibility")
    private val PKG = Regex("[A-Za-z][A-Za-z0-9_]*(\\.[A-Za-z][A-Za-z0-9_]*)+")
    private val GROUPS = setOf("games", "emulators", "ports", "utilities", "media", "themes-launchers")
    private val TAG = Regex("[a-z0-9][a-z0-9+-]{1,23}")
    private val CATEGORIES = setOf("application", "utility", "launcher", "theme", "port", "other")

    /** (tokens, max depth) counted the way the native parser counts them. */
    fun shape(v: Any?, depth: Int = 0): Pair<Int, Int> = when (v) {
        is Map<*, *> -> { var t = 1; var d = depth; for (x in v.values) { val (a, b) = shape(x, depth + 1); t += 1 + a; d = maxOf(d, b) }; t to d }
        is List<*> -> { var t = 1; var d = depth; for (x in v) { val (a, b) = shape(x, depth + 1); t += a; d = maxOf(d, b) }; t to d }
        else -> 1 to depth
    }

    /** The artifact URL must be a release download of the entry's own GitHub source repo. */
    fun releaseOk(source: String?, url: String?, release: String? = null): Boolean {
        val m = Regex("https://github\\.com/([^/\\s]+)/([^/\\s]+?)(?:\\.git)?/?").matchEntire(source ?: "") ?: return false
        val base = "https://github.com/${m.groupValues[1]}/${m.groupValues[2]}".lowercase()
        val u = Regex(Regex.escape(base) + "/releases/download/([^/\\s]+)/[^/\\s]+").matchEntire((url ?: "").lowercase()) ?: return false
        return release == null || release.lowercase() == "$base/releases/tag/${u.groupValues[1]}"
    }

    private fun isInt(v: Any?) = v is Long

    /** artifact.android: {package, version_code 1..2^31-1, signer_sha256: 1..8 unique sha256}. Mirrors tools/trust.py and core/rh_catalog.c. */
    private fun androidProblem(w: String, v: Any?): String? {
        val a = v as? Map<*, *> ?: return "$w: apk artifact needs android (package, version_code, signer_sha256)"
        if (a.keys != setOf("package", "version_code", "signer_sha256")) return "$w: android has wrong fields"
        val pkg = a["package"] as? String
        if (pkg == null || pkg.length > 255 || !PKG.matches(pkg)) return "$w: android package is not an application id"
        val vc = a["version_code"]
        if (vc !is Long || vc < 1 || vc > 2147483647L) return "$w: android version_code out of range"
        val sg = a["signer_sha256"] as? List<*>
        if (sg == null || sg.isEmpty() || sg.size > 8 || sg.any { it !is String || !SHA.matches(it) } || sg.toSet().size != sg.size) return "$w: android signer_sha256 must be 1-8 unique sha256 values"
        return null
    }

    @Suppress("UNCHECKED_CAST")
    private fun objs(v: Any?): List<Map<String, Any?>>? = (v as? List<*>)?.let { l -> if (l.all { it is Map<*, *> }) l as List<Map<String, Any?>> else null }

    /**
     * [allowExperimental]: set ONLY for a catalog signed by a DEV fixture key (debug builds). Such a catalog may carry artifacts with compatibility level
     * "experimental": no human approval and no test evidence are required for them, but everything else still is (https GitHub release URL of the entry's own
     * source repo, sha256, size, android identity, known licence, not revoked). Level "verified" keeps ALL the production gates, also in a DEV catalog.
     * Production keys never get this: tools/trust.py and every release build reject an "experimental" artifact.
     */
    fun check(doc: Map<String, Any?>, allowExperimental: Boolean = false): String? {
        val (tokens, depth) = shape(doc)
        if (tokens > MAX_TOKENS || depth > MAX_DEPTH) return "index too complex for the device verifier ($tokens tokens, depth $depth)"
        val extra = doc.keys - TOP - "expires"
        if (extra.isNotEmpty() || (TOP - doc.keys).isNotEmpty()) return "index keys wrong: missing ${(TOP - doc.keys).sorted()}, unexpected ${extra.sorted()}"
        if (doc["format"] != FORMAT) return "unsupported format ${doc["format"]}"
        val serial = doc["serial"]
        if (!isInt(serial) || (serial as Long) < 1) return "serial must be an integer >= 1"
        for (f in listOf("generated", "expires")) if (f in doc && !(doc[f] is String && DATE.matches(doc[f] as String))) return "$f must be YYYY-MM-DD"
        val devices = objs(doc["devices"]); val apps = objs(doc["apps"]); val approvals = objs(doc["approvals"]); val revokedL = objs(doc["revoked"])
        if (devices == null || apps == null || approvals == null || revokedL == null) return "devices/apps/approvals/revoked must be lists of objects"
        if (devices.size > MAX_DEVICES || approvals.size > MAX_ITEMS) return "too many devices or approvals for the device verifier"
        for ((kind, list) in listOf("device" to devices, "app" to apps)) {
            val ids = list.map { it["id"] }
            if (ids.any { it !is String || !ID.matches(it) }) return "$kind: bad id"
            if (ids.toSet().size != ids.size) return "duplicate $kind id"
        }

        // ---- devices (device.schema.json) ----
        val dev = HashMap<String, Map<String, Any?>>()
        for (d in devices) {
            val id = d["id"] as String
            if (!DEVICE_KEYS.containsAll(d.keys) || !d.keys.containsAll(listOf("schema", "id", "name", "adapter", "package_format", "firmware"))) return "device $id: wrong fields"
            if (d["schema"] != 1L || d["name"] !is String || (d["name"] as String).isEmpty()) return "device $id: bad schema or name"
            if (d["adapter"] !in setOf("opk-funkeyos", "android-packageinstaller") || d["package_format"] !in setOf("opk", "apk")) return "device $id: bad adapter or package_format"
            val fw = d["firmware"] as? List<*>
            if (fw == null || fw.isEmpty() || fw.any { it !is String || !ID.matches(it) }) return "device $id: bad firmware ids"
            dev[id] = d
        }

        // ---- approvals / revoked ----
        val appr = HashMap<List<Any?>, Map<String, Any?>>()
        for (a in approvals) {
            if (a.keys != APPROVAL_KEYS) return "approval ${a["app"]}: wrong fields"
            val strs = listOf("app", "device", "firmware", "sha256", "release", "approved_by", "date")
            val ok = strs.all { a[it] is String } && ID.matches(a["app"] as String) && ID.matches(a["device"] as String) && ID.matches(a["firmware"] as String) &&
                SHA.matches(a["sha256"] as String) && DATE.matches(a["date"] as String) && (a["approved_by"] as String).isNotEmpty() &&
                URLISH.matches(a["release"] as String) && isInt(a["size"]) && (a["size"] as Long) >= 1
            if (!ok) return "approval ${a["app"]}: bad field value"
            val k = listOf(a["app"], a["device"], a["firmware"], a["sha256"])
            if (k in appr) return "duplicate approval $k"
            appr[k] = a
        }
        val revoked = HashSet<Pair<Any?, Any?>>()
        for (r in revokedL) {
            if (r.keys != setOf("app", "sha256", "reason") || r.values.any { it !is String } || !ID.matches(r["app"] as String) ||
                !SHA.matches(r["sha256"] as String) || (r["reason"] as String).isEmpty()) return "revoked entry: wrong fields"
            revoked.add(r["app"] to r["sha256"])
        }

        // ---- apps (app.schema.json + validate.py cross rules + publish gates) ----
        val used = HashSet<List<Any?>>()
        var artifacts = 0
        for (app in apps) {
            val aid = app["id"] as String
            if (!APP_KEYS.containsAll(app.keys) || !app.keys.containsAll(listOf("schema", "id", "name", "description", "developer", "source", "license", "category", "artifacts"))) return "$aid: wrong fields"
            if (app["schema"] != 1L || listOf("name", "description", "developer", "source", "license").any { app[it] !is String || (app[it] as String).isEmpty() }) return "$aid: bad field value"
            if (app["category"] !in CATEGORIES) return "$aid: bad category"
            app["long_description"]?.let { if (it !is String || it.isEmpty() || it.length > 2000) return "$aid: bad long_description" }
            app["group"]?.let { if (it !in GROUPS) return "$aid: bad group" }
            app["tags"]?.let { t -> if (t !is List<*> || t.size > 8 || t.any { it !is String || !TAG.matches(it) }) return "$aid: bad tags" }
            for (k in listOf("released", "added")) app[k]?.let { if (it !is String || !DATE.matches(it)) return "$aid: bad $k" }
            app["features"]?.let { f -> if (f !is List<*> || f.isEmpty() || f.size > 8 || f.any { it !is String || it.isEmpty() || it.length > 120 }) return "$aid: bad features" }
            if (!URLISH.matches(app["source"] as String) || (app["website"]?.let { it !is String || !URLISH.matches(it) } == true)) return "$aid: bad urls"
            val arts = objs(app["artifacts"]) ?: return "$aid: artifacts must be a list of objects"
            if (arts.isEmpty()) return "$aid: published app has no artifacts"
            artifacts += arts.size
            for (art in arts) {
                val w = "$aid/${art["device"]}"
                if (!ART_KEYS.containsAll(art.keys) || !art.keys.containsAll(listOf("device", "firmware", "format", "status", "compatibility"))) return "$w: wrong artifact fields"
                val dv = dev[art["device"]] ?: return "$w: unknown device '${art["device"]}'"
                if (art["firmware"] !in (dv["firmware"] as List<*>)) return "$w: firmware '${art["firmware"]}' not on device"
                if (art["format"] != dv["package_format"]) return "$w: format != device package_format"
                if (art["status"] != "available") return "$w: only available artifacts may be published"
                for (f in listOf("version", "url", "sha256", "size")) if (f !in art) return "$w: available artifact missing '$f'"
                if (app["license"] == "unknown") return "$w: available artifact with unknown license"
                val sha = art["sha256"]; val url = art["url"]
                if (sha !is String || !SHA.matches(sha) || url !is String || !URLISH.matches(url) || !isInt(art["size"]) || (art["size"] as Long) < 1) return "$w: artifact fields"
                val comp = art["compatibility"] as? Map<*, *> ?: return "$w: bad compatibility"
                val experimental = allowExperimental && comp["level"] == "experimental"
                if (comp["level"] != "verified" && !experimental) return "$w: compatibility level '${comp["level"]}' is not publishable"
                val ev = (comp["evidence"] as? List<*>) ?: emptyList<Any?>()
                var matched = false
                for (e in ev) {
                    val m = e as? Map<*, *> ?: return "$w: bad evidence"
                    if (m["sha256"] !is String || !SHA.matches(m["sha256"] as String) || m["date"] !is String || !DATE.matches(m["date"] as String)) return "$w: evidence"
                    if (m["sha256"] == sha) matched = true
                }
                if (!matched && !experimental) return "$w: verified needs evidence whose sha256 matches the artifact"
                if (art["format"] == "opk") {
                    if ("android" in art) return "$w: android is only for apk artifacts"
                    val dn = (art["install"] as? Map<*, *>)?.get("dest_name") as? String ?: return "$w: artifact has no install.dest_name"
                    if (!DEST.matches(dn) || !dn.lowercase().endsWith(".opk")) return "$w: destination '$dn' is not a plain .opk name"
                } else {
                    if ("install" in art) return "$w: apk artifact must not have install"
                    androidProblem(w, art["android"])?.let { return it }
                }
                if (!releaseOk(app["source"] as String, url)) return "$w: url is not a release download of the source repo"
                val key = listOf(aid, art["device"], art["firmware"], sha)
                if (!experimental) {
                    val a = appr[key] ?: return "$w: no human approval for this exact sha256"
                    used.add(key)
                    if (a["size"] != art["size"] || !releaseOk(app["source"] as String, url, a["release"] as String)) return "$w: approval does not match artifact size/release"
                }
                if ((aid to sha) in revoked) return "$w: artifact is revoked"
            }
        }
        if (artifacts > MAX_ITEMS) return "too many artifacts for the device verifier"
        (appr.keys - used).firstOrNull()?.let { return "approval $it matches no published artifact" }
        return null
    }
}
