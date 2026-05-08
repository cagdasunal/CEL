# Blog Image Optimization — Webhook Setup (One-Time)

The `blog-image-optimization` workflow has 3 trigger modes:

1. **Cron** (`0 11 * * *` UTC) — fires nightly, processes ALL Blog Posts. No setup required.
2. **Manual** (`workflow_dispatch`) — fires on demand from GitHub Actions UI. No setup required. Optionally accepts a `posts` input (comma-separated slugs) to scope to specific posts.
3. **Webhook** (`repository_dispatch`) — fires within ~30s when a Blog Post is published in Webflow. **Requires the setup below.**

Each mode runs the same optimizer with `--apply --auto-publish` (item-level publish, drafts preserved).

---

## Webhook setup — Webflow → relay → GitHub

The webhook chain is: Webflow webhook → HTTPS relay endpoint → GitHub `/repos/{owner}/{repo}/dispatches` API → workflow runs.

You need ONE of these relay options:

### Option A — Cloudflare Worker (recommended; you already use Cloudflare)

1. Generate a GitHub Personal Access Token with `repo` scope:
   - https://github.com/settings/tokens/new — give it `repo` permission, copy the token (`ghp_...`).
2. Cloudflare Dashboard → **Workers & Pages → Create Worker** — name it `blog-publish-relay`.
3. Paste the Worker code below. Replace `OWNER/REPO` with `cagdasunal/CEL` (or wherever this workflow lives).
4. Click **Settings → Variables → Add encrypted secret**:
   - Name: `GH_TOKEN`, Value: the `ghp_...` from step 1.
   - Name: `WEBFLOW_WEBHOOK_SECRET`, Value: a long random string (you'll use the same one in step 6).
5. Deploy. The Worker URL will look like `https://blog-publish-relay.<your-account>.workers.dev`.
6. In Webflow:
   - **Site Settings → Integrations → Webhooks → Add webhook**
   - Trigger: **`collection_item_published`**
   - URL: the Worker URL from step 5
   - Filter: Collection = **Blog - Posts** (collection id `667453c576e8d35c454ccaae`)
   - Save → Webflow will show the secret it generates. **Copy that secret** and paste it back into the Cloudflare Worker's `WEBFLOW_WEBHOOK_SECRET` (step 4) — replacing the random string with the real one.
7. Test: in Webflow CMS, edit a Blog Post and click **Publish** (CMS-level publish on the item, not site-publish). Within ~30 seconds, GitHub Actions should show a new run of `blog-image-optimization` with the post's slug as filter.

```javascript
// blog-publish-relay (Cloudflare Worker) — receives Webflow webhook,
// validates HMAC, forwards to GitHub repository_dispatch.
//
// Env vars (Worker secrets):
//   GH_TOKEN                 — GitHub PAT with repo scope
//   WEBFLOW_WEBHOOK_SECRET   — secret Webflow gave you when creating the webhook
//   GH_OWNER (default: cagdasunal)
//   GH_REPO  (default: CEL)

export default {
  async fetch(request, env) {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const sig = request.headers.get("x-webflow-signature") || "";
    const ts  = request.headers.get("x-webflow-timestamp") || "";
    const raw = await request.text();

    // HMAC-SHA-256 over `${ts}:${raw}` with the shared secret.
    const enc = new TextEncoder();
    const key = await crypto.subtle.importKey(
      "raw", enc.encode(env.WEBFLOW_WEBHOOK_SECRET),
      { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
    );
    const computed = await crypto.subtle.sign("HMAC", key, enc.encode(`${ts}:${raw}`));
    const computedHex = [...new Uint8Array(computed)]
      .map(b => b.toString(16).padStart(2, "0")).join("");
    if (computedHex !== sig) return new Response("Invalid signature", { status: 401 });

    let payload;
    try { payload = JSON.parse(raw); }
    catch { return new Response("Invalid JSON", { status: 400 }); }

    // Webflow's collection_item_published payload contains the item slug.
    const slug = payload?.payload?.slug || payload?.slug;
    if (!slug) return new Response("No slug in payload", { status: 400 });

    const owner = env.GH_OWNER || "cagdasunal";
    const repo  = env.GH_REPO  || "CEL";
    const dispatchUrl = `https://api.github.com/repos/${owner}/${repo}/dispatches`;

    const ghResp = await fetch(dispatchUrl, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GH_TOKEN}`,
        Accept: "application/vnd.github+json",
        "User-Agent": "blog-publish-relay/1.0",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        event_type: "webflow_blog_published",
        client_payload: { slug },
      }),
    });

    if (!ghResp.ok) {
      const txt = await ghResp.text();
      return new Response(`GitHub dispatch failed: ${ghResp.status} ${txt}`, { status: 502 });
    }
    return new Response(JSON.stringify({ ok: true, slug }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

### Option B — Reuse the existing offers dispatch worker

If your existing `OFFERS_DISPATCH_PROXY_URL` Cloudflare Worker can be extended with a `kind: "blog_published"` action, that's the cheapest. Forward the slug to GitHub's `/dispatches` endpoint with `event_type: webflow_blog_published`. Same security model as the offers flow.

### Option C — Skip webhooks; rely on cron

If you're fine with up-to-24h latency for new posts, do nothing. The nightly cron at 11:00 UTC catches anything published in the past day. The optimizer is idempotent — already-AVIF posts are skipped.

If 24h is too slow but you don't want to set up a Worker, change the cron to `0 */6 * * *` (every 6 hours) — max 6h latency, 4× the GitHub Actions minutes per day, still fits comfortably under free quota.

---

## What `--auto-publish` does (and what it doesn't)

When the workflow processes a published post, it:

1. PATCHes the `post-body` field with new AVIF URLs (CMS staged state).
2. Calls `POST /v2/collections/{id}/items/publish` with that one item ID — propagates the staged state to live.

It does **NOT** call `data_sites_tool.publish_site` (that endpoint is banned by `rules/workflow.md §7.1` — only humans publish sites).

The safeguard inside the optimizer:
```python
was_published_before = (
    bool(item.get("lastPublished"))
    and item.get("isDraft") is False
    and item.get("isArchived") is False
)
if apply and patched and auto_publish and was_published_before:
    publish_collection_items(token, [post_id])
```

A post that has never been published, OR is currently a draft, OR is archived → optimizer PATCHes the staged content and stops. Drafts stay drafts. Manual user publish required to make them live.

---

## Verify the chain end-to-end

After completing Option A:

```bash
# 1. Verify webhook is listed in Webflow
#    Site Settings → Integrations → Webhooks should show 1 entry

# 2. Trigger a publish in Webflow
#    Edit any Blog Post → Publish (CMS-level on the item, not site-publish)

# 3. Within 30s, check GitHub Actions
gh workflow view blog-image-optimization --ref main
# Or visit: https://github.com/cagdasunal/CEL/actions/workflows/blog-image-optimization.yml

# 4. Check the run logs for "Filter: webhook slug=<your-post-slug>"
```

If the chain breaks, Cloudflare Worker → Logs tab shows the request + response (success/error/signature mismatch).
