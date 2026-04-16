import Capacitor
import UIKit

/// Custom CAPBridgeViewController subclass that registers plugins compiled
/// directly into the App target (i.e. not shipped as a CocoaPod). Capacitor
/// v6 only auto-discovers plugins from installed pods, so local plugins must
/// be registered via `bridge?.registerPluginInstance(...)`.
class MainViewController: CAPBridgeViewController {
    override open func capacitorDidLoad() {
        bridge?.registerPluginInstance(WidgetBridgePlugin())
    }
}
