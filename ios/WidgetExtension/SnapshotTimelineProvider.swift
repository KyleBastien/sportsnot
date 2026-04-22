import Foundation
import WidgetKit

@available(iOS 17.0, *)
struct SnapshotTimelineProvider: AppIntentTimelineProvider {
    typealias Entry = SnapshotEntry
    typealias Intent = FeaturedLeagueIntent

    func placeholder(in context: Context) -> SnapshotEntry { .placeholder }

    func snapshot(for configuration: FeaturedLeagueIntent, in context: Context) async -> SnapshotEntry {
        await entry(for: configuration)
    }

    func timeline(for configuration: FeaturedLeagueIntent, in context: Context) async -> Timeline<SnapshotEntry> {
        let baseEntry = await self.entry(for: configuration)
        let nextRefresh = refreshDate(for: baseEntry.snapshot)
        let entries = paginatedEntries(
            base: baseEntry,
            family: context.family,
            nextRefresh: nextRefresh
        )
        return Timeline(entries: entries, policy: .after(nextRefresh))
    }

    // MARK: - Pagination

    // Visual rotation cadence between pages. WidgetKit forbids true
    // sub-minute timeline reloads, but pre-built entries spaced N seconds
    // apart are honored by the system when rendering the timeline that the
    // provider returned.
    private static let pageDurationSeconds: TimeInterval = 30

    private func paginatedEntries(
        base: SnapshotEntry,
        family: WidgetFamily,
        nextRefresh: Date
    ) -> [SnapshotEntry] {
        let totalPages = WidgetScheduleLayout.totalPages(
            for: base.snapshot,
            family: family
        )

        if totalPages <= 1 {
            return [SnapshotEntry(
                date: base.date,
                snapshot: base.snapshot,
                staleFromCache: base.staleFromCache,
                shareCode: base.shareCode,
                errorMessage: base.errorMessage,
                myTeamName: base.myTeamName,
                pageIndex: 0,
                totalPages: 1
            )]
        }

        // Fill the time until the next data refresh with rotating page
        // entries, cycling page indices if there is room for more rotations
        // than there are pages.
        let availableSeconds = max(
            Self.pageDurationSeconds,
            nextRefresh.timeIntervalSince(base.date)
        )
        let slots = max(1, Int(floor(availableSeconds / Self.pageDurationSeconds)))

        return (0..<slots).map { i in
            SnapshotEntry(
                date: base.date.addingTimeInterval(Self.pageDurationSeconds * Double(i)),
                snapshot: base.snapshot,
                staleFromCache: base.staleFromCache,
                shareCode: base.shareCode,
                errorMessage: base.errorMessage,
                myTeamName: base.myTeamName,
                pageIndex: i % totalPages,
                totalPages: totalPages
            )
        }
    }

    // MARK: - Helpers

    // Cache TTLs:
    //  - If the main app primed the cache within `freshCacheMaxAge`, the
    //    extension reuses it instead of making its own network call. This
    //    avoids hitting the constrained extension network and guarantees
    //    the widget shows what the app last fetched.
    //  - On a fetch failure, the extension only falls back to cached data
    //    that is younger than `staleFallbackMaxAge`. Older cached data is
    //    treated as missing so the widget surfaces an error rather than
    //    showing yesterday's slate forever.
    private static let freshCacheMaxAge: TimeInterval = 120        // 2 minutes
    private static let staleFallbackMaxAge: TimeInterval = 60 * 60 // 1 hour

