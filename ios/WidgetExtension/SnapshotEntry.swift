import Foundation
import WidgetKit

struct SnapshotEntry: TimelineEntry {
    let date: Date
    let snapshot: WidgetSnapshot?
    let staleFromCache: Bool
    let shareCode: String?
    let errorMessage: String?
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
