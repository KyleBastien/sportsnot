import SwiftUI
import WidgetKit

@available(iOS 17.0, *)
struct SportsNotLockScreenWidget: Widget {
    let kind = "SportsNotLockScreenWidget"

    var body: some WidgetConfiguration {
        AppIntentConfiguration(
            kind: kind,
            intent: FeaturedLeagueIntent.self,
            provider: SnapshotTimelineProvider()
        ) { entry in
            LockScreenView(entry: entry)
        }
        .configurationDisplayName("SportsNot Lock Screen")
        .description("Glanceable fantasy total on the lock screen.")
        .supportedFamilies([.accessoryRectangular, .accessoryCircular, .accessoryInline])
    }
}

@available(iOS 17.0, *)
struct LockScreenView: View {
    @Environment(\.widgetFamily) private var family
    let entry: SnapshotEntry

    var body: some View {
        switch family {
        case .accessoryRectangular:
            AccessoryRectangularView(entry: entry)
        case .accessoryCircular:
            AccessoryCircularView(entry: entry)
        case .accessoryInline:
            AccessoryInlineView(entry: entry)
        default:
            EmptyView()
        }
    }
}
