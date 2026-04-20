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

    /// How many drafted players each family can render per page. Small only
    /// fits a single player line; Medium matches the previous static cap of
    /// 3; Large gets ~8 rows comfortably.
    static func playersPerPage(for family: WidgetFamily) -> Int {
        switch family {
        case .systemSmall: return 1
        case .systemMedium: return 3
        case .systemLarge: return 8
        default: return 0  // accessory families don't paginate
        }
    }

    private func paginatedEntries(
        base: SnapshotEntry,
        family: WidgetFamily,
        nextRefresh: Date
    ) -> [SnapshotEntry] {
        let perPage = Self.playersPerPage(for: family)
        let players = base.snapshot?.players.filter { $0.gameId != nil } ?? []
        let totalPages = perPage > 0
            ? max(1, Int(ceil(Double(players.count) / Double(perPage))))
            : 1

        if totalPages <= 1 {
            // Single entry preserves prior behavior for accessory families
            // and for snapshots that fit in one page.
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

    private func entry(for configuration: FeaturedLeagueIntent) async -> SnapshotEntry {
        let shareCode = configuration.shareCode ?? AppGroup.featuredShareCode
        let myTeamName = shareCode.flatMap { AppGroup.myTeamName(forShareCode: $0) }
        guard let code = shareCode, !code.isEmpty else {
            return SnapshotEntry(
                date: .now,
                snapshot: nil,
                staleFromCache: false,
                shareCode: nil,
                errorMessage: "Open SportsNot and tap Feature on widget in a league.",
                myTeamName: nil
            )
        }
        guard let config = SnapshotAPIConfig.fromBundle() else {
            return SnapshotEntry(
                date: .now,
                snapshot: AppGroup.cachedSnapshot()?.snapshot,
                staleFromCache: AppGroup.cachedSnapshot() != nil,
                shareCode: code,
                errorMessage: "Widget is not configured",
                myTeamName: myTeamName
            )
        }
        let api = SnapshotAPI(config: config)
        do {
            let fresh = try await api.fetchSnapshot(shareCode: code)
            try? AppGroup.cacheSnapshot(fresh)
            return SnapshotEntry(
                date: .now,
                snapshot: fresh,
                staleFromCache: false,
                shareCode: code,
                errorMessage: nil,
                myTeamName: myTeamName
            )
        } catch {
            let cached = AppGroup.cachedSnapshot()
            return SnapshotEntry(
                date: .now,
                snapshot: cached?.snapshot,
                staleFromCache: cached != nil,
                shareCode: code,
                errorMessage: cached == nil ? "Couldn't load snapshot" : nil,
                myTeamName: myTeamName
            )
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
