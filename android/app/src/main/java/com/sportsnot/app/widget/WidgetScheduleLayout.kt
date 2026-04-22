package com.sportsnot.app.widget

import com.sportsnot.app.widget.models.WidgetDraftedPlayer
import com.sportsnot.app.widget.models.WidgetGame
import com.sportsnot.app.widget.models.WidgetSnapshot
import java.text.SimpleDateFormat
import java.util.Comparator
import java.util.Date
import java.util.Locale

internal enum class WidgetHomeSize {
    SMALL,
    MEDIUM,
    LARGE
}

internal object WidgetScheduleLayout {
    data class FamilyConfig(
        val gamesPerPage: Int,
        val maxFantasyTeamsPerGame: Int,
        val maxNhlGroupsPerFantasyTeam: Int,
        val compactRows: Boolean
    )

    data class TeamAssetLine(
        val teamAbbrev: String,
        val assetNames: List<String>
    )

    data class FantasyTeamGroup(
        val name: String,
        val totalFantasyPoints: Double,
        val teamLines: List<TeamAssetLine>
    )

    data class GameSection(
        val game: WidgetGame,
        val fantasyTeams: List<FantasyTeamGroup>
    )

    fun config(size: WidgetHomeSize): FamilyConfig =
        when (size) {
            WidgetHomeSize.SMALL -> FamilyConfig(
                gamesPerPage = 1,
                maxFantasyTeamsPerGame = 2,
                maxNhlGroupsPerFantasyTeam = 1,
                compactRows = true
            )
            WidgetHomeSize.MEDIUM -> FamilyConfig(
                gamesPerPage = 2,
                maxFantasyTeamsPerGame = 2,
                maxNhlGroupsPerFantasyTeam = 2,
                compactRows = false
            )
            WidgetHomeSize.LARGE -> FamilyConfig(
                gamesPerPage = 4,
                maxFantasyTeamsPerGame = 2,
                maxNhlGroupsPerFantasyTeam = 2,
                compactRows = false
            )
        }

    fun totalPages(snapshot: WidgetSnapshot?, size: WidgetHomeSize): Int {
        if (snapshot == null) return 1
        val sections = sections(snapshot, size)
        val gamesPerPage = config(size).gamesPerPage.coerceAtLeast(1)
        return maxOf(1, (sections.size + gamesPerPage - 1) / gamesPerPage)
    }

    fun pageSections(
        snapshot: WidgetSnapshot?,
        size: WidgetHomeSize,
        pageIndex: Int
    ): List<GameSection> {
        if (snapshot == null) return emptyList()
        val sections = sections(snapshot, size)
        if (sections.isEmpty()) return emptyList()
        val gamesPerPage = config(size).gamesPerPage.coerceAtLeast(1)
        val safeIndex = pageIndex.coerceAtLeast(0)
        val start = (safeIndex * gamesPerPage).coerceAtMost(sections.size)
        val end = (start + gamesPerPage).coerceAtMost(sections.size)
        return sections.subList(start, end)
    }

    fun headerText(game: WidgetGame): String {
        val matchup = "${game.awayTeamAbbrev} @ ${game.homeTeamAbbrev}"
        return when (game.state) {
            "LIVE", "CRIT" -> {
                val detail = liveDetail(game)
                "$matchup - ${game.awayScore}-${game.homeScore} $detail".trim()
            }
            "FINAL", "OFF" -> "$matchup - ${game.awayScore}-${game.homeScore} F"
            else -> "$matchup - ${startTimeText(game.startsAt)}"
        }
    }

    fun bodyText(section: GameSection, size: WidgetHomeSize): String? {
        val cfg = config(size)
        if (section.fantasyTeams.isEmpty()) return null

        val visibleTeams = section.fantasyTeams.take(cfg.maxFantasyTeamsPerGame)
        val lines = mutableListOf<String>()

        if (cfg.compactRows) {
            visibleTeams.mapTo(lines) { compactRowText(it, cfg) }
        } else {
            visibleTeams.forEach { team ->
                lines += team.name
                val visibleGroups = team.teamLines.take(cfg.maxNhlGroupsPerFantasyTeam)
                visibleGroups.forEach { group ->
                    lines += "- ${group.teamAbbrev}: ${group.assetNames.joinToString(", ")}"
                }
                val hiddenGroups = team.teamLines.size - visibleGroups.size
                if (hiddenGroups > 0) {
                    lines += "- +$hiddenGroups more NHL groups"
                }
            }
        }

        val hiddenTeams = section.fantasyTeams.size - visibleTeams.size
        if (hiddenTeams > 0) {
            lines += "+$hiddenTeams more teams"
        }

        return lines.takeIf { it.isNotEmpty() }?.joinToString("\n")
    }

