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
