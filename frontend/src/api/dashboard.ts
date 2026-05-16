import type { BundleResponse } from "../types/bundle";

export async function fetchBundle(runId: string): Promise<BundleResponse> {
  const resp = await fetch(`/api/experiments/${runId}/dashboard_bundle`);
  if (!resp.ok) {
    throw new Error(`Failed to fetch bundle (${resp.status})`);
  }
  return resp.json();
}
