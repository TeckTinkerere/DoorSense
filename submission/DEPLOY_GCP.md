# Host DoorLens on your team's hackathon Google Cloud project

You do this once, in the browser, with the team credentials from the Hackathon portal. No installs.

1. Sign in to the Google Cloud console in an **Incognito** window (portal step 3-6), and pick your team project in the top-left project selector.
2. Click the **Cloud Shell** icon (`>_`, top right) and wait for the terminal.
3. Paste:

```bash
git clone https://github.com/TeckTinkerere/DoorSense.git
cd DoorSense
gcloud config get-value project          # confirm it is your team project
gcloud run deploy doorlens \
  --source . \
  --region asia-southeast1 \
  --memory 2Gi --cpu 2 --timeout 300 \
  --min-instances 1 --max-instances 1 --concurrency 8 \
  --allow-unauthenticated
```

4. Answer `y` if asked to enable Cloud Build / Cloud Run / Artifact Registry APIs (about 3-5 minutes the first time).
5. The command prints `Service URL: https://doorlens-…run.app`. That is the **hosted domain** for the submission.
6. Open it, click **ACV**, upload `acv_test_case.xlsx`; then Door and upload `Test.csv`. You should get the same predictions as `predictions/`.

Notes
- One instance is deliberate: results are held in memory, so a second instance would lose a user's analysis.
- If `--allow-unauthenticated` is refused by an organisation policy, ask the organisers to allow public access, or keep it private and show it from the console's *Cloud Run > Test* URL.
- Uploads are capped at 32 MiB by Cloud Run; both test files are about 2 MB.
- To update after a code change: `git pull` then repeat the `gcloud run deploy` command.
