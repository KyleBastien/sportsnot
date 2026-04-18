import SwiftUI
import WidgetKit

@main
struct SportsNotWidgetBundle: WidgetBundle {
    var body: some Widget {
        SportsNotHomeWidget()
        SportsNotLockScreenWidget()
        if #available(iOS 16.2, *) {
            SportsNotLiveActivityWidget()
        }
    }
}
