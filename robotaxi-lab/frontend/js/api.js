// Thin wrapper over the backend HTTP API.

async function request(method, url, body) {
  let res;
  try {
    res = await fetch(url, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error("Can't reach the lab server. Check that `python run.py` is still running.");
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON error body */
  }
  if (!res.ok) {
    let detail = data && data.detail;
    if (Array.isArray(detail)) detail = detail.map((d) => `${(d.loc || []).slice(-1)[0]}: ${d.msg}`).join("; ");
    throw new Error(detail || `Request failed (${res.status}).`);
  }
  return data;
}

export const api = {
  meta: () => request("GET", "/api/meta"),
  validate: (h) => request("POST", "/api/heuristics/validate", h),
  randomDay: (params) => request("POST", "/api/instance/random", params),
  compare: (body) => request("POST", "/api/compare", body),
  startJob: (kind, body) => request("POST", `/api/jobs/${kind}`, body),
  job: (id) => request("GET", `/api/jobs/${id}`),
  cancel: (id) => request("POST", `/api/jobs/${id}/cancel`),
};

// Poll a background job until it finishes. onProgress(done, total, message).
export async function waitForJob(id, onProgress) {
  for (;;) {
    const job = await api.job(id);
    onProgress(job.done, job.total, job.message);
    if (job.status === "done") return job.result;
    if (job.status === "cancelled") return job.result ? { ...job.result, cancelled: true } : null;
    if (job.status === "error") throw new Error(job.error || "The experiment failed.");
    await new Promise((r) => setTimeout(r, 400));
  }
}
