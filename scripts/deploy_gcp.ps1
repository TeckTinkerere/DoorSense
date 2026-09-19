[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ProjectId,
    [string]$Region = 'asia-southeast1',   # Singapore
    [string]$Service = 'doorlens',
    [switch]$AllowUnauthenticated           # public URL; omit to keep it private
)
# Deploys the app to Cloud Run using Cloud Build (no local Docker needed).
# Requires: gcloud installed and `gcloud auth login` done by you. Billing must be enabled on the project.
$ErrorActionPreference = 'Stop'
gcloud config set project $ProjectId | Out-Null
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

$args = @(
    'run', 'deploy', $Service,
    '--source', (Split-Path $PSScriptRoot -Parent),
    '--region', $Region,
    '--memory', '2Gi', '--cpu', '2',
    '--timeout', '300',
    # Analyses are kept in process memory, so every request must reach the same instance.
    '--min-instances', '1', '--max-instances', '1', '--concurrency', '8',
    '--set-env-vars', 'DOORLENS_ANALYSIS_TTL_SECONDS=1800'
)
if ($AllowUnauthenticated) { $args += '--allow-unauthenticated' } else { $args += '--no-allow-unauthenticated' }
gcloud @args
if ($LASTEXITCODE -ne 0) { throw 'Cloud Run deploy failed.' }
gcloud run services describe $Service --region $Region --format 'value(status.url)'
