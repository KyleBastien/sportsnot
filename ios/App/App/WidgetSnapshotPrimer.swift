import Foundation
import WidgetKit
import os.log

/// Fetches the widget snapshot from the main app process and writes it to
/// the App Group cache, then asks WidgetKit to reload all timelines.
///
/// Why we do this from the main app:
///   1. The widget extension is subject to a daily reload budget (~40-70).
///      During a long live game it can be exhausted, after which the
///      extension's own `timeline(for:in:)` may not run for hours.
///   2. Network calls in the extension are constrained (memory + time).
///      Failures there leave the widget showing whatever was in cache,
///      potentially stale (e.g. yesterday's games).
///   3. `WidgetCenter.reloadAllTimelines()` from the container app is NOT
///      throttled the way internal extension reloads are — it forces an
///      immediate reload. Combined with a freshly-primed AppGroup cache,
///      the extension can return current data without making its own
///      network call.
enum WidgetSnapshotPrimer {
    private static let log = OSLog(subsystem: "com.sportsnot.app", category: "WidgetSnapshotPrimer")
    private static let inflight = NSLock()
    private static var isRefreshing = false

    /// Fire-and-forget refresh. Safe to call from any lifecycle hook
    /// (didBecomeActive, willEnterForeground, openURL, etc.).
    static func refresh(reason: String) {
        // Coalesce overlapping calls — multiple lifecycle hooks can fire
        // back-to-back and we only want one in-flight network request.
        inflight.lock()
        if isRefreshing {
            inflight.unlock()
            return
        }
        isRefreshing = true
        inflight.unlock()

        Task.detached(priority: .userInitiated) {
            defer {
                inflight.lock()
                isRefreshing = false
                inflight.unlock()
            }
            await runRefresh(reason: reason)
        }
    }

    private static func runRefresh(reason: String) async {
        guard let shareCode = AppGroup.featuredShareCode, !shareCode.isEmpty else {
            os_log("Skip refresh (%{public}@): no featured share code", log: log, type: .debug, reason)
            return
        }
        guard let config = SnapshotAPIConfig.fromBundle() else {
            os_log("Skip refresh (%{public}@): missing SUPABASE config", log: log, type: .error, reason)
            return
        }

        let api = SnapshotAPI(config: config)
        do {
            let snapshot = try await api.fetchSnapshot(shareCode: shareCode)
            try? AppGroup.cacheSnapshot(snapshot)
            os_log("Primed snapshot (%{public}@): games=%{public}d players=%{public}d",
                   log: log, type: .info, reason, snapshot.games.count, snapshot.players.count)
        } catch {
            os_log("Primer fetch failed (%{public}@): %{public}@",
                   log: log, type: .error, reason, String(describing: error))
            // Still reload — the extension may still have a recent cache, or
            // may want to surface its own error UI.
        }

        if #available(iOS 14.0, *) {
            WidgetCenter.shared.reloadAllTimelines()
        }
    }
}
