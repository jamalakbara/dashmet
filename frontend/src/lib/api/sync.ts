import apiClient from "./client";

/**
 * POST /sync/trigger request body. `job_types` is optional: when omitted the
 * backend picks a platform-appropriate default set (see backend
 * services.sync.DEFAULT_JOB_TYPES). Only job_types with a producer for the
 * account's platform are dispatched.
 */
export interface TriggerSyncRequest {
  account_id: string;
  job_types?: string[];
}

export interface TriggerSyncResponse {
  message: string;
  job_ids: string[];
}

export const syncApi = {
  status: (accountId: string) =>
    apiClient.get("/sync/status", { params: { account_id: accountId } }),
  trigger: (accountId: string, jobTypes?: string[]) => {
    const body: TriggerSyncRequest = { account_id: accountId };
    if (jobTypes !== undefined) body.job_types = jobTypes;
    return apiClient.post("/sync/trigger", body);
  },
};
