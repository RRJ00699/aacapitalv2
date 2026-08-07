# JOB_FLAG KV namespace split (owner-run; not applied)

Status: **PREPARATION ONLY**. This repository change does not create a namespace,
copy or delete a key, change a production binding, or deploy.

## Create the namespace

From the authenticated owner workstation:

```powershell
npx wrangler kv namespace create JOB_FLAG
```

Record the returned namespace ID as `<NEW_JOB_FLAG_NAMESPACE_ID>`. The proposed
configuration change, in a later activation PR, is exactly:

```diff
-    { "binding": "JOB_FLAG", "id": "71fc0e8060ce4cad919b58d35b9681e2" },
+    { "binding": "JOB_FLAG", "id": "<NEW_JOB_FLAG_NAMESPACE_ID>" },
```

Do not commit the placeholder and do not change the `CACHE` binding.

## Key migration

The only job-queue flag is `admin:jobs-pending`. Immediately before deployment,
read it from the old namespace. If and only if its value is `1`, write `1` to the
new namespace with the same one-hour TTL. Do not delete the old key during the
cutover. If it is absent, leave it absent in the new namespace.

## Deployment sequence

1. Create `JOB_FLAG` and record its ID; make no binding change yet.
2. Inspect `admin:jobs-pending` in the current shared namespace.
3. If pending, copy the value and TTL behavior to the new namespace.
4. Replace only the `JOB_FLAG` ID, review the resulting `wrangler.jsonc` diff,
   run the complete test/build gate, and deploy once.
5. Queue one harmless Admin smoke job and verify the jobs route writes the flag,
   the flag route reads it, and the VM clears it after draining the queue.
6. Verify ordinary `CACHE` reads remain unchanged. Retain the old key until the
   observation window has completed.

## Rollback

1. Restore `JOB_FLAG` to `71fc0e8060ce4cad919b58d35b9681e2`.
2. Redeploy the last known-good worker configuration.
3. Verify `admin:jobs-pending` through the job-flag route and drain any queued job.
4. Leave the new namespace and its key intact for diagnosis; delete neither until
   the owner separately approves cleanup.

## Cost impact

Creating a namespace has no separate namespace fee. The split does not add normal
job-flag reads or writes; it redirects them, so expected usage is unchanged and
should remain within the existing Cloudflare Workers KV free-tier allowance.
Actual account-plan limits and billing remain owner-verified at activation time.
