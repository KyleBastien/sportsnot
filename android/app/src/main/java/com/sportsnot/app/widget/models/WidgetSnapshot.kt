package com.sportsnot.app.widget.models

import kotlinx.serialization.Serializable

@Serializable
data class WidgetSnapshot(
    val league: League,
    val date: String,
    val generatedAt: String,
    val games: List<WidgetGame>,
    val players: List<WidgetDraftedPlayer>
)

@Serializable
data class League(
    val id: String,
    val name: String,
    val shareCode: String,
    val currentRound: Int,
    val status: String
)

@Serializable
data class WidgetGame(
    val id: Int,
    val startsAt: String,
    val state: String,
    val homeTeamId: Int,
    val homeTeamAbbrev: String,
    val homeTeamName: String,
    val homeScore: Int,
    val awayTeamId: Int,
    val awayTeamAbbrev: String,
    val awayTeamName: String,
    val awayScore: Int,
    val period: Int? = null,
    val timeRemaining: String? = null,
    val hasDraftedPlayers: Boolean
)

@Serializable
data class WidgetDraftedPlayer(
    val playerId: Int? = null,
    val teamId: Int? = null,
    val name: String,
    val teamAbbrev: String,
    val position: String,
    val gameId: Int? = null,
    val fantasyPoints: Double,
    val ownedByTeamName: String
)
