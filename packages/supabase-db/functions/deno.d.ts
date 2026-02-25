// Type declarations for Deno runtime used by Supabase Edge Functions.
// Supabase deploys these functions in a real Deno runtime where these
// globals are natively available. This file lets VS Code resolve them.

declare namespace Deno {
  function serve(handler: (req: Request) => Response | Promise<Response>): void;

  const env: {
    get(key: string): string | undefined;
  };
}