    private func entry(for configuration: FeaturedLeagueIntent) async -> SnapshotEntry {
        // The featured league is controlled exclusively by the in-app
        // Feature on widget button via AppGroup.featuredShareCode. The
        // configuration intent intentionally exposes no editable fields,
        // so there's nothing to read off `configuration` here.
        let shareCode = AppGroup.featuredShareCode
        let myTeamName = shareCode.flatMap { AppGroup.myTeamName(forShareCode: $0) }
        WidgetTelemetry.record("timeline.entry.start", [
            "hasShareCode": shareCode == nil ? "false" : "true",
            "shareCode": shareCode ?? "",
            "cachedAge": AppGroup.cachedSnapshotAge.map { String(Int($0)) } ?? "nil",
        ])
        guard let code = shareCode, !code.isEmpty else {
            WidgetTelemetry.record("timeline.entry.no_share_code", [:])
            return SnapshotEntry(
                date: .now,
                snapshot: nil,
                staleFromCache: false,
                shareCode: nil,
                errorMessage: "Open SportsNot and tap Feature on widget in a league.",
                myTeamName: nil
            )
        }

        // Prefer a recently-primed cache (written by the main app on
        // foreground) over making our own network call from the extension.
        if let recent = AppGroup.cachedSnapshot(maxAge: Self.freshCacheMaxAge) {
            WidgetTelemetry.record("timeline.cache.fresh", [
                "ageSec": String(Int(Date().timeIntervalSince(recent.stored))),
            ])
            return SnapshotEntry(
                date: .now,
                snapshot: recent.snapshot,
                staleFromCache: false,
                shareCode: code,
                errorMessage: nil,
                myTeamName: myTeamName
            )
        }

        guard let config = SnapshotAPIConfig.fromBundle() else {
            let cached = AppGroup.cachedSnapshot(maxAge: Self.staleFallbackMaxAge)
            WidgetTelemetry.record("timeline.config_missing", [
                "hasStaleFallback": cached == nil ? "false" : "true",
            ])
            return SnapshotEntry(
                date: .now,
                snapshot: cached?.snapshot,
                staleFromCache: cached != nil,
                shareCode: code,
                errorMessage: "Widget is not configured (E:cfg)",
                myTeamName: myTeamName
            )
        }
        let api = SnapshotAPI(config: config)
        do {
            let fresh = try await api.fetchSnapshot(shareCode: code)
            try? AppGroup.cacheSnapshot(fresh)
            WidgetTelemetry.record("timeline.fetch.ok", [
                "games": String(fresh.games.count),
                "players": String(fresh.players.count),
            ])
            return SnapshotEntry(
                date: .now,
                snapshot: fresh,
                staleFromCache: false,
                shareCode: code,
                errorMessage: nil,
                myTeamName: myTeamName
            )
        } catch {
            // Fall back to cached data only if it's still reasonably fresh.
            // Anything older than `staleFallbackMaxAge` is dropped to avoid
            // showing yesterday's games when the network is unreachable.
            let cached = AppGroup.cachedSnapshot(maxAge: Self.staleFallbackMaxAge)
            let code = errorCode(for: error)
            WidgetTelemetry.record("timeline.fetch.error", [
                "errorCode": code,
                "error": String(describing: error),
                "hasStaleFallback": cached == nil ? "false" : "true",
            ])
            return SnapshotEntry(
                date: .now,
                snapshot: cached?.snapshot,
                staleFromCache: cached != nil,
                shareCode: shareCode,
                errorMessage: cached == nil ? "Couldn't load snapshot (E:\(code))" : nil,
                myTeamName: myTeamName
            )
        }
    }

    /// Compresses a `SnapshotAPIError` into a short token that's safe to
    /// embed in the user-visible "Couldn't load snapshot" string. Lets a
    /// user report the failure mode at a glance without needing to grab
    /// device logs.
    private func errorCode(for error: Error) -> String {
        guard let api = error as? SnapshotAPIError else { return "unk" }
        switch api {
        case .missingConfig: return "cfg"
        case .badStatus(let code, _): return "h\(code)"
        case .decoding: return "dec"
        case .transport: return "net"
        }
    }

    private func refreshDate(for snapshot: WidgetSnapshot?) -> Date {
        let anyLive = snapshot?.games.contains { $0.state == "LIVE" || $0.state == "CRIT" } ?? false
        // 5 minutes during live games balances freshness vs WidgetKit reload
        // budget (~40-70/day). 2 minutes blows the budget in a single game.
        let minutes: Int = anyLive ? 5 : 15
        return Calendar.current.date(byAdding: .minute, value: minutes, to: .now) ?? .now.addingTimeInterval(Double(minutes * 60))
    }
}

@available(iOS 17.0, *)
enum WidgetScheduleLayout {
    struct AssetEntry: Hashable {
        let name: String
        let fantasyPoints: Double
    }

