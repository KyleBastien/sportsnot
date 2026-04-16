import SwiftUI
import WidgetKit

@available(iOS 17.0, *)
struct SportsNotHomeWidget: Widget {
    let kind = "SportsNotHomeWidget"

    var body: some WidgetConfiguration {
        AppIntentConfiguration(
            kind: kind,
            intent: FeaturedLeagueIntent.self,
            provider: SnapshotTimelineProvider()
        ) { entry in
            SportsNotHomeWidgetView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("SportsNot")
        .description("Today's playoff games and your drafted players' fantasy points.")
        .supportedFamilies([.systemSmall, .systemMedium, .systemLarge])
    }
}

@available(iOS 17.0, *)
struct SportsNotHomeWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let entry: SnapshotEntry

    var body: some View {
        switch family {
        case .systemSmall:
            SmallFamilyView(entry: entry)
        case .systemMedium:
            MediumFamilyView(entry: entry)
        default:
            LargeFamilyView(entry: entry)
        }
    }
}
