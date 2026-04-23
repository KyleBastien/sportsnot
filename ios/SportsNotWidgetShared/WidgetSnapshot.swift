import Foundation

/// Mirrors `WidgetSnapshot` in packages/widget-api/src/lib/types.ts.
/// Keep field names identical; this struct is decoded directly from the
/// edge function response.
public struct WidgetSnapshot: Codable, Sendable, Equatable {
    public struct League: Codable, Sendable, Equatable {
        public let id: String
        public let name: String
        public let shareCode: String
        public let currentRound: Int
        public let status: String
    }

    public struct Game: Codable, Sendable, Equatable, Identifiable {
        public let id: Int
        public let startsAt: String
        public let state: String
        public let homeTeamId: Int
        public let homeTeamAbbrev: String
        public let homeTeamName: String
        public let homeScore: Int
        public let awayTeamId: Int
        public let awayTeamAbbrev: String
        public let awayTeamName: String
        public let awayScore: Int
        public let period: Int?
        public let timeRemaining: String?
        public let hasDraftedPlayers: Bool
    }

    public struct DraftedPlayer: Codable, Sendable, Equatable, Identifiable {
        enum CodingKeys: String, CodingKey {
            case playerId
            case teamId
            case name
            case teamAbbrev
            case position
            case gameId
            case fantasyPoints
            case dailyFantasyPoints
            case ownedByTeamName
        }

        public var id: String {
            if let pid = playerId { return "p-\(pid)" }
            if let tid = teamId { return "t-\(tid)" }
            return "unknown-\(name)"
        }
        public let playerId: Int?
        public let teamId: Int?
        public let name: String
        public let teamAbbrev: String
        public let position: String
        public let gameId: Int?
        public let fantasyPoints: Double
        public let dailyFantasyPoints: Double
        public let ownedByTeamName: String

        public init(
            playerId: Int?,
            teamId: Int?,
            name: String,
            teamAbbrev: String,
            position: String,
            gameId: Int?,
            fantasyPoints: Double,
            dailyFantasyPoints: Double = 0,
            ownedByTeamName: String
        ) {
            self.playerId = playerId
            self.teamId = teamId
            self.name = name
            self.teamAbbrev = teamAbbrev
            self.position = position
            self.gameId = gameId
            self.fantasyPoints = fantasyPoints
            self.dailyFantasyPoints = dailyFantasyPoints
            self.ownedByTeamName = ownedByTeamName
        }

        public init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            playerId = try container.decodeIfPresent(Int.self, forKey: .playerId)
            teamId = try container.decodeIfPresent(Int.self, forKey: .teamId)
            name = try container.decode(String.self, forKey: .name)
            teamAbbrev = try container.decode(String.self, forKey: .teamAbbrev)
            position = try container.decode(String.self, forKey: .position)
            gameId = try container.decodeIfPresent(Int.self, forKey: .gameId)
            fantasyPoints = try container.decode(Double.self, forKey: .fantasyPoints)
            dailyFantasyPoints = try container.decodeIfPresent(
                Double.self,
                forKey: .dailyFantasyPoints
            ) ?? 0
            ownedByTeamName = try container.decode(
                String.self,
                forKey: .ownedByTeamName
            )
        }
    }

    public let league: League
    public let date: String
    public let generatedAt: String
    public let games: [Game]
    public let players: [DraftedPlayer]
}
