import Foundation
import WidgetKit

struct SnapshotEntry: TimelineEntry {
    let date: Date
    let snapshot: WidgetSnapshot?
    let staleFromCache: Bool
    let shareCode: String?
    let errorMessage: String?
    /// The current user's `team_name` within the featured league, used to
    /// compute "your team" totals against the league-wide snapshot.
    let myTeamName: String?
    // Index into the paginated player list for rotating widget views.
    // Provider emits multiple entries with increasing pageIndex so the
    // system cycles through pages without re-fetching the snapshot.
    let pageIndex: Int
    let totalPages: Int

    init(
        date: Date,
        snapshot: WidgetSnapshot?,
        staleFromCache: Bool,
        shareCode: String?,
        errorMessage: String?,
        myTeamName: String? = nil,
        pageIndex: Int = 0,
        totalPages: Int = 1
    ) {
        self.date = date
        self.snapshot = snapshot
        self.staleFromCache = staleFromCache
        self.shareCode = shareCode
        self.errorMessage = errorMessage
        self.myTeamName = myTeamName
        self.pageIndex = pageIndex
        self.totalPages = totalPages
    }
}

extension SnapshotEntry {
    static let placeholder = SnapshotEntry(
        date: .now,
        snapshot: nil,
        staleFromCache: false,
        shareCode: nil,
        errorMessage: nil
    )
}
