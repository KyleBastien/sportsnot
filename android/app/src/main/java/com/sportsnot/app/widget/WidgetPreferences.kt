package com.sportsnot.app.widget

import android.content.Context
import android.content.SharedPreferences
import com.sportsnot.app.widget.models.WidgetSnapshot
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

object WidgetPreferences {
    private const val PREFS_NAME = "com.sportsnot.widget"
    private const val KEY_FEATURED_SHARE_CODE = "featuredShareCode"
    private const val KEY_ALL_SHARE_CODES = "allShareCodes"
    private const val KEY_TEAM_NAMES = "myTeamNamesByShareCode"
    private const val KEY_CACHED_SNAPSHOT = "cachedSnapshot"
    private const val KEY_CACHED_SNAPSHOT_TIME = "cachedSnapshotTime"

    private val json = Json { ignoreUnknownKeys = true }

    private fun prefs(context: Context): SharedPreferences =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    fun getFeaturedShareCode(context: Context): String? =
        prefs(context).getString(KEY_FEATURED_SHARE_CODE, null)

    fun setFeaturedShareCode(context: Context, shareCode: String) {
        prefs(context).edit().putString(KEY_FEATURED_SHARE_CODE, shareCode).apply()
        rememberShareCode(context, shareCode)
    }

    fun getAllShareCodes(context: Context): List<String> {
        val raw = prefs(context).getString(KEY_ALL_SHARE_CODES, null) ?: return emptyList()
        return raw.split(",").filter { it.isNotBlank() }
    }

    fun rememberShareCode(context: Context, shareCode: String) {
        val existing = getAllShareCodes(context).toMutableSet()
        existing.add(shareCode)
        prefs(context).edit()
            .putString(KEY_ALL_SHARE_CODES, existing.joinToString(","))
            .apply()
    }

    fun getMyTeamName(context: Context, shareCode: String): String? {
        val raw = prefs(context).getString(KEY_TEAM_NAMES, null) ?: return null
        val map = raw.split(";").associate {
            val parts = it.split("=", limit = 2)
            if (parts.size == 2) parts[0] to parts[1] else "" to ""
        }
        return map[shareCode]
    }

    fun setMyTeamName(context: Context, teamName: String?, shareCode: String) {
        val raw = prefs(context).getString(KEY_TEAM_NAMES, null) ?: ""
        val map = raw.split(";")
            .filter { it.contains("=") }
            .associate {
                val parts = it.split("=", limit = 2)
                parts[0] to parts[1]
            }.toMutableMap()

        if (teamName != null) {
            map[shareCode] = teamName
        } else {
            map.remove(shareCode)
        }

        prefs(context).edit()
            .putString(KEY_TEAM_NAMES, map.entries.joinToString(";") { "${it.key}=${it.value}" })
            .apply()
    }

    fun cacheSnapshot(context: Context, snapshot: WidgetSnapshot) {
        val encoded = json.encodeToString(snapshot)
        prefs(context).edit()
            .putString(KEY_CACHED_SNAPSHOT, encoded)
            .putLong(KEY_CACHED_SNAPSHOT_TIME, System.currentTimeMillis())
            .apply()
    }

    fun getCachedSnapshot(context: Context): WidgetSnapshot? {
        val raw = prefs(context).getString(KEY_CACHED_SNAPSHOT, null) ?: return null
        return try {
            json.decodeFromString<WidgetSnapshot>(raw)
        } catch (_: Exception) {
            null
        }
    }

    /**
     * Returns the cached snapshot only if it was stored within `maxAgeMs`
     * milliseconds. Used as a stale-fallback guard so the widget doesn't
     * render yesterday's slate forever when the network has been failing.
     */
    fun getCachedSnapshot(context: Context, maxAgeMs: Long): WidgetSnapshot? {
        val storedAt = prefs(context).getLong(KEY_CACHED_SNAPSHOT_TIME, 0L)
        if (storedAt == 0L) return null
        if (System.currentTimeMillis() - storedAt > maxAgeMs) return null
        return getCachedSnapshot(context)
    }

    // Page rotation for widget player lists (mirrors iOS 30s timeline entries)
    fun getPageIndex(context: Context, widgetId: Int): Int =
        prefs(context).getInt("pageIndex_$widgetId", 0)

    fun advancePage(context: Context, widgetId: Int, totalPages: Int): Int {
        val next = if (totalPages <= 1) 0 else (getPageIndex(context, widgetId) + 1) % totalPages
        prefs(context).edit().putInt("pageIndex_$widgetId", next).apply()
        return next
    }

    fun clearPageIndex(context: Context, widgetId: Int) {
        prefs(context).edit().remove("pageIndex_$widgetId").apply()
    }
}
