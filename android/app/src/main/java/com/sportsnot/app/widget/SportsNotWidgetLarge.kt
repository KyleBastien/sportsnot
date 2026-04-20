package com.sportsnot.app.widget

import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.Context
import android.view.View
import android.widget.RemoteViews
import com.sportsnot.app.R
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class SportsNotWidgetLarge : AppWidgetProvider() {

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
            val views = RemoteViews(context.packageName, R.layout.widget_large)

            if (snapshot != null) {
                views.setTextViewText(R.id.league_name, snapshot.league.name)

                // Team total for the user's team
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
                val gameIds = listOf(R.id.game_1, R.id.game_2, R.id.game_3, R.id.game_4, R.id.game_5, R.id.game_6)
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

                // Players (up to 8)
                val players = snapshot.players
                    .sortedByDescending { it.fantasyPoints }
                    .take(8)
                val nameIds = listOf(
                    R.id.player_1_name, R.id.player_2_name, R.id.player_3_name, R.id.player_4_name,
                    R.id.player_5_name, R.id.player_6_name, R.id.player_7_name, R.id.player_8_name
                )
                val ptsIds = listOf(
                    R.id.player_1_pts, R.id.player_2_pts, R.id.player_3_pts, R.id.player_4_pts,
                    R.id.player_5_pts, R.id.player_6_pts, R.id.player_7_pts, R.id.player_8_pts
                )
                for (i in 0..7) {
                    if (i < players.size) {
                        val p = players[i]
                        views.setViewVisibility(nameIds[i], View.VISIBLE)
                        views.setViewVisibility(ptsIds[i], View.VISIBLE)
                        views.setTextViewText(nameIds[i], "${p.name} (${p.teamAbbrev})")
                        views.setTextViewText(ptsIds[i], formatPoints(p.fantasyPoints))
                    } else {
                        views.setViewVisibility(nameIds[i], View.GONE)
                        views.setViewVisibility(ptsIds[i], View.GONE)
                    }
                }
            } else {
                views.setTextViewText(R.id.league_name, "SportsNot")
                views.setTextViewText(R.id.team_total, "Tap to configure")
            }

            appWidgetManager.updateAppWidget(appWidgetId, views)
        }
    }
}
