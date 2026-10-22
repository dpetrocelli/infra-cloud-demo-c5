#!/usr/bin/env bash
# One-time setup of the managed database (run it yourself, as project Owner).
# Creates a small Cloud SQL for Postgres instance, the "demo" database and user,
# the GCP service account the API Pods act as (Workload Identity, no JSON key),
# and the Kubernetes Secret "db" with the password. The password is random and
# never written to a file: it goes straight to Cloud SQL and to the Secret.
#
# Cost: db-f1-micro + 10 GB, billed by the hour while the instance exists.
# Delete it when done: gcloud sql instances delete demo-c5-db
set -euo pipefail

export CLOUDSDK_CORE_PROJECT=project-4c4f803f-f2a7-4566-9fe
PROJECT_ID=project-4c4f803f-f2a7-4566-9fe
INSTANCE=demo-c5-db
NAMESPACE=clase5
SA=api-cloudsql@$PROJECT_ID.iam.gserviceaccount.com

# 1. The instance: the smallest one, one zone, no backups (it is a demo). Takes ~10-15 min.
gcloud services enable sqladmin.googleapis.com
gcloud sql instances create "$INSTANCE" --database-version=POSTGRES_16 --edition=ENTERPRISE \
  --tier=db-f1-micro --region=us-central1 --availability-type=zonal --storage-size=10 --no-backup

# 2. The database and its user, with a random password.
gcloud sql databases create demo --instance="$INSTANCE"
PW=$(openssl rand -hex 16)
gcloud sql users create demo --instance="$INSTANCE" --password="$PW"

# 3. The Kubernetes Secret the API reads (PGUSER, PGPASSWORD). Not in Git.
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "$NAMESPACE" create secret generic db --from-literal=username=demo --from-literal=password="$PW"
unset PW

# 4. The identity of the API: it may only connect to Cloud SQL.
gcloud iam service-accounts create api-cloudsql --display-name="Clase 5: la API se conecta a Cloud SQL"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --condition=None \
  --member="serviceAccount:$SA" --role=roles/cloudsql.client

# 5. Workload Identity: the Kubernetes ServiceAccount clase5/api (k8s/api.yaml) acts as it.
gcloud iam service-accounts add-iam-policy-binding "$SA" --role=roles/iam.workloadIdentityUser \
  --member="serviceAccount:$PROJECT_ID.svc.id.goog[$NAMESPACE/api]"

echo "Listo. kubectl apply -f k8s/ y la API se conecta a $PROJECT_ID:us-central1:$INSTANCE"
