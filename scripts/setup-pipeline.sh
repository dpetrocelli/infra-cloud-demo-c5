#!/usr/bin/env bash
# One-time setup for the deploy pipeline (run it yourself, as project Owner).
# Creates the gke-deployer service account, gives it only what the pipeline
# needs, lets GitHub Actions of this repo impersonate it via OIDC (no JSON
# key), and sets the repository variables the workflow reads.
set -euo pipefail

export CLOUDSDK_CORE_PROJECT=project-4c4f803f-f2a7-4566-9fe
PROJECT_ID=project-4c4f803f-f2a7-4566-9fe
PROJECT_NUMBER=158566931151
REPO=dpetrocelli/infra-cloud-demo-c5
POOL=github-pool-ensayo
PROVIDER=github-provider-c5
SA=gke-deployer@$PROJECT_ID.iam.gserviceaccount.com

# 1. The pipeline's identity.
gcloud iam service-accounts create gke-deployer \
  --display-name="Clase 5: pipeline de demo-c5 (push a AR y deploy a GKE)"

# 2. Push images, only to the demo-c5 repo.
gcloud artifacts repositories add-iam-policy-binding demo-c5 --location=us-central1 \
  --member="serviceAccount:$SA" --role=roles/artifactregistry.writer

# 3. Deploy to GKE (kubectl apply, rollout status).
gcloud projects add-iam-policy-binding "$PROJECT_ID" --condition=None \
  --member="serviceAccount:$SA" --role=roles/container.developer

# 4. OIDC: a provider in the existing pool that only accepts this repo.
gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
  --workload-identity-pool="$POOL" --location=global \
  --issuer-uri=https://token.actions.githubusercontent.com \
  --attribute-mapping=google.subject=assertion.sub,attribute.repository=assertion.repository \
  --attribute-condition="assertion.repository=='$REPO'"

# 5. Only this repo's workflows can act as gke-deployer. Takes up to 5 min to propagate.
gcloud iam service-accounts add-iam-policy-binding "$SA" --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/attribute.repository/$REPO"

# 6. The variables the workflow reads (no secrets).
gh variable set GCP_PROJECT_ID -R "$REPO" --body "$PROJECT_ID"
gh variable set GCP_WORKLOAD_IDENTITY_PROVIDER -R "$REPO" \
  --body "projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/providers/$PROVIDER"
gh variable set GCP_SERVICE_ACCOUNT -R "$REPO" --body "$SA"
gh variable set GKE_CLUSTER -R "$REPO" --body demo-c5
gh variable set GKE_LOCATION -R "$REPO" --body us-central1-a

echo "Listo. Esperá ~5 min (propagación de IAM) y hacé push a main o: gh workflow run deploy -R $REPO"
