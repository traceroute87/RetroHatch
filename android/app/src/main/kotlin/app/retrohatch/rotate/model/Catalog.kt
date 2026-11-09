package app.retrohatch.rotate.model

/** Catalog structures: the same fields as catalog/schema/app.schema.json and device.schema.json (the index that tools/trust.py builds). */
data class DeviceProfile(
    val id: String, val name: String, val adapter: String, val packageFormat: String,
    val width: Int?, val height: Int?, val firmware: List<String>, val notes: String? = null,
)

/** APK identity from the signed entry: what the downloaded file must be, besides its SHA-256 (the artifact's own `sha256`). */
data class AndroidPackage(val packageName: String, val versionCode: Long, val signerSha256: List<String>)

data class Artifact(
    val device: String, val firmware: String, val format: String, val available: Boolean, val unavailableReason: String?,
    val version: String?, val url: String?, val sha256: String?, val size: Long?, val level: String, val android: AndroidPackage? = null,
)

data class AppEntry(
    val id: String, val name: String, val description: String, val developer: String, val source: String,
    val website: String?, val license: String, val category: String, val artifacts: List<Artifact>,
)

data class Catalog(val devices: List<DeviceProfile>, val apps: List<AppEntry>, val serial: Long? = null, val generated: String? = null) {
    companion object { val EMPTY = Catalog(emptyList(), emptyList()) }
}

/** One catalog entry as shown on this device: the app plus the single artifact built for it. */
data class Listing(val app: AppEntry, val artifact: Artifact) {
    /** True only for an `available` artifact with full APK identity (package, versionCode, signer, size, URL, hash). Also needs a verified catalog (checked by the UI). */
    val installable: Boolean get() = artifact.available && artifact.android != null && artifact.url != null && artifact.sha256 != null && artifact.size != null
}

object CatalogMapper {
    @Suppress("UNCHECKED_CAST")
    private fun objs(v: Any?): List<Map<String, Any?>> = (v as? List<*>)?.filterIsInstance<Map<String, Any?>>() ?: emptyList()
    private fun s(m: Map<String, Any?>, k: String): String? = m[k] as? String

    private fun android(v: Any?): AndroidPackage? {
        val m = v as? Map<*, *> ?: return null
        val pkg = m["package"] as? String ?: return null
        val vc = m["version_code"] as? Long ?: return null
        val sg = (m["signer_sha256"] as? List<*>)?.filterIsInstance<String>() ?: return null
        return AndroidPackage(pkg, vc, sg)
    }

    /** Lenient mapping for display: a malformed entry is skipped, never crashes the UI. Trust decisions are made by [CatalogPolicy], not here. */
    fun fromDoc(doc: Map<String, Any?>): Catalog {
        val devices = objs(doc["devices"]).mapNotNull { d ->
            val id = s(d, "id") ?: return@mapNotNull null
            val disp = d["display"] as? Map<*, *>
            DeviceProfile(id, s(d, "name") ?: id, s(d, "adapter") ?: "", s(d, "package_format") ?: "",
                (disp?.get("w") as? Long)?.toInt(), (disp?.get("h") as? Long)?.toInt(),
                (d["firmware"] as? List<*>)?.filterIsInstance<String>() ?: emptyList(), s(d, "notes"))
        }
        val apps = objs(doc["apps"]).mapNotNull { a ->
            val id = s(a, "id") ?: return@mapNotNull null
            val arts = objs(a["artifacts"]).mapNotNull { x ->
                Artifact(s(x, "device") ?: return@mapNotNull null, s(x, "firmware") ?: return@mapNotNull null, s(x, "format") ?: return@mapNotNull null,
                    s(x, "status") == "available", s(x, "unavailable_reason"), s(x, "version"), s(x, "url"), s(x, "sha256"), x["size"] as? Long,
                    ((x["compatibility"] as? Map<*, *>)?.get("level") as? String) ?: "untested", android(x["android"]))
            }
            AppEntry(id, s(a, "name") ?: id, s(a, "description") ?: "", s(a, "developer") ?: "", s(a, "source") ?: "", s(a, "website"),
                s(a, "license") ?: "unknown", s(a, "category") ?: "other", arts)
        }
        return Catalog(devices, apps, doc["serial"] as? Long, s(doc, "generated"))
    }
}

