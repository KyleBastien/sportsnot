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
    this.fetchImpl = opts.fetch ?? fetch;
  }

  private localDateString(): string {
    const now = new Date();
    const year = String(now.getFullYear());
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  private fnUrl(name: string): string {
    return `${this.opts.supabaseUrl}/functions/v1/${name}`;
  }

  private headers(): Record<string, string> {
    return {
      'Content-Type': 'application/json',
      apikey: this.opts.anonKey,
      Authorization: `Bearer ${this.opts.anonKey}`,
    };
  }

  async getSnapshot(shareCode: string, date?: string): Promise<WidgetSnapshot> {
    const qs = new URLSearchParams({
      shareCode,
      date: date ?? this.localDateString(),
    });
    const resp = await this.fetchImpl(
      `${this.fnUrl('widget-league-snapshot')}?${qs.toString()}`,
      { headers: this.headers() }
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
        headers: this.headers(),
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
