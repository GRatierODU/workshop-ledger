// Starts the "Update Workshop stats" GitHub workflow for the dashboard's Reload button.
// The GitHub token lives only in this Vercel project's GITHUB_TOKEN environment variable.
const REPO = "GRatierODU/workshop-ledger";
const WORKFLOW = "update.yml";
const ORIGINS = ["https://gratierodu.github.io", "http://localhost:8766"];
const COOLDOWN_MS = 90 * 1000; // ignore presses while a run just started or is still going

async function gh(path, init = {}) {
  return fetch(`https://api.github.com/repos/${REPO}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${process.env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "workshop-ledger-refresh",
      ...(init.headers || {}),
    },
  });
}

export default async function handler(req, res) {
  const origin = req.headers.origin;
  if (ORIGINS.includes(origin)) res.setHeader("Access-Control-Allow-Origin", origin);
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  res.setHeader("Cache-Control", "no-store");
  if (req.method === "OPTIONS") return res.status(204).end();
  if (req.method !== "POST") return res.status(405).json({ status: "error", message: "Use POST" });
  if (!process.env.GITHUB_TOKEN) return res.status(503).json({ status: "error", message: "Refresh is not set up yet" });

  try {
    const runs = await gh(`/actions/workflows/${WORKFLOW}/runs?per_page=3`);
    if (runs.ok) {
      const { workflow_runs = [] } = await runs.json();
      const busy = workflow_runs.find(
        (r) => r.status !== "completed" || Date.now() - Date.parse(r.created_at) < COOLDOWN_MS
      );
      if (busy) return res.status(200).json({ status: "running", since: busy.created_at });
    }
    const go = await gh(`/actions/workflows/${WORKFLOW}/dispatches`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ref: "main" }),
    });
    if (go.status === 204) return res.status(200).json({ status: "started" });
    return res.status(502).json({ status: "error", message: `GitHub answered ${go.status}` });
  } catch (e) {
    return res.status(502).json({ status: "error", message: "Could not reach GitHub" });
  }
}
