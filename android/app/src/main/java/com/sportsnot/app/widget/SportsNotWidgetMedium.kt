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

class SportsNotWidgetMedium : AppWidgetProvider() {

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
            val views = RemoteViews(context.packageName, R.layout.widget_medium)

            if (snapshot != null) {
                views.setTextViewText(R.id.league_name, snapshot.league.name)

                // Top 3 players by fantasy points
                val topPlayers = snapshot.players
                    .sortedByDescending { it.fantasyPoints }
                    .take(3)

                val playerNameIds = listOf(R.id.player_1_name, R.id.player_2_name, R.id.player_3_name)
                val playerPtsIds = listOf(R.id.player_1_points, R.id.player_2_points, R.id.player_3_points)
                val playerRowIds = listOf(R.id.player_row_1, R.id.player_row_2, R.id.player_row_3)

                for (i in 0..2) {
                    if (i < topPlayers.size) {
                        val p = topPlayers[i]
                        views.setViewVisibility(playerRowIds[i], View.VISIBLE)
                        views.setTextViewText(playerNameIds[i], "${p.name} (${p.teamAbbrev})")
                        views.setTextViewText(playerPtsIds[i], formatPoints(p.fantasyPoints))
                    } else {
                        views.setViewVisibility(playerRowIds[i], View.GONE)
                    }
                }

                // Team total for the user's team
                val myTeamName = WidgetPreferences.getMyTeamName(
                    context,
                    snapshot.league.shareCode
                )
                val teamTotal = if (myTeamName != null) {
                    val pts = snapshot.players
                        .filter { it.ownedByTeamName == myTeamName }
                        .sumOf { it.fantasyPoints }
                    "$myTeamName: ${formatPoints(pts)} pts"
                } else {
                    ""
                }
                views.setTextViewText(R.id.team_total, teamTotal)

                // Today's games (up to 4)
                val games = snapshot.games.take(4)
                val matchupIds = listOf(R.id.game_1_matchup, R.id.game_2_matchup, R.id.game_3_matchup, R.id.game_4_matchup)
                val scoreIds = listOf(R.id.game_1_score, R.id.game_2_score, R.id.game_3_score, R.id.game_4_score)
                val gameRowIds = listOf(R.id.game_row_1, R.id.game_row_2, R.id.game_row_3, R.id.game_row_4)

                for (i in 0..3) {
                    if (i < games.size) {
                        val g = games[i]
                        views.setViewVisibility(gameRowIds[i], View.VISIBLE)
                        views.setTextViewText(matchupIds[i], "${g.awayTeamAbbrev} @ ${g.homeTeamAbbrev}")
                        val scoreText = when (g.state) {
                            "LIVE", "CRIT" -> "${g.awayScore}-${g.homeScore} 🔴"
                            "FINAL", "OFF" -> "${g.awayScore}-${g.homeScore} F"
                            else -> g.startsAt.substringAfterLast("T").take(5)
                        }
                        views.setTextViewText(scoreIds[i], scoreText)
                    } else {
                        views.setViewVisibility(gameRowIds[i], View.GONE)
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
