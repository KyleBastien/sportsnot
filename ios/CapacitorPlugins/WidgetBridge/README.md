# WidgetBridge Capacitor plugin

Native side of the `@sportsnot/widget-bridge` plugin. Exposes the Swift
`WidgetBridgePlugin` to JavaScript as `Capacitor.Plugins.WidgetBridge`.

## Files

- `WidgetBridgePlugin.swift` — the `CAPPlugin` implementation with
  `setFeaturedLeague`, `getFeaturedLeague`, `startLiveActivity`,
  `endLiveActivity`, `isLiveActivitySupported`.
- `WidgetBridge.swift` — required Capacitor registration shim.

## Xcode wiring (one-time)

1. Drag `ios/CapacitorPlugins/WidgetBridge/` into the `App` target as
   a group reference (Create groups, not folder references).
2. Drag `ios/SportsNotWidgetShared/` into **both** the `App` target
   and the `SportsNotWidget` extension target.
3. Enable App Group `group.com.sportsnot.widget` on both targets
   (Signing & Capabilities → + Capability → App Groups).
4. Enable "Push Notifications" capability on the `App` target.

The JS side of the plugin lives in `packages/widget-bridge/`.
