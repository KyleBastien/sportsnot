// Tiny PostgREST client shared across widget edge functions.

export interface PgConfig {
  url: string;
  key: string;
}

export function pgHeaders(apiKey: string): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    apikey: apiKey,
    Authorization: `Bearer ${apiKey}`,
  };
}

export async function pgSelect<T>(
  cfg: PgConfig,
  table: string,
  params: string
): Promise<T[]> {
  const resp = await fetch(`${cfg.url}/rest/v1/${table}?${params}`, {
    headers: pgHeaders(cfg.key),
  });
  if (!resp.ok) return [];
  return (await resp.json()) as T[];
}

export async function pgInsert(
  cfg: PgConfig,
  table: string,
  body: unknown,
  prefer: string = 'return=minimal'
): Promise<boolean> {
  const resp = await fetch(`${cfg.url}/rest/v1/${table}`, {
    method: 'POST',
    headers: { ...pgHeaders(cfg.key), Prefer: prefer },
    body: JSON.stringify(body),
  });
  return resp.ok;
}

export async function pgUpsert(
  cfg: PgConfig,
  table: string,
  onConflict: string,
  body: unknown
): Promise<boolean> {
  const resp = await fetch(
    `${cfg.url}/rest/v1/${table}?on_conflict=${onConflict}`,
    {
      method: 'POST',
      headers: {
        ...pgHeaders(cfg.key),
        Prefer: 'resolution=merge-duplicates,return=minimal',
      },
      body: JSON.stringify(body),
    }
  );
  return resp.ok;
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json',
      // Widget-friendly: widgets refresh from arbitrary hosts (Xcode Simulator
      // origin, App Group file URLs). Since these endpoints are public
      // read-only (or token-registration), CORS wildcard is safe.
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers':
        'authorization, x-client-info, apikey, content-type',
    },
  });
}

/** Simple sha256 hex helper using Web Crypto (available in Deno). */
export async function sha256Hex(input: string): Promise<string> {
  const buf = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest('SHA-256', buf);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}
