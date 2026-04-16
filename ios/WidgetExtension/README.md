# SportsNotWidget extension

A WidgetKit app extension target containing:

1. Home Screen widget families: `.systemSmall`, `.systemMedium`, `.systemLarge`.
2. Lock Screen widgets: `.accessoryRectangular`, `.accessoryCircular`,
   `.accessoryInline`.
3. **Live Activity** (ActivityKit) for the Dynamic Island and Lock Screen,
   driven by APNs pushes from the `push-live-activity-updates` edge function.
4. A configuration intent (`FeaturedLeagueIntent`) that lets the user pick
   which of their linked share codes to show.

## Files

| File                          | Role                                                   |
| ----------------------------- | ------------------------------------------------------ |
| `SportsNotWidgetBundle.swift` | `@main` widget bundle entry point                      |
| `SnapshotTimelineProvider.swift` | `IntentTimelineProvider` fetching via `SnapshotAPI` |
| `SnapshotEntry.swift`         | `TimelineEntry` wrapping `WidgetSnapshot`              |
| `FeaturedLeagueIntent.swift`  | `AppIntent` widget configuration                       |
| `SportsNotWidget.swift`       | Home screen widget (small/medium/large)                |
| `SportsNotLockScreenWidget.swift` | Lock screen accessory families                     |
| `SportsNotLiveActivityWidget.swift` | ActivityKit Live Activity + Dynamic Island        |
| `Views/*.swift`               | SwiftUI views for each family                          |

## Xcode setup (one-time, macOS)

1. In Xcode: File → New → Target → Widget Extension, name
   `SportsNotWidget`. Include Live Activity support.
2. In Signing & Capabilities for this target:
   - Add App Group `group.com.sportsnot.widget`.
3. In Info.plist add user-defined build settings (populated from CI /
   `.env` at build time) for `SUPABASE_URL` and `SUPABASE_ANON_KEY`.
4. Add `SportsNotWidgetShared` as a local Swift package dependency (or
   link the source files directly to this target and the App target).
5. Replace the generated files with the ones in this directory.

## Push for Live Activities

The host app starts an activity with `pushType: .token`. We forward the
push token to `register-live-activity-token`. The server periodically
POSTs to APNs with:

```
apns-topic: com.sportsnot.app.push-type.liveactivity
apns-push-type: liveactivity
```

Bodies are `{ aps: { timestamp, event: "update"|"end", "content-state": ... } }`.
