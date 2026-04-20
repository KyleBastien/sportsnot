package com.sportsnot.app.widget

import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.Context
import android.widget.RemoteViews
import com.sportsnot.app.R
import com.sportsnot.app.widget.models.WidgetSnapshot
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class SportsNotWidgetSmall : AppWidgetProvider() {

    override fun onUpdate(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetIds: IntArray
    ) {
        for (appWidgetId in appWidgetIds) {
            updateWidget(context, appWidgetManager, appWidgetId)
        }
    }

    private fun updateWidget(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetId: Int
    ) {
        CoroutineScope(Dispatchers.IO).launch {
            val snapshot = fetchOrCached(context)
            val views = RemoteViews(context.packageName, R.layout.widget_small)

            if (snapshot != null && snapshot.players.isNotEmpty()) {
                val player = snapshot.players.maxByOrNull { it.fantasyPoints }
                    ?: snapshot.players.first()
                views.setTextViewText(R.id.player_name, player.name)
                views.setTextViewText(R.id.player_team, "${player.teamAbbrev} · ${player.position}")
                views.setTextViewText(
                    R.id.player_points,
                    formatPoints(player.fantasyPoints)
                )
                views.setTextViewText(R.id.league_name, snapshot.league.name)
            } else {
                views.setTextViewText(R.id.player_name, "SportsNot")
                views.setTextViewText(R.id.player_team, "")
                views.setTextViewText(R.id.player_points, "--")
                views.setTextViewText(R.id.league_name, "Tap to configure")
            }

            appWidgetManager.updateAppWidget(appWidgetId, views)
        }
    }
}

internal fun fetchOrCached(context: Context): WidgetSnapshot? {
    val shareCode = WidgetPreferences.getFeaturedShareCode(context) ?: return null
    return try {
        val snapshot = SnapshotAPI.fetchSnapshot(shareCode)
        WidgetPreferences.cacheSnapshot(context, snapshot)
        snapshot
    } catch (_: Exception) {
        WidgetPreferences.getCachedSnapshot(context)
    }
}

internal fun formatPoints(points: Double): String =
    if (points == points.toLong().toDouble()) {
        points.toLong().toString()
    } else {
        "%.1f".format(points)
    }
