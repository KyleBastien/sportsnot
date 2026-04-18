import ActivityKit
import Foundation

/// Attributes are constant for the lifetime of a Live Activity — here we
/// key by league share code and include the league display name that was
/// current when the activity was started.
public struct SportsNotGameAttributes: ActivityAttributes, Sendable {
    public struct ContentState: Codable, Hashable, Sendable {
        public struct GameScore: Codable, Hashable, Sendable {
            public var homeAbbr: String
            public var awayAbbr: String
            public var homeScore: Int
            public var awayScore: Int
            public var state: String
            public var period: Int?
            public var clock: String?

            public init(homeAbbr: String, awayAbbr: String, homeScore: Int, awayScore: Int, state: String, period: Int? = nil, clock: String? = nil) {
                self.homeAbbr = homeAbbr
                self.awayAbbr = awayAbbr
                self.homeScore = homeScore
                self.awayScore = awayScore
                self.state = state
                self.period = period
                self.clock = clock
            }
        }

        public struct PlayerPoints: Codable, Hashable, Sendable {
            public var playerId: Int?
            public var teamId: Int?
            public var name: String
            public var teamAbbrev: String
            public var fantasyPoints: Double
            public var gameId: Int?

            public init(playerId: Int?, teamId: Int?, name: String, teamAbbrev: String, fantasyPoints: Double, gameId: Int?) {
                self.playerId = playerId
                self.teamId = teamId
                self.name = name
                self.teamAbbrev = teamAbbrev
                self.fantasyPoints = fantasyPoints
                self.gameId = gameId
            }
        }

        public var updatedAt: Date
        /// Every game on today's slate, keyed by game id.
        public var games: [String: GameScore]
        /// Only players on the featured league's roster.
        public var players: [PlayerPoints]

        public init(updatedAt: Date, games: [String: GameScore], players: [PlayerPoints]) {
            self.updatedAt = updatedAt
            self.games = games
            self.players = players
        }
    }

    public var leagueId: String
    public var leagueName: String
    public var shareCode: String

    public init(leagueId: String, leagueName: String, shareCode: String) {
        self.leagueId = leagueId
        self.leagueName = leagueName
        self.shareCode = shareCode
    }
}
