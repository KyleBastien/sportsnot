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
        let entry = await self.entry(for: configuration)
        // Reload every 2 minutes when any game is live, every 15 minutes otherwise.
        let nextRefresh = refreshDate(for: entry.snapshot)
        return Timeline(entries: [entry], policy: .after(nextRefresh))
    }

    // MARK: - Helpers

    private func entry(for configuration: FeaturedLeagueIntent) async -> SnapshotEntry {
        let shareCode = configuration.shareCode ?? AppGroup.featuredShareCode
        guard let code = shareCode, !code.isEmpty else {
            return SnapshotEntry(
                date: .now,
                snapshot: nil,
                staleFromCache: false,
                shareCode: nil,
                errorMessage: "Open SportsNot and tap Feature on widget in a league."
            )
        }
        guard let config = SnapshotAPIConfig.fromBundle() else {
            return SnapshotEntry(
                date: .now,
                snapshot: AppGroup.cachedSnapshot()?.snapshot,
                staleFromCache: AppGroup.cachedSnapshot() != nil,
                shareCode: code,
                errorMessage: "Widget is not configured"
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
                errorMessage: nil
            )
        } catch {
            let cached = AppGroup.cachedSnapshot()
            return SnapshotEntry(
                date: .now,
                snapshot: cached?.snapshot,
                staleFromCache: cached != nil,
                shareCode: code,
                errorMessage: cached == nil ? "Couldn't load snapshot" : nil
            )
        }
    }

    private func refreshDate(for snapshot: WidgetSnapshot?) -> Date {
        let anyLive = snapshot?.games.contains { $0.state == "LIVE" } ?? false
        let minutes: Int = anyLive ? 2 : 15
        return Calendar.current.date(byAdding: .minute, value: minutes, to: .now) ?? .now.addingTimeInterval(Double(minutes * 60))
    }
}
