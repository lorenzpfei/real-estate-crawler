export interface Env {
  SUPABASE_URL: string;
  SUPABASE_SERVICE_ROLE_KEY: string;
  API_KEY_CACHE: KVNamespace;
}

const KEY_CACHE_TTL_SECONDS = 60;
const DATA_CACHE_TTL_SECONDS = 300;
const MAX_LIMIT = 1000;

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/") {
      return new Response(JSON.stringify({ status: "ok" }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url.pathname !== "/listings") {
      return json({ error: "Not found" }, 404);
    }

    const apiKey = request.headers.get("X-API-Key");
    if (!apiKey) return json({ error: "Missing X-API-Key header" }, 401);

    const userId = await validateApiKey(apiKey, env);
    if (!userId) return json({ error: "Invalid API key" }, 403);

    // Data cache keyed by URL params only (same data for all authenticated users)
    const cacheKey = new Request(`https://cache${url.pathname}?${url.searchParams}`);
    const cache = caches.default;
    const cached = await cache.match(cacheKey);
    if (cached) return cached;

    const format = url.searchParams.get("format") === "csv" ? "csv" : "json";
    const supabaseParams = buildSupabaseParams(url.searchParams);

    const supabaseRes = await fetch(
      `${env.SUPABASE_URL}/rest/v1/apartments?${supabaseParams}`,
      {
        headers: {
          apikey: env.SUPABASE_SERVICE_ROLE_KEY,
          Authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}`,
          Accept: format === "csv" ? "text/csv" : "application/json",
          "Accept-Profile": "public",
        },
      }
    );

    if (!supabaseRes.ok) {
      const err = await supabaseRes.text();
      return json({ error: "Database error", detail: err }, 502);
    }

    const headers = new Headers({
      "Content-Type":
        format === "csv" ? "text/csv; charset=utf-8" : "application/json",
      "Cache-Control": `public, max-age=${DATA_CACHE_TTL_SECONDS}`,
      "Access-Control-Allow-Origin": "*",
    });
    if (format === "csv") {
      headers.set("Content-Disposition", 'attachment; filename="listings.csv"');
    }

    const response = new Response(supabaseRes.body, { status: 200, headers });
    ctx.waitUntil(cache.put(cacheKey, response.clone()));
    return response;
  },
};

async function validateApiKey(apiKey: string, env: Env): Promise<string | null> {
  const cached = await env.API_KEY_CACHE.get(`key:${apiKey}`);
  if (cached !== null) return cached === "" ? null : cached;

  const res = await fetch(
    `${env.SUPABASE_URL}/rest/v1/users?api_key=eq.${encodeURIComponent(apiKey)}&select=id&limit=1`,
    {
      headers: {
        apikey: env.SUPABASE_SERVICE_ROLE_KEY,
        Authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}`,
      },
    }
  );

  if (!res.ok) return null;

  const data = (await res.json()) as { id: number }[];
  const userId = data[0]?.id?.toString() ?? "";

  // Cache empty string for invalid keys so we don't hammer the DB
  await env.API_KEY_CACHE.put(`key:${apiKey}`, userId, {
    expirationTtl: KEY_CACHE_TTL_SECONDS,
  });

  return userId || null;
}

function buildSupabaseParams(searchParams: URLSearchParams): string {
  const p = new URLSearchParams();
  p.set("select", "*");
  p.set("order", "timestamp.desc");

  const listing_type = searchParams.get("listing_type");
  if (listing_type) p.set("listing_type", `eq.${listing_type}`);

  const portal = searchParams.get("portal");
  if (portal) p.set("portal", `eq.${portal}`);

  const city = searchParams.get("city");
  if (city) p.set("city", `ilike.*${city}*`);

  const zip_code = searchParams.get("zip_code");
  if (zip_code) p.set("zip_code", `eq.${zip_code}`);

  const min_rooms = searchParams.get("min_rooms");
  if (min_rooms) p.set("rooms", `gte.${min_rooms}`);

  const min_space = searchParams.get("min_space");
  if (min_space) p.set("living_space", `gte.${min_space}`);

  // max_price applies to cold_rent for rent listings, buy_price for buy
  const max_price = searchParams.get("max_price");
  if (max_price) {
    if (listing_type === "rent") {
      p.set("cold_rent", `lte.${max_price}`);
    } else if (listing_type === "buy") {
      p.set("buy_price", `lte.${max_price}`);
    }
    // without listing_type we skip max_price — ambiguous
  }

  const since = searchParams.get("since");
  if (since) p.set("timestamp", `gte.${since}`);

  const limit = Math.min(
    parseInt(searchParams.get("limit") ?? "500"),
    MAX_LIMIT
  );
  p.set("limit", String(limit));

  const offset = searchParams.get("offset") ?? "0";
  p.set("offset", offset);

  return p.toString();
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
    },
  });
}
