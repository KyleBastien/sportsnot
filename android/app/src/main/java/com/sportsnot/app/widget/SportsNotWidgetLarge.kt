package com.sportsnot.app.widget

import android.app.AlarmManager
import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.Context
import android.content.Intent
import android.os.SystemClock
import android.view.View
import android.widget.RemoteViews
import com.sportsnot.app.R
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class SportsNotWidgetLarge : AppWidgetProvider() {

    companion object {
        const val ACTION_ROTATE_PAGE = "com.sportsnot.app.ROTATE_PAGE_LARGE"
        const val EXTRA_WIDGET_ID = "widget_id"
        const val PLAYERS_PER_PAGE = 8
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
        val intent = Intent(context, SportsNotWidgetLarge::class.java).apply {
            action = ACTION_ROTATE_PAGE
            putExtra(EXTRA_WIDGET_ID, widgetId)
        }
        val pending = PendingIntent.getBroadcast(
            context, 10000 + widgetId, intent,
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
        val intent = Intent(context, SportsNotWidgetLarge::class.java).apply {
            action = ACTION_ROTATE_PAGE
            putExtra(EXTRA_WIDGET_ID, widgetId)
        }
        val pending = PendingIntent.getBroadcast(
            context, 10000 + widgetId, intent,
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
            val views = RemoteViews(context.packageName, R.layout.widget_large)

            if (snapshot != null) {
                views.setTextViewText(R.id.league_name, snapshot.league.name)

                // Team total
                val myTeamName = WidgetPreferences.getMyTeamName(
                    context,
                    snapshot.league.shareCode
                )
                val teamTotal = if (myTeamName != null) {
                    val pts = snapshot.players
                        .filter { it.ownedByTeamName == myTeamName }
                        .sumOf { it.fantasyPoints }
                    "${formatPoints(pts)} pts"
                } else {
                    val totalPts = snapshot.players.sumOf { it.fantasyPoints }
                    "${formatPoints(totalPts)} pts total"
                }
                views.setTextViewText(R.id.team_total, teamTotal)

                // Games (up to 6)
                val games = snapshot.games.take(6)
                val gameIds = listOf(
                    R.id.game_1, R.id.game_2, R.id.game_3,
                    R.id.game_4, R.id.game_5, R.id.game_6
                )
                for (i in 0..5) {
                    if (i < games.size) {
                        val g = games[i]
                        views.setViewVisibility(gameIds[i], View.VISIBLE)
                        val scoreText = when (g.state) {
                            "LIVE", "CRIT" -> "${g.awayTeamAbbrev} ${g.awayScore} - ${g.homeTeamAbbrev} ${g.homeScore} 🔴"
                            "FINAL", "OFF" -> "${g.awayTeamAbbrev} ${g.awayScore} - ${g.homeTeamAbbrev} ${g.homeScore} F"
                            else -> "${g.awayTeamAbbrev} @ ${g.homeTeamAbbrev}"
                        }
                        views.setTextViewText(gameIds[i], scoreText)
                    } else {
                        views.setViewVisibility(gameIds[i], View.GONE)
                    }
                }

                // Players playing today, paginated (8 per page)
                val playingToday = snapshot.players
                    .filter { it.gameId != null }
                    .sortedByDescending { it.fantasyPoints }

                val totalPages = if (playingToday.isEmpty()) 1
                    else ((playingToday.size + PLAYERS_PER_PAGE - 1) / PLAYERS_PER_PAGE)

                val pageIndex = if (totalPages > 1) {
                    WidgetPreferences.advancePage(context, appWidgetId, totalPages)
                } else {
                    0
                }

                // Page indicator
                if (totalPages > 1) {
                    views.setTextViewText(R.id.page_indicator, "${pageIndex + 1}/$totalPages")
                    views.setViewVisibility(R.id.page_indicator, View.VISIBLE)
                } else {
                    views.setViewVisibility(R.id.page_indicator, View.GONE)
                }

                val start = (pageIndex * PLAYERS_PER_PAGE).coerceAtMost(playingToday.size)
                val end = (start + PLAYERS_PER_PAGE).coerceAtMost(playingToday.size)
                val page = playingToday.subList(start, end)

                val nameIds = listOf(
                    R.id.player_1_name, R.id.player_2_name, R.id.player_3_name, R.id.player_4_name,
                    R.id.player_5_name, R.id.player_6_name, R.id.player_7_name, R.id.player_8_name
                )
                val ptsIds = listOf(
                    R.id.player_1_pts, R.id.player_2_pts, R.id.player_3_pts, R.id.player_4_pts,
                    R.id.player_5_pts, R.id.player_6_pts, R.id.player_7_pts, R.id.player_8_pts
                )
                for (i in 0..7) {
                    if (i < page.size) {
                        val p = page[i]
                        views.setViewVisibility(nameIds[i], View.VISIBLE)
                        views.setViewVisibility(ptsIds[i], View.VISIBLE)
                        views.setTextViewText(nameIds[i], "${p.teamAbbrev} ${p.name}")
                        views.setTextViewText(ptsIds[i], formatPoints(p.fantasyPoints))
                    } else {
                        views.setViewVisibility(nameIds[i], View.GONE)
                        views.setViewVisibility(ptsIds[i], View.GONE)
                    }
                }
            } else {
                views.setTextViewText(R.id.league_name, "SportsNot")
                views.setTextViewText(R.id.team_total, "Tap to configure")
                views.setViewVisibility(R.id.page_indicator, View.GONE)
            }

            appWidgetManager.updateAppWidget(appWidgetId, views)
        }
    }
}
