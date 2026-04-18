# SportsNotWidgetShared

A Swift package (or framework — see the Xcode setup note in `../WidgetExtension/README.md`)
containing code shared between the host app, the WidgetKit extension, and
the Live Activity extension.

Two responsibilities:

1. **Codable models** for the `widget-league-snapshot` edge function
   payload (keep these in sync with `packages/widget-api/src/lib/types.ts`).
2. **Shared state** (via App Group `UserDefaults` key
   `group.com.sportsnot.widget`):
   - `featuredShareCode: String?` — the league the widget follows.
   - `lastSnapshot: Data?` — last successfully fetched snapshot, used for
     offline fallback.

3. **Network client** (`SnapshotAPI`) — hits
   `{SUPABASE_URL}/functions/v1/widget-league-snapshot?shareCode=...` with
   the anon key. `SUPABASE_URL` + `SUPABASE_ANON_KEY` are read from the
   widget target's `Info.plist` (populated at build time from env vars by
   an Xcode build phase so the key is never checked in).
