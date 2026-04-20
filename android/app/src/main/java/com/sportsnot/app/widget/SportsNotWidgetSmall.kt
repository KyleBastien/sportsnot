package com.sportsnot.app.widget

import android.app.AlarmManager
import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.Context
import android.content.Intent
import android.os.SystemClock
import android.widget.RemoteViews
import com.sportsnot.app.R
import com.sportsnot.app.widget.models.WidgetSnapshot
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class SportsNotWidgetSmall : AppWidgetProvider() {

    companion object {
        const val ACTION_ROTATE_PAGE = "com.sportsnot.app.ROTATE_PAGE_SMALL"
        const val EXTRA_WIDGET_ID = "widget_id"
        const val PLAYERS_PER_PAGE = 1
        private const val PAGE_INTERVAL_MS = 30_000L
    }

    override fun onUpdate(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetIds: IntArray
    ) {
        for (appWidgetId in appWidgetIds) {
            updateWidget(context, appWidgetManager, appWidgetId)
            schedulePageRotation(context, appWidgetId)
        }
    }

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        if (intent.action == ACTION_ROTATE_PAGE) {
            val widgetId = intent.getIntExtra(EXTRA_WIDGET_ID, -1)
            if (widgetId != -1) {
                val manager = AppWidgetManager.getInstance(context)
                updateWidget(context, manager, widgetId)
                schedulePageRotation(context, widgetId)
            }
        }
    }

    override fun onDeleted(context: Context, appWidgetIds: IntArray) {
        for (id in appWidgetIds) {
            cancelPageRotation(context, id)
            WidgetPreferences.clearPageIndex(context, id)
        }
    }

    private fun schedulePageRotation(context: Context, widgetId: Int) {
        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val intent = Intent(context, SportsNotWidgetSmall::class.java).apply {
            action = ACTION_ROTATE_PAGE
            putExtra(EXTRA_WIDGET_ID, widgetId)
        }
        val pending = PendingIntent.getBroadcast(
            context, 20000 + widgetId, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        alarmManager.set(
            AlarmManager.ELAPSED_REALTIME,
            SystemClock.elapsedRealtime() + PAGE_INTERVAL_MS,
            pending
        )
    }

    private fun cancelPageRotation(context: Context, widgetId: Int) {
        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val intent = Intent(context, SportsNotWidgetSmall::class.java).apply {
            action = ACTION_ROTATE_PAGE
            putExtra(EXTRA_WIDGET_ID, widgetId)
        }
        val pending = PendingIntent.getBroadcast(
            context, 20000 + widgetId, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        alarmManager.cancel(pending)
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
                val playingToday = snapshot.players
                    .filter { it.gameId != null }
                    .sortedByDescending { it.fantasyPoints }

                val totalPages = playingToday.size.coerceAtLeast(1)
                val pageIndex = if (totalPages > 1) {
                    WidgetPreferences.advancePage(context, appWidgetId, totalPages)
                } else {
                    0
                }

                val player = if (playingToday.isNotEmpty()) {
                    playingToday[pageIndex.coerceAtMost(playingToday.size - 1)]
                } else {
                    snapshot.players.maxByOrNull { it.fantasyPoints }
                        ?: snapshot.players.first()
                }

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
