package com.sportsnot.app.widget

import com.sportsnot.app.widget.models.League
import com.sportsnot.app.widget.models.WidgetDraftedPlayer
import com.sportsnot.app.widget.models.WidgetGame
import com.sportsnot.app.widget.models.WidgetSnapshot
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class WidgetScheduleLayoutTest {

    @Test
    fun `small pages prioritize live drafted games first`() {
        val snapshot = snapshot(
            games = listOf(
                game(id = 1, startsAt = "2026-04-21T23:00:00Z", state = "FUT"),
                game(id = 2, startsAt = "2026-04-21T22:00:00Z", state = "LIVE"),
                game(id = 3, startsAt = "2026-04-21T21:00:00Z", state = "FUT")
            ),
            players = listOf(
                player(gameId = 1, ownedBy = "12 Bar Hughes", name = "Nick Suzuki"),
                player(gameId = 2, ownedBy = "Connor McJudah", name = "Jake Guentzel")
            )
        )

        val first = WidgetScheduleLayout.pageSections(
            snapshot,
            WidgetHomeSize.SMALL,
            0
        ).single()
        val second = WidgetScheduleLayout.pageSections(
            snapshot,
            WidgetHomeSize.SMALL,
            1
        ).single()
        val third = WidgetScheduleLayout.pageSections(
            snapshot,
            WidgetHomeSize.SMALL,
            2
        ).single()

        assertEquals(2, first.game.id)
        assertEquals(1, second.game.id)
        assertEquals(3, third.game.id)
    }

    @Test
    fun `body text groups assets by fantasy team then nhl team`() {
        val section = WidgetScheduleLayout.pageSections(
            snapshot(
                games = listOf(game(id = 10, startsAt = "2026-04-21T23:00:00Z")),
                players = listOf(
                    player(
                        gameId = 10,
                        ownedBy = "12 Bar Hughes",
                        teamAbbrev = "MTL",
                        name = "Cole Caufield",
                        fantasyPoints = 5.0
                    ),
                    player(
                        gameId = 10,
                        ownedBy = "12 Bar Hughes",
                        teamAbbrev = "MTL",
                        name = "Nick Suzuki",
                        fantasyPoints = 7.0
                    ),
                    player(
                        gameId = 10,
                        ownedBy = "12 Bar Hughes",
                        teamAbbrev = "TBL",
                        name = "Nikita Kucherov",
                        fantasyPoints = 9.0
                    ),
                    player(
                        gameId = 10,
                        ownedBy = "Connor McJudah",
                        teamAbbrev = "TBL",
                        name = "Jake Guentzel",
                        fantasyPoints = 4.0
                    )
                )
            ),
            WidgetHomeSize.LARGE,
            0
        ).single()

        val body = WidgetScheduleLayout.bodyText(section, WidgetHomeSize.LARGE)

        assertTrue(body!!.contains("12 Bar Hughes"))
        assertTrue(body.contains("- MTL: Nick Suzuki, Cole Caufield"))
        assertTrue(body.contains("- TBL: Nikita Kucherov"))
        assertTrue(body.contains("Connor McJudah"))
    }

    @Test
    fun `medium pages chunk by games`() {
        val snapshot = snapshot(
            games = listOf(
                game(id = 1, startsAt = "2026-04-21T20:00:00Z"),
                game(id = 2, startsAt = "2026-04-21T21:00:00Z"),
                game(id = 3, startsAt = "2026-04-21T22:00:00Z")
            ),
            players = emptyList()
        )

        assertEquals(
            2,
            WidgetScheduleLayout.totalPages(snapshot, WidgetHomeSize.MEDIUM)
        )
        assertEquals(
            listOf(1, 2),
            WidgetScheduleLayout.pageSections(
                snapshot,
                WidgetHomeSize.MEDIUM,
                0
            ).map { it.game.id }
        )
        assertEquals(
            listOf(3),
            WidgetScheduleLayout.pageSections(
                snapshot,
                WidgetHomeSize.MEDIUM,
                1
            ).map { it.game.id }
        )
    }

    private fun snapshot(
        games: List<WidgetGame>,
        players: List<WidgetDraftedPlayer>
    ) = WidgetSnapshot(
        league = League(
            id = "league-1",
            name = "Test League",
            shareCode = "ABC123",
            currentRound = 1,
            status = "active"
        ),
        date = "2026-04-21",
        generatedAt = "2026-04-21T18:00:00Z",
        games = games,
        players = players
    )

    private fun game(
        id: Int,
        startsAt: String,
        state: String = "FUT"
    ) = WidgetGame(
        id = id,
        startsAt = startsAt,
        state = state,
        homeTeamId = id * 10,
        homeTeamAbbrev = "T$id",
        homeTeamName = "Home $id",
        homeScore = 0,
        awayTeamId = id * 10 + 1,
        awayTeamAbbrev = "A$id",
        awayTeamName = "Away $id",
        awayScore = 0,
        period = if (state == "LIVE") 2 else null,
        timeRemaining = if (state == "LIVE") "14:07" else null,
        hasDraftedPlayers = true
    )

    private fun player(
        gameId: Int,
        ownedBy: String,
        teamAbbrev: String = "MTL",
        name: String,
        fantasyPoints: Double = 3.0
    ) = WidgetDraftedPlayer(
        playerId = null,
        teamId = null,
        name = name,
        teamAbbrev = teamAbbrev,
        position = "F",
        gameId = gameId,
        fantasyPoints = fantasyPoints,
        ownedByTeamName = ownedBy
    )
}
