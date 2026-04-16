import AppIntents
import Foundation

/// Per-widget-instance configuration: which of the share codes linked on
/// this device should this widget display.
@available(iOS 17.0, *)
struct FeaturedLeagueIntent: WidgetConfigurationIntent {
    static var title: LocalizedStringResource = "Featured League"
    static var description = IntentDescription("Choose which SportsNot league this widget follows.")

    @Parameter(title: "Share code")
    var shareCode: String?

    init() {}

    init(shareCode: String?) {
        self.shareCode = shareCode
    }
}