    struct FamilyConfig {
        let gamesPerPage: Int
        let maxFantasyTeamsPerGame: Int
        let fantasyTeamColumns: Int
        let maxNhlGroupsPerFantasyTeam: Int
        let maxNamesPerLine: Int
        let compactRows: Bool
        let bodyLineLimit: Int
    }

    struct TeamAssetLine: Hashable {
        let teamAbbrev: String
        let assets: [AssetEntry]
    }

    struct FantasyTeamGroup: Hashable, Identifiable {
        var id: String { name }
        let name: String
        let totalFantasyPoints: Double
        let teamLines: [TeamAssetLine]
    }

    struct GameSection: Identifiable {
        var id: Int { game.id }
        let game: WidgetSnapshot.Game
        let fantasyTeams: [FantasyTeamGroup]
    }

    private static let isoFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    private static let displayTimeFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "h:mm a"
        return formatter
    }()

    static func config(for family: WidgetFamily) -> FamilyConfig {
        switch family {
        case .systemSmall:
            return FamilyConfig(
                gamesPerPage: 1,
                maxFantasyTeamsPerGame: 2,
                fantasyTeamColumns: 1,
                maxNhlGroupsPerFantasyTeam: 1,
                maxNamesPerLine: 1,
                compactRows: true,
                bodyLineLimit: 3
            )
        case .systemMedium:
            return FamilyConfig(
                gamesPerPage: 1,
                maxFantasyTeamsPerGame: 4,
                fantasyTeamColumns: 2,
                maxNhlGroupsPerFantasyTeam: 2,
                maxNamesPerLine: 1,
                compactRows: false,
                bodyLineLimit: 10
            )
        case .systemLarge:
            return FamilyConfig(
                gamesPerPage: 2,
                maxFantasyTeamsPerGame: 4,
                fantasyTeamColumns: 2,
                maxNhlGroupsPerFantasyTeam: 2,
                maxNamesPerLine: 1,
                compactRows: false,
                bodyLineLimit: 12
            )
        default:
            return FamilyConfig(
                gamesPerPage: 1,
                maxFantasyTeamsPerGame: 1,
                fantasyTeamColumns: 1,
                maxNhlGroupsPerFantasyTeam: 1,
                maxNamesPerLine: 1,
                compactRows: true,
                bodyLineLimit: 2
            )
        }
    }

    static func totalPages(
        for snapshot: WidgetSnapshot?,
        family: WidgetFamily
    ) -> Int {
        guard supportsPagination(for: family) else { return 1 }
        guard let snapshot else { return 1 }
        let sections = sections(for: snapshot, family: family)
        let gamesPerPage = max(1, config(for: family).gamesPerPage)
        return max(1, Int(ceil(Double(sections.count) / Double(gamesPerPage))))
    }

    static func pageSections(
        for snapshot: WidgetSnapshot?,
        family: WidgetFamily,
        pageIndex: Int
    ) -> [GameSection] {
        guard let snapshot else { return [] }
        let sections = sections(for: snapshot, family: family)
        let gamesPerPage = max(1, config(for: family).gamesPerPage)
        let start = min(pageIndex * gamesPerPage, sections.count)
        let end = min(start + gamesPerPage, sections.count)
        return Array(sections[start..<end])
    }

    static func headerText(for game: WidgetSnapshot.Game) -> String {
        let matchup = "\(game.awayTeamAbbrev) @ \(game.homeTeamAbbrev)"
        switch game.state {
        case "LIVE", "CRIT":
            let score = "\(game.awayScore)-\(game.homeScore)"
            let detail = liveDetail(for: game)
            return "\(matchup) — \(score) \(detail)".trimmingCharacters(in: .whitespaces)
        case "FINAL", "OFF":
            return "\(matchup) — \(game.awayScore)-\(game.homeScore) F"
        default:
            return "\(matchup) — \(startTimeText(for: game.startsAt))"
        }
    }

    static func bodyText(
        for section: GameSection,
        family: WidgetFamily
    ) -> String? {
        let cfg = config(for: family)
        guard !section.fantasyTeams.isEmpty else { return nil }

        let visibleTeams = visibleFantasyTeams(for: section, family: family)
        var lines: [String] = []

        if cfg.compactRows {
            lines = visibleTeams.map { compactRowText(for: $0, cfg: cfg) }
        } else {
            for team in visibleTeams {
                lines.append(team.name)
                lines.append(contentsOf: teamLines(for: team, family: family))
            }
        }

        let hiddenTeams = hiddenFantasyTeamCount(for: section, family: family)
        if hiddenTeams > 0 {
            lines.append("+\(hiddenTeams) more teams")
        }

        return lines.isEmpty ? nil : lines.joined(separator: "\n")
    }

    static func visibleFantasyTeams(
        for section: GameSection,
        family: WidgetFamily
    ) -> [FantasyTeamGroup] {
        Array(section.fantasyTeams.prefix(config(for: family).maxFantasyTeamsPerGame))
    }

    static func hiddenFantasyTeamCount(
        for section: GameSection,
        family: WidgetFamily
    ) -> Int {
        max(0, section.fantasyTeams.count - visibleFantasyTeams(
            for: section,
            family: family
        ).count)
    }

    static func teamLines(
        for team: FantasyTeamGroup,
        family: WidgetFamily
    ) -> [String] {
        let cfg = config(for: family)
        let visibleGroups = Array(team.teamLines.prefix(cfg.maxNhlGroupsPerFantasyTeam))
        var lines: [String] = []
        for group in visibleGroups {
            let wrappedGroupLines = wrappedTeamAssetLines(
                for: group,
                cfg: cfg
            )
            lines.append(contentsOf: wrappedGroupLines)
        }
        let hiddenGroups = team.teamLines.count - visibleGroups.count
        if hiddenGroups > 0 {
            lines.append("- +\(hiddenGroups) more NHL groups")
        }
        return lines
    }

    static func footerText(for entry: SnapshotEntry) -> String? {
        guard let team = entry.myTeamName, !team.isEmpty,
              let snapshot = entry.snapshot else { return nil }
        let total = snapshot.players
            .filter { $0.ownedByTeamName == team }
            .reduce(0) { $0 + $1.fantasyPoints }
        return String(format: "%@ · %.0f pts", team, total)
    }

    private static func sections(
        for snapshot: WidgetSnapshot,
        family: WidgetFamily
    ) -> [GameSection] {
        let groupedGames = snapshot.games.map { game in
            GameSection(
                game: game,
                fantasyTeams: groupedFantasyTeams(
                    snapshot.players.filter { $0.gameId == game.id }
                )
            )
        }

        switch family {
        case .systemSmall:
            return groupedGames.sorted(by: smallPrioritySort)
        default:
            return groupedGames.sorted(by: chronologicalSort)
        }
    }

    private static func supportsPagination(for family: WidgetFamily) -> Bool {
        switch family {
        case .systemSmall, .systemMedium, .systemLarge:
            return true
        default:
            return false
        }
    }

    private static func groupedFantasyTeams(
        _ players: [WidgetSnapshot.DraftedPlayer]
    ) -> [FantasyTeamGroup] {
        Dictionary(grouping: players, by: \.ownedByTeamName)
            .map { teamName, members in
                let total = members.reduce(0) { $0 + $1.fantasyPoints }
                let teamLines = Dictionary(grouping: members, by: \.teamAbbrev)
                    .map { abbrev, assets in
                        TeamAssetLine(
                            teamAbbrev: abbrev.isEmpty ? "NHL" : abbrev,
                            assets: assets
                                .sorted(by: draftedAssetSort)
                                .map {
                                    AssetEntry(
                                        name: $0.name,
                                        fantasyPoints: $0.fantasyPoints
                                    )
                                }
                        )
                    }
                    .sorted {
                        $0.teamAbbrev.localizedCaseInsensitiveCompare($1.teamAbbrev) == .orderedAscending
                    }
                return FantasyTeamGroup(
                    name: teamName,
                    totalFantasyPoints: total,
                    teamLines: teamLines
                )
            }
            .sorted {
                if $0.totalFantasyPoints != $1.totalFantasyPoints {
                    return $0.totalFantasyPoints > $1.totalFantasyPoints
                }
                return $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending
            }
    }

    private static func compactRowText(
        for team: FantasyTeamGroup,
        cfg: FamilyConfig
    ) -> String {
        let visibleGroups = Array(team.teamLines.prefix(cfg.maxNhlGroupsPerFantasyTeam))
        let segments = visibleGroups.map {
            let namesText = $0.assets
                .map(compactAssetText)
                .joined(separator: ", ")
            return "\($0.teamAbbrev): \(namesText)"
        }
        var row = team.name
        if !segments.isEmpty {
            row += " • " + segments.joined(separator: " • ")
        }
        let hiddenGroups = team.teamLines.count - visibleGroups.count
        if hiddenGroups > 0 {
            row += " • +\(hiddenGroups) more"
        }
        return row
    }

    private static func wrappedTeamAssetLines(
        for group: TeamAssetLine,
        cfg: FamilyConfig
    ) -> [String] {
        let assets = group.assets
        guard !assets.isEmpty else { return ["- \(group.teamAbbrev)"] }

        let chunkSize = max(1, cfg.maxNamesPerLine)
        let chunks = stride(from: 0, to: assets.count, by: chunkSize).map {
            Array(assets[$0..<min($0 + chunkSize, assets.count)])
        }

        return chunks.enumerated().map { index, chunk in
            let namesText = chunk
                .map(fullAssetText)
                .joined(separator: ", ")
            if index == 0 {
                return "- \(group.teamAbbrev): \(namesText)"
            }
            return "  \(namesText)"
        }
    }

    private static func compactAssetText(_ asset: AssetEntry) -> String {
        "\(asset.name) \(pointsText(for: asset.fantasyPoints))"
    }

    private static func fullAssetText(_ asset: AssetEntry) -> String {
        "\(asset.name) \(pointsText(for: asset.fantasyPoints))"
    }

    private static func pointsText(for value: Double) -> String {
        if value.rounded(.towardZero) == value {
            return String(format: "%.0f", value)
        }
        return String(format: "%.1f", value)
    }

    private static func chronologicalSort(_ lhs: GameSection, _ rhs: GameSection) -> Bool {
        let leftDate = gameDate(for: lhs.game.startsAt) ?? .distantFuture
        let rightDate = gameDate(for: rhs.game.startsAt) ?? .distantFuture
        if leftDate != rightDate {
            return leftDate < rightDate
        }
        return lhs.game.id < rhs.game.id
    }

    private static func smallPrioritySort(_ lhs: GameSection, _ rhs: GameSection) -> Bool {
        let leftRank = smallPriorityRank(for: lhs)
        let rightRank = smallPriorityRank(for: rhs)
        if leftRank != rightRank {
            return leftRank < rightRank
        }
        return chronologicalSort(lhs, rhs)
    }

    private static func smallPriorityRank(for section: GameSection) -> Int {
        if !section.fantasyTeams.isEmpty && isLive(section.game) {
            return 0
        }
        if !section.fantasyTeams.isEmpty {
            return 1
        }
        return 2
    }

    private static func isLive(_ game: WidgetSnapshot.Game) -> Bool {
        game.state == "LIVE" || game.state == "CRIT"
    }

    private static func draftedAssetSort(
        _ lhs: WidgetSnapshot.DraftedPlayer,
        _ rhs: WidgetSnapshot.DraftedPlayer
    ) -> Bool {
        if lhs.fantasyPoints != rhs.fantasyPoints {
            return lhs.fantasyPoints > rhs.fantasyPoints
        }
        return lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
    }

    private static func startTimeText(for value: String) -> String {
        guard let date = gameDate(for: value) else { return value }
        return displayTimeFormatter.string(from: date)
    }

    private static func liveDetail(for game: WidgetSnapshot.Game) -> String {
        let period = game.period.map { "P\($0)" } ?? "LIVE"
        if let timeRemaining = game.timeRemaining, !timeRemaining.isEmpty {
            return "\(period) \(timeRemaining)"
        }
        return period
    }

    private static func gameDate(for value: String) -> Date? {
        isoFormatter.date(from: value)
    }
}
