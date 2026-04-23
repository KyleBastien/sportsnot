import type { RegisterLiveActivityTokenRequest, WidgetSnapshot } from './types';

export interface WidgetApiClientOptions {
  /** Supabase project URL, e.g. https://<ref>.supabase.co */
  supabaseUrl: string;
  /** Supabase anon/publishable key. */
  anonKey: string;
  /** Optional fetch override (for tests or native shims). */
  fetch?: typeof fetch;
}

export class WidgetApiClient {
  private readonly fetchImpl: typeof fetch;

  constructor(private readonly opts: WidgetApiClientOptions) {
    this.fetchImpl =
      opts.fetch ?? ((input, init) => globalThis.fetch(input, init));
  }

  private widgetDateString(): string {
    return new Intl.DateTimeFormat('en-CA', {
      timeZone: 'America/New_York',
    }).format(new Date());
  }

  private fnUrl(name: string): string {
    return `${this.opts.supabaseUrl}/functions/v1/${name}`;
  }

  async getSnapshot(shareCode: string, date?: string): Promise<WidgetSnapshot> {
    const qs = new URLSearchParams({
      shareCode,
      date: date ?? this.widgetDateString(),
    });
    const resp = await this.fetchImpl(
      `${this.fnUrl('widget-league-snapshot')}?${qs.toString()}`,
      {
        // Public read-only endpoint. Keep GET request "simple" so Capacitor
        // WebView does not send a CORS preflight that Supabase may reject.
        headers: { Accept: 'application/json' },
      }
    );
    if (!resp.ok) {
      throw new Error(
        `widget-league-snapshot failed: ${resp.status} ${resp.statusText}`
      );
    }
    return (await resp.json()) as WidgetSnapshot;
  }

  async registerLiveActivityToken(
    req: RegisterLiveActivityTokenRequest
  ): Promise<void> {
    const resp = await this.fetchImpl(
      this.fnUrl('register-live-activity-token'),
      {
        method: 'POST',
        // Public endpoint. Send plain-text JSON body to keep request
        // "simple" and avoid Capacitor WebView CORS preflights.
        headers: {
          Accept: 'application/json',
          'Content-Type': 'text/plain',
        },
        body: JSON.stringify(req),
      }
    );
    if (!resp.ok) {
      throw new Error(
        `register-live-activity-token failed: ${resp.status} ${resp.statusText}`
      );
    }
  }
}
