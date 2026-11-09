package app.retrohatch.rotate.model

/** What the Discover list shows: search text, one category, a sort and a filter. Pure data, no Android classes, unit-tested on the JVM. */
enum class Sort(val label: String) { NAME("A to Z"), UPDATED("Recently updated"), ADDED("Newly added") }

enum class Filter(val label: String) {
    ALL("All apps"), INSTALLED("Installed"), NOT_INSTALLED("Not installed"), UPDATES("Updates available"), VERIFIED("Verified only"),
}

/** [group] null = every category. */
data class DiscoverQuery(val text: String = "", val group: String? = null, val sort: Sort = Sort.NAME, val filter: Filter = Filter.ALL) {
    val active: Boolean get() = text.isNotBlank() || group != null || filter != Filter.ALL
}

/** How an entry stands on this device, as far as the filter cares. */
enum class Presence { NOT_INSTALLED, INSTALLED, UPDATE }

object Groups {
    /** Fixed display order, shared with discovery/categories.py. Only groups that hold entries are ever shown. */
    val ORDER = listOf("games" to "Games", "emulators" to "Emulators", "ports" to "Ports", "utilities" to "Utilities", "media" to "Media", "themes-launchers" to "Themes & Launchers")
    val LABEL = ORDER.toMap()
    fun label(id: String?) = LABEL[id] ?: "Other"

    /** The entry's own group; for a catalog without one, a stable guess from the signed `category` (the RG Nano's vocabulary). */
    fun of(a: AppEntry): String = a.group ?: when (a.category) { "launcher", "theme" -> "themes-launchers"; "port" -> "ports"; else -> "utilities" }
}

object Discover {
    /** Categories that contain at least one of [listings], in display order, with their counts. */
    fun groups(listings: List<Listing>): List<Triple<String, String, Int>> {
        val n = listings.groupingBy { Groups.of(it.app) }.eachCount()
        return Groups.ORDER.filter { n.containsKey(it.first) }.map { Triple(it.first, it.second, n.getValue(it.first)) }
    }

    /** Every word of the query must appear in the name, description, developer or a tag (case-insensitive). */
    fun matches(l: Listing, text: String): Boolean {
        val words = text.lowercase().split(Regex("\\s+")).filter { it.isNotEmpty() }
        if (words.isEmpty()) return true
        val hay = (listOf(l.app.name, l.app.description, l.app.developer) + l.app.tags).joinToString(" ").lowercase()
        return words.all { hay.contains(it) }
    }

    fun apply(listings: List<Listing>, q: DiscoverQuery, presence: (Listing) -> Presence): List<Listing> {
        val kept = listings.filter { l ->
            (q.group == null || Groups.of(l.app) == q.group) && matches(l, q.text) && when (q.filter) {
                Filter.ALL -> true
                Filter.INSTALLED -> presence(l) != Presence.NOT_INSTALLED
                Filter.NOT_INSTALLED -> presence(l) == Presence.NOT_INSTALLED
                Filter.UPDATES -> presence(l) == Presence.UPDATE
                Filter.VERIFIED -> l.artifact.level == "verified"
            }
        }
        val byName = compareBy<Listing> { it.app.name.lowercase() }
        return when (q.sort) {
            Sort.NAME -> kept.sortedWith(byName)
            Sort.UPDATED -> kept.sortedWith(compareByDescending<Listing> { it.app.released ?: "" }.then(byName))     // no date: last
            Sort.ADDED -> kept.sortedWith(compareByDescending<Listing> { it.app.added ?: "" }.then(byName))
        }
    }

    /** A one-line description of what is active, for the line under the toolbar: "Emulators - Updates available - 'gb'". */
    fun summary(q: DiscoverQuery, shown: Int, total: Int): String {
        val bits = listOfNotNull(q.group?.let { Groups.label(it) }, q.filter.takeIf { it != Filter.ALL }?.label, q.text.takeIf { it.isNotBlank() }?.let { "\"${it.trim()}\"" })
        return (if (bits.isEmpty()) "$total apps" else "$shown of $total  -  " + bits.joinToString("  -  ")) + "  -  " + q.sort.label
    }
}
