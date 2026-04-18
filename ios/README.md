# SportsNot iOS

Capacitor-wrapped iOS host for the SportsNot web app, plus the
`SportsNotWidget` WidgetKit extension (Home Screen widgets, Lock Screen
widgets, Dynamic Island, and ActivityKit Live Activities).

## One-time setup (macOS only)

`npx cap add ios` needs to be run on macOS with CocoaPods installed. The
repository already contains this directory with the Swift sources for the
widget extension and `SportsNotWidgetShared` package, so the flow is:

```bash
# From repo root, on macOS
yarn install
yarn nx build @sportsnot/web
yarn nx sync-web @sportsnot/ios-app   # runs `npx cap sync ios`
yarn nx pod-install @sportsnot/ios-app
```

If the `ios/App` Xcode workspace doesn't exist yet (first checkout on a
new macOS dev box), run:

```bash
npx cap add ios                                    # generates ios/App/*
ruby scripts/ios/setup-xcode-project.rb            # wires SportsNotWidget target
```

The setup script (idempotent) adds the `SportsNotWidget` Widget Extension
target, wires Swift sources from `ios/WidgetExtension/`,
`ios/SportsNotWidgetShared/` (shared with App), and
`ios/CapacitorPlugins/WidgetBridge/` (App only), creates entitlements
files, enables App Groups + Push Notifications, and embeds the widget
in the App bundle. Requires the `xcodeproj` gem:

```bash
gem install --user-install xcodeproj
```

## Remaining manual steps

1. **Signing team** — open `ios/App/App.xcworkspace`, select a Team in
   Signing & Capabilities for both the `App` and `SportsNotWidget`
   targets (required for device builds; Simulator works without).
2. **APNs secrets** — for the `push-live-activity-updates` edge function
   to send Live Activity pushes, set these on the Supabase project
   (`supabase secrets set …`):
   - `APNS_KEY_ID` — 10-char key id from Apple Developer portal
   - `APNS_TEAM_ID` — Apple developer team id
   - `APNS_BUNDLE_ID` — `com.sportsnot.app`
   - `APNS_ENV` — `sandbox` (TestFlight/Simulator) or `production`
   - `APNS_P8` — contents of the `AuthKey_XXXXXX.p8` file
     (`supabase secrets set --from-literal APNS_P8="$(cat AuthKey_X.p8)"`)
3. **Push cron** — in the Supabase dashboard, Edge Functions →
   `push-live-activity-updates` → Cron, add a schedule (e.g. `* * * * *`
   every minute during playoff games).
4. **SUPABASE_URL / SUPABASE_ANON_KEY** — both `App/Info.plist` and
   `SportsNotWidget/Info.plist` read `$(SUPABASE_URL)` and
   `$(SUPABASE_ANON_KEY)` from build settings. Set them in Xcode's
   build settings per target, or via a CI build phase that substitutes
   env vars.

## Nx targets

All iOS tasks are wrapped as Nx targets on `@sportsnot/ios-app` so the
CLI matches the rest of the monorepo:

| Command                                   | What it does                                  |
| ----------------------------------------- | --------------------------------------------- |
| `yarn nx sync-web @sportsnot/ios-app`     | `nx build @sportsnot/web` then `cap sync ios` |
| `yarn nx build @sportsnot/ios-app`        | `xcodebuild build` for the App scheme         |
| `yarn nx build-widget @sportsnot/ios-app` | `xcodebuild build` for the Widget scheme      |
| `yarn nx run-ios @sportsnot/ios-app`      | `cap run ios` on the default simulator        |
| `yarn nx archive @sportsnot/ios-app`      | `xcodebuild archive` for TestFlight builds    |
| `yarn nx pod-install @sportsnot/ios-app`  | `cap update ios` + `pod install`              |

These targets are **not** part of `nx affected` for Windows/Linux CI —
they only run on the dedicated macOS workflow (see `.github/workflows/ios-build.yml`).

## APNs / Live Activity secrets

Set these Supabase function secrets before deploying
`push-live-activity-updates`:

- `APNS_KEY_ID` — 10-character key id from developer.apple.com
- `APNS_TEAM_ID` — 10-character team id
- `APNS_P8` — the raw `.p8` contents (including BEGIN/END lines)
- `APNS_BUNDLE_ID` — defaults to `com.sportsnot.app`
- `APNS_ENV` — `sandbox` for TestFlight/simulator, `production` for App Store
