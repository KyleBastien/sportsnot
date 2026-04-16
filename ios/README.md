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
npx cap add ios   # generates ios/App/* from capacitor.config.ts
```

then copy the files in [`WidgetExtension/`](./WidgetExtension/) and
[`SportsNotWidgetShared/`](./SportsNotWidgetShared/) into the Xcode
project and enable the App Group `group.com.sportsnot.widget` on both
the App and Widget targets. See [`WidgetExtension/README.md`](./WidgetExtension/README.md)
for the step-by-step.

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
