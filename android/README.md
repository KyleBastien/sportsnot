# SportsNot Android

Capacitor-wrapped Android host for the SportsNot web app, plus native
Kotlin Home Screen widgets (small, medium, large) and Android 15+ Live
Update notifications for real-time playoff score tracking.

## One-time setup

The repository already contains the `android/` directory with Kotlin
sources for widgets, FCM, and the Capacitor bridge plugin. First checkout:

```bash
# From repo root
yarn install
yarn nx build @sportsnot/web
npx cap sync android
```

### Secrets

Create `android/app/secrets.properties` (gitignored) with your real
Supabase values:

```bash
cp android/app/secrets.properties.example android/app/secrets.properties
# Edit with your SUPABASE_URL and SUPABASE_ANON_KEY
```

### Firebase (FCM)

For push notifications, place a `google-services.json` file from the
Firebase console into `android/app/`. This file is gitignored. Without it
the build still succeeds (the google-services plugin is conditionally
applied), but FCM push will not work.

## Nx targets

All Android tasks are wrapped as Nx targets on `@sportsnot/android-app`:

| Command                                         | What it does                                      |
| ------------------------------------------------ | ------------------------------------------------- |
| `yarn nx sync-web @sportsnot/android-app`        | `nx build @sportsnot/web` then `cap sync android` |
| `yarn nx build @sportsnot/android-app`           | `gradlew assembleDebug`                           |
| `yarn nx run-android @sportsnot/android-app`     | `cap run android` on connected device / emulator  |
| `yarn nx assemble-release @sportsnot/android-app`| `gradlew bundleRelease` (AAB for Play Store)      |

These targets are **not** part of `nx affected` for the default CI gate —
they only run on the dedicated Android workflow (see
`.github/workflows/android-build.yml`).

## Widget architecture

Android widgets use `AppWidgetProvider` + `RemoteViews` (XML layouts),
unlike iOS which uses WidgetKit + SwiftUI. Three sizes are provided:

| Size   | Class                    | Layout             | Content                                |
| ------ | ------------------------ | ------------------ | -------------------------------------- |
| Small  | `SportsNotWidgetSmall`   | `widget_small.xml` | Single rotating player + fantasy pts   |
| Medium | `SportsNotWidgetMedium`  | `widget_medium.xml`| 3 players + 4 games + team total       |
| Large  | `SportsNotWidgetLarge`   | `widget_large.xml` | 6 games + 8 players + team total       |

Widgets fetch data from the `widget-league-snapshot` Supabase edge
function via `SnapshotAPI.kt`. Cached snapshots in SharedPreferences
provide offline fallback. Refresh: every 15 minutes via
`updatePeriodMillis`, plus on-demand via FCM data messages during live
games.

## Android 15+ Live Updates

On Android 15 (API 35) and above, the app supports Live Update
notifications — ongoing notifications pinned at the top of the shade
that update in real-time with live scores. These mirror iOS Live
Activities. On older devices, `isLiveActivitySupported()` returns false
and the feature gracefully degrades (users still have Home Screen widgets).

## FCM / Push notification secrets

Set these Supabase function secrets for dual-platform push support
(alongside existing APNs secrets for iOS):

- `FCM_PROJECT_ID` — Firebase project ID
- `FCM_SERVICE_ACCOUNT_JSON` — full JSON of a Firebase service account
  with `firebase.messaging` scope

```bash
supabase secrets set FCM_PROJECT_ID="your-project-id"
supabase secrets set --from-literal FCM_SERVICE_ACCOUNT_JSON="$(cat service-account.json)"
```

## CI / CD

- **PR builds**: `.github/workflows/android-build.yml` — triggers on PRs
  touching `android/`, `packages/widget-*`, `packages/web/`, or
  `capacitor.config.ts`. Builds a debug APK and uploads as artifact.
- **Releases**: `.github/workflows/android-release.yml` — manual dispatch,
  builds a signed release AAB and optionally uploads to Play Store
  internal track.

### Required GitHub secrets for CI

| Secret                            | Purpose                                     |
| --------------------------------- | ------------------------------------------- |
| `VITE_SUPABASE_URL`              | Supabase project URL                        |
| `VITE_SUPABASE_ANON_KEY`        | Supabase anon/publishable key               |
| `GOOGLE_SERVICES_JSON`           | Full `google-services.json` content          |
| `ANDROID_KEYSTORE_BASE64`       | Base64-encoded release signing keystore      |
| `ANDROID_KEYSTORE_PASSWORD`     | Keystore password                            |
| `ANDROID_KEY_ALIAS`             | Key alias in the keystore                    |
| `ANDROID_KEY_PASSWORD`          | Key password                                 |
| `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` | (Optional) Play Store upload service account |
