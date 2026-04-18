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
        public let ownedByTeamName: String
    }

    public let league: League
    public let date: String
    public let generatedAt: String
    public let games: [Game]
    public let players: [DraftedPlayer]
}
