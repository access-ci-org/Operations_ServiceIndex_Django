# Service Index deployment workflows

Every normal beta and production deployment runs with `run_migrations=false`.
That is the safe default. If Django reports pending migrations, the infrastructure
playbook stops before release activation; it never changes the value to `true`.

Migration execution requires a new, explicit workflow dispatch for the exact same
immutable release tag. Do not use GitHub's **Re-run failed jobs** action: a rerun
keeps the original `run_migrations=false` input.

## Before a migration-enabled retry

1. Confirm the failed **Run Ansible deployment** step stopped at the pending-
   migration check. Do not treat a database connection, configuration, backup,
   checkout, Ansible, or other failure as proof that migrations are pending.
2. Review the migration plan printed by the infrastructure playbook and inspect
   the migration code in the release tag.
3. Use the same `vX.Y.Z` value for `--ref` and `version_tag`. Never move or reuse
   a release tag.
4. Confirm that the workflow files are present at that tag and that the tag is
   reachable from `main`.
5. Authenticate GitHub CLI as an actor allowed to run the workflow. These commands
   dispatch GitHub Actions; they do not run a deployment from the local machine.

## Beta retry with migrations

For a migration-enabled retry, the normal tag-triggered beta run must first have
stopped with migrations disabled. After the checks above, replace `vX.Y.Z` with
that same failed release tag and run:

```bash
gh workflow run deploy-beta.yml \
  --repo access-ci-org/Operations_ServiceIndex_Django \
  --ref vX.Y.Z \
  --field version_tag=vX.Y.Z \
  --field run_migrations=true
```

The workflow rejects a migration-enabled beta dispatch unless it can find a failed
default-false beta deployment for the same tag and commit. A human must still
verify that pending migrations—not another failure—caused that earlier stop.

After this run succeeds, beta smoke tests must pass before production is eligible.
The normal production call still starts with `run_migrations=false`.

## Production retry with migrations

Use this only after the same tag has passed beta, the default-false production
deployment has stopped on pending migrations, the migration plan has been
reviewed, and the separately approved database recovery process is ready. Replace
`vX.Y.Z` with that exact release tag and run:

```bash
gh workflow run deploy-production.yml \
  --repo access-ci-org/Operations_ServiceIndex_Django \
  --ref vX.Y.Z \
  --field version_tag=vX.Y.Z \
  --field run_migrations=true
```

The production workflow revalidates the tag-to-commit binding, confirms the tag is
reachable from `main`, and requires successful beta smoke tests for the same tag
and commit. It then waits for the separate protected `production` environment
approval before deployment steps or production environment secrets are available.

## What happens next

With explicit authorization, the checked-out Service Index infrastructure
playbook runs the migrations, checks again for unapplied migrations, and only then
continues with static collection, release activation, service restart, and
readiness checks. If any guarded step fails, follow the authorized recovery or
rollback procedure; do not move the tag or turn unrelated failures into migration
authorization.
