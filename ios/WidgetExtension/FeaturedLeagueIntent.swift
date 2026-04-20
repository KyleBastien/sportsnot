import AppIntents
import Foundation

/// Widget configuration intent with no user-editable parameters. The
/// featured league is controlled exclusively by the in-app "Feature on
/// widget" button, which writes `AppGroup.featuredShareCode`. We keep
/// this intent (rather than switching to `StaticConfiguration`) so the
/// existing `AppIntentTimelineProvider` wiring stays intact and any
/// previously-installed widget instances continue to render without
/// requiring the user to remove and re-add them.
@available(iOS 17.0, *)
struct FeaturedLeagueIntent: WidgetConfigurationIntent {
    static var title: LocalizedStringResource = "Featured League"
    static var description = IntentDescription("Set the featured league from inside SportsNot using Feature on widget.")

    init() {}
}
