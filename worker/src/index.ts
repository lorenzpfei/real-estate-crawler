export interface Env {
  SUPABASE_URL: string;
  SUPABASE_SERVICE_ROLE_KEY: string;
  API_KEY_CACHE: KVNamespace;
}

const KEY_CACHE_TTL_SECONDS = 60;
const DATA_CACHE_TTL_SECONDS = 300;
const SUPABASE_PAGE_SIZE = 1000;

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/") {
      return json({ status: "ok" });
    }

    // Auth required for all other routes
    const apiKey = request.headers.get("X-API-Key");
    if (!apiKey) return json({ error: "Missing X-API-Key header" }, 401);

    const userId = await validateApiKey(apiKey, env);
    if (!userId) return json({ error: "Invalid API key" }, 403);

    // PATCH /listings/:id/sent  or  /listings/:id/seen
    const patchMatch = url.pathname.match(/^\/listings\/(.+)\/(sent|seen)$/);
    if (request.method === "PATCH" && patchMatch) {
      return handleStatusUpdate(patchMatch[1], patchMatch[2] as "sent" | "seen", userId, env);
    }

    if (url.pathname !== "/listings") {
      return json({ error: "Not found" }, 404);
    }

    if (request.method !== "GET") {
      return json({ error: "Method not allowed" }, 405);
    }

    // GET /listings
    const skipCache = url.searchParams.get("unsent") === "true";
    const cacheKey = new Request(`https://cache${url.pathname}?${url.searchParams}&_u=${userId}`);
    const cache = caches.default;
    if (!skipCache) {
      const cached = await cache.match(cacheKey);
      if (cached) return cached;
    }

    const format = url.searchParams.get("format") === "csv" ? "csv" : "json";
    const rawLimit = url.searchParams.has("limit") ? parseInt(url.searchParams.get("limit")!) : null;
    const fetchAll = rawLimit === 0 || (rawLimit === null && format === "csv");
    const requestedLimit = fetchAll ? Infinity : (rawLimit ?? 500);
    const startOffset = parseInt(url.searchParams.get("offset") ?? "0");

    // Resolve unsent filter: fetch sent listing IDs for this user
    let excludeIds: string[] = [];
    if (url.searchParams.get("unsent") === "true") {
      excludeIds = await getSentIds(userId, env);
    }

    // Fetch first page
    const firstParams = buildSupabaseParams(url.searchParams, startOffset, Math.min(requestedLimit, SUPABASE_PAGE_SIZE), excludeIds);
    const firstRes = await fetch(`${env.SUPABASE_URL}/rest/v1/apartments?${firstParams}`, sbInit(env));
    if (!firstRes.ok) {
      return json({ error: "Database error", detail: await firstRes.text() }, 502);
    }

    let allRows = (await firstRes.json()) as Record<string, unknown>[];

    // Paginate if needed
    let offset = startOffset + SUPABASE_PAGE_SIZE;
    while (allRows.length === offset - startOffset && allRows.length < requestedLimit) {
      const remaining = fetchAll ? SUPABASE_PAGE_SIZE : Math.min(requestedLimit - allRows.length, SUPABASE_PAGE_SIZE);
      const nextParams = buildSupabaseParams(url.searchParams, offset, remaining, excludeIds);
      const nextRes = await fetch(`${env.SUPABASE_URL}/rest/v1/apartments?${nextParams}`, sbInit(env));
      if (!nextRes.ok) break;
      const nextRows = (await nextRes.json()) as Record<string, unknown>[];
      allRows = allRows.concat(nextRows);
      if (nextRows.length < SUPABASE_PAGE_SIZE) break;
      offset += SUPABASE_PAGE_SIZE;
    }

    const transformed = allRows.map(transformRow);

    let body: string;
    let contentType: string;
    if (format === "csv") {
      body = toCSV(transformed);
      contentType = "text/csv; charset=utf-8";
    } else {
      body = JSON.stringify(transformed);
      contentType = "application/json";
    }

    const headers = new Headers({
      "Content-Type": contentType,
      "Cache-Control": `public, max-age=${DATA_CACHE_TTL_SECONDS}`,
      "Access-Control-Allow-Origin": "*",
    });
    if (format === "csv") {
      headers.set("Content-Disposition", 'attachment; filename="listings.csv"');
    }

    const response = new Response(body, { status: 200, headers });
    if (!skipCache) ctx.waitUntil(cache.put(cacheKey, response.clone()));
    return response;
  },
};