    fun footerText(snapshot: WidgetSnapshot, myTeamName: String?): String? {
        if (myTeamName.isNullOrBlank()) return null
        val total = snapshot.players
            .filter { it.ownedByTeamName == myTeamName }
            .sumOf { it.fantasyPoints }
        return "$myTeamName - ${formatPoints(total)} pts"
    }

    private fun sections(
        snapshot: WidgetSnapshot,
        size: WidgetHomeSize
    ): List<GameSection> {
        val groupedGames = snapshot.games.map { game ->
            GameSection(
                game = game,
                fantasyTeams = groupedFantasyTeams(
                    snapshot.players.filter { it.gameId == game.id }
                )
            )
        }

        return when (size) {
            WidgetHomeSize.SMALL ->
                groupedGames.sortedWith(Comparator(::smallPriorityComparator))
            WidgetHomeSize.MEDIUM, WidgetHomeSize.LARGE ->
                groupedGames.sortedWith(Comparator(::chronologicalComparator))
        }
    }

    private fun groupedFantasyTeams(
        players: List<WidgetDraftedPlayer>
    ): List<FantasyTeamGroup> =
        players
            .groupBy { it.ownedByTeamName }
            .map { (teamName, members) ->
                FantasyTeamGroup(
                    name = teamName,
                    totalFantasyPoints = members.sumOf { it.fantasyPoints },
                    teamLines = members
                        .groupBy { if (it.teamAbbrev.isBlank()) "NHL" else it.teamAbbrev }
                        .map { (teamAbbrev, assets) ->
                            TeamAssetLine(
                                teamAbbrev = teamAbbrev,
                                assetNames = assets
                                    .sortedWith(Comparator(::draftedAssetComparator))
                                    .map { it.name }
                            )
                        }
                        .sortedBy { it.teamAbbrev }
                )
            }
            .sortedWith(
                compareByDescending<FantasyTeamGroup> { it.totalFantasyPoints }
                    .thenBy { it.name.lowercase(Locale.US) }
            )

    private fun compactRowText(
        team: FantasyTeamGroup,
        cfg: FamilyConfig
    ): String {
        val visibleGroups = team.teamLines.take(cfg.maxNhlGroupsPerFantasyTeam)
        val segments = visibleGroups.map {
            "${it.teamAbbrev}: ${it.assetNames.joinToString(", ")}"
        }
        var row = team.name
        if (segments.isNotEmpty()) {
            row += " • ${segments.joinToString(" • ")}"
        }
        val hiddenGroups = team.teamLines.size - visibleGroups.size
        if (hiddenGroups > 0) {
            row += " • +$hiddenGroups more"
        }
        return row
    }

    private fun chronologicalComparator(lhs: GameSection, rhs: GameSection): Int {
        val leftDate = gameDate(lhs.game.startsAt) ?: Date(Long.MAX_VALUE)
        val rightDate = gameDate(rhs.game.startsAt) ?: Date(Long.MAX_VALUE)
        if (leftDate != rightDate) {
            return leftDate.compareTo(rightDate)
        }
        return lhs.game.id.compareTo(rhs.game.id)
    }

    private fun smallPriorityComparator(lhs: GameSection, rhs: GameSection): Int {
        val leftRank = smallPriorityRank(lhs)
        val rightRank = smallPriorityRank(rhs)
        if (leftRank != rightRank) {
            return leftRank.compareTo(rightRank)
        }
        return chronologicalComparator(lhs, rhs)
    }

    private fun smallPriorityRank(section: GameSection): Int =
        when {
            section.fantasyTeams.isNotEmpty() && isLive(section.game) -> 0
            section.fantasyTeams.isNotEmpty() -> 1
            else -> 2
        }

    private fun draftedAssetComparator(
        lhs: WidgetDraftedPlayer,
        rhs: WidgetDraftedPlayer
    ): Int {
        if (lhs.fantasyPoints != rhs.fantasyPoints) {
            return rhs.fantasyPoints.compareTo(lhs.fantasyPoints)
        }
        return lhs.name.lowercase(Locale.US).compareTo(rhs.name.lowercase(Locale.US))
    }

    private fun isLive(game: WidgetGame): Boolean =
        game.state == "LIVE" || game.state == "CRIT"

    private fun liveDetail(game: WidgetGame): String {
        val period = game.period?.let { "P$it" } ?: "LIVE"
        return if (!game.timeRemaining.isNullOrBlank()) {
            "$period ${game.timeRemaining}"
        } else {
            period
        }
    }

    private fun startTimeText(value: String): String {
        val date = gameDate(value) ?: return value
        val formatter = SimpleDateFormat("h:mm a", Locale.US)
        return formatter.format(date)
    }

    private fun gameDate(value: String): Date? = try {
        SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssX", Locale.US).parse(value)
    } catch (_: Exception) {
        null
    }
}