/** What RG Rotate is, from catalog/devices/rg-rotate.json (kept in sync by a unit test). */
object Targets {
    val RG_ROTATE = DeviceProfile(
        id = "rg-rotate", name = "RG Rotate", adapter = "android-packageinstaller", packageFormat = "apk",
        width = 720, height = 720, firmware = listOf("android-12"),
        notes = "Android 12 (API 31), Unisoc T618 (arm64), 3 GB RAM, 720x720 touchscreen, physical D-pad and buttons.",
    )
}

/**
 * Device filtering. An entry is offered on a device only when ALL hold: the artifact is built for exactly this device id,
 * its firmware profile is one of the device's, and its package format is the device's (`apk`). An Nano `.opk` artifact can
 * therefore never appear on Android, even if a catalog entry is malformed or mislabelled.
 */
object DeviceFilter {
    fun forDevice(cat: Catalog, target: DeviceProfile): List<Listing> =
        cat.apps.mapNotNull { app ->
            val art = app.artifacts.firstOrNull { matches(it, target) } ?: return@mapNotNull null
            Listing(app, art)
        }.sortedBy { it.app.name.lowercase() }

    fun matches(a: Artifact, target: DeviceProfile): Boolean =
        a.device == target.id && a.firmware in target.firmware && a.format == target.packageFormat && a.format == "apk"

    /** Entries in the catalog that have no artifact for this device (other handhelds). Shown in Catalog Status, never in the app list. */
    fun hiddenCount(cat: Catalog, target: DeviceProfile): Int = cat.apps.size - forDevice(cat, target).size
}

sealed class CatalogSource {
    /** Signature, rollback state and every publish gate verified against a pinned key. */
    data class Signed(val serial: Long, val keyId: String, val generated: String?, val dev: Boolean = false, val cached: Boolean = false) : CatalogSource()

    /** Offline sample data. Not signed, not approved, not installable. The UI must label it as such everywhere it shows apps. */
    data class Preview(val reason: String) : CatalogSource()
}

class LoadedCatalog(val source: CatalogSource, val catalog: Catalog, val newState: TrustState? = null)

object CatalogLoader {
    private const val NO_SIGNED = "No signed Android catalog is published yet."

    /**
     * Signed catalog if one is present AND verifies; otherwise the bundled preview sample. A catalog that fails verification is
     * discarded entirely (its content is never shown); the reason is kept for Catalog Status.
     */
    fun load(
        signedIndex: ByteArray?, signedSig: ByteArray?, previewIndex: ByteArray?,
        trusted: List<String> = Trust.PRODUCTION_KEYS, state: TrustState? = null, devKeys: List<String> = emptyList(),
    ): LoadedCatalog {
        var why = NO_SIGNED
        if (signedIndex != null) {
            try {
                // devKeys (DEBUG builds only) are test-fixture keys; a catalog they verify is labelled DEV everywhere and is never "production"
                val v = Trust.verify(signedIndex, signedSig ?: ByteArray(0), trusted + devKeys, state)
                val dev = devKeys.any { Trust.keyId(Trust.unhex(it)) == v.keyId } && trusted.none { Trust.keyId(Trust.unhex(it)) == v.keyId }
                return LoadedCatalog(CatalogSource.Signed(v.state.serial, v.keyId, v.doc["generated"] as? String, dev), CatalogMapper.fromDoc(v.doc), v.state)
            } catch (e: TrustException) {
                why = "Signed catalog rejected: ${e.message}"
            }
        }
        val cat = try { previewIndex?.let { CatalogMapper.fromDoc(StrictJson.parseObject(it)) } } catch (e: TrustException) { null } ?: Catalog.EMPTY
        return LoadedCatalog(CatalogSource.Preview(why), cat)
    }
}