async function handleStatusUpdate(
  listingId: string,
  action: "sent" | "seen",
  userId: string,
  env: Env
): Promise<Response> {
  const now = new Date().toISOString();

  if (action === "sent") {
    // Upsert: create row with sent_at (and seen_at) set
    const res = await fetch(`${env.SUPABASE_URL}/rest/v1/listing_user_status`, {
      method: "POST",
      headers: {
        ...sbHeaders(env),
        "Content-Type": "application/json",
        Prefer: "resolution=merge-duplicates",
      },
      body: JSON.stringify({
        listing_id: listingId,
        user_id: parseInt(userId),
        sent_at: now,
        seen_at: now,
      }),
    });
    if (!res.ok) return json({ error: "Database error", detail: await res.text() }, 502);
    return json({ ok: true });
  }

  // seen: upsert row with seen_at (marks as processed without counting as sent)
  const res = await fetch(`${env.SUPABASE_URL}/rest/v1/listing_user_status`, {
    method: "POST",
    headers: {
      ...sbHeaders(env),
      "Content-Type": "application/json",
      Prefer: "resolution=merge-duplicates",
    },
    body: JSON.stringify({
      listing_id: listingId,
      user_id: parseInt(userId),
      seen_at: now,
    }),
  });
  if (!res.ok) return json({ error: "Database error", detail: await res.text() }, 502);
  return json({ ok: true });
}

async function getSentIds(userId: string, env: Env): Promise<string[]> {
  const res = await fetch(
    `${env.SUPABASE_URL}/rest/v1/listing_user_status?user_id=eq.${userId}&seen_at=not.is.null&select=listing_id&limit=5000`,
    sbInit(env)
  );
  if (!res.ok) return [];
  const rows = (await res.json()) as { listing_id: string }[];
  return rows.map((r) => r.listing_id);
}

function sbHeaders(env: Env): Record<string, string> {
  return {
    apikey: env.SUPABASE_SERVICE_ROLE_KEY,
    Authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}`,
    Accept: "application/json",
    "Accept-Profile": "public",
  };
}

function sbInit(env: Env): RequestInit {
  return { headers: sbHeaders(env) };
}

async function validateApiKey(apiKey: string, env: Env): Promise<string | null> {
  const cached = await env.API_KEY_CACHE.get(`key:${apiKey}`);
  if (cached !== null) return cached === "" ? null : cached;

  const res = await fetch(
    `${env.SUPABASE_URL}/rest/v1/users?api_key=eq.${encodeURIComponent(apiKey)}&select=id&limit=1`,
    sbInit(env)
  );
  if (!res.ok) return null;

  const data = (await res.json()) as { id: number }[];
  const userId = data[0]?.id?.toString() ?? "";

  await env.API_KEY_CACHE.put(`key:${apiKey}`, userId, { expirationTtl: KEY_CACHE_TTL_SECONDS });
  return userId || null;
}

function buildSupabaseParams(
  searchParams: URLSearchParams,
  offset: number,
  limit: number,
  excludeIds: string[] = []
): string {
  const p = new URLSearchParams();
  p.set("select", "*");
  const sortDir = searchParams.get("sort") === "asc" ? "asc" : "desc";
  p.set("order", `timestamp.${sortDir}`);

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

  const max_price = searchParams.get("max_price");
  if (max_price) {
    if (listing_type === "rent") p.set("cold_rent", `lte.${max_price}`);
    else if (listing_type === "buy") p.set("buy_price", `lte.${max_price}`);
  }

  const since = searchParams.get("since");
  if (since) p.set("timestamp", `gte.${since}`);

  if (excludeIds.length > 0) {
    p.set("id", `not.in.(${excludeIds.join(",")})`);
  }

  p.set("limit", String(limit));
  p.set("offset", String(offset));

  return p.toString();
}

function stripHtml(s: unknown): string {
  if (typeof s !== "string") return "";
  return s.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}

function parseImages(val: unknown): string {
  if (!val) return "";
  const s = String(val);
  if (s.startsWith("{") && s.endsWith("}")) {
    return s.slice(1, -1).split(",").filter(Boolean).join(",");
  }
  return s;
}

function transformRow(row: Record<string, unknown>): Record<string, unknown> {
  return {
    ...row,
    description: stripHtml(row.description),
    equipment: stripHtml(row.equipment),
    location_description: stripHtml(row.location_description),
    other_info: stripHtml(row.other_info),
    images: parseImages(row.images),
  };
}

function csvCell(val: unknown): string {
  if (val === null || val === undefined) return "";
  const s = String(val);
  if (s.includes('"') || s.includes(",") || s.includes("\n") || s.includes("\r")) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

function toCSV(rows: Record<string, unknown>[]): string {
  if (rows.length === 0) return "";
  const cols = Object.keys(rows[0]);
  const header = cols.join(",");
  const lines = rows.map((row) => cols.map((c) => csvCell(row[c])).join(","));
  return [header, ...lines].join("\r\n");
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
