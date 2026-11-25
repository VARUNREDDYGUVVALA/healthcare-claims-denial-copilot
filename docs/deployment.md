# Deployment

## GitHub Pages

Create the public repository `healthcare-claims-denial-copilot`, then choose **Settings → Pages → Build and deployment → Source → GitHub Actions**. Push `main` or dispatch **Checks and GitHub Pages** after enabling Pages.

The workflow regenerates and checks the committed export, runs Python tests, type-checks and builds React, and runs desktop and mobile browser tests. A successful `main` build publishes `apps/frontend/dist` and checks the deployed HTML and JSON. The Actions deployment job displays the Pages URL.

## Local application

From the repository root, set separate local analyst and supervisor tokens before starting Docker Compose. Keep these values out of Git.

```sh
export COPILOT_ANALYST_TOKEN="$(openssl rand -hex 32)"
export COPILOT_SUPERVISOR_TOKEN="$(openssl rand -hex 32)"
docker compose up --build -d
docker compose ps
```

If your build network uses a trusted TLS inspection CA, build with `docker build -f infrastructure/docker/Dockerfile --secret id=claims_build_ca,src=/path/to/trusted-ca-bundle.pem -t healthcare-claims-denial-copilot-copilot .`, then run `docker compose up --no-build -d`. The build uses the optional bundle only while installing dependencies.

Open [the authenticated local workflow](http://localhost:8000/?mode=api). Open **Review March 2026 case**, simulate the response, then start the **Local investigation** with the analyst token. The evidence includes the January authorization and the Version 1 policy. Save the investigation ID to reopen it after a service restart. Enter the supervisor token, a review note, and an approval or rejection to record the final review.

You can also run without Docker after generating the artifacts. Build with `npm ci && npm run build` inside `apps/frontend`, then from the repository root run `COPILOT_SERVE_UI=1 python -m uvicorn apps.api.main:app`. Set the same two tokens in that shell. The investigation UI appears only on loopback hosts.
