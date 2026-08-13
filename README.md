# demo-kube — Chat App with Full CI/CD (Jenkins + GitHub) and GitOps CD (ArgoCD) + Monitoring (Prometheus / Grafana)

This project is a complete, production-style demo: a chat application is built,
tested, containerized, published to Docker Hub, deployed to Kubernetes via
GitOps (ArgoCD) and monitored with Prometheus + Grafana — all from a GitHub
push to `main`.

---

## 1. Application (technology stack)

A chat app made of two services plus a Redis dependency:

| Component | Technology | Details |
|-----------|------------|---------|
| **Backend** (`app/`) | **Python 3.12** + **Flask 3.0.3** + **Redis client 5.0.8** | REST API; messages stored in Redis (`chat:messages`, max 100); attachments (images/videos ≤ 10 MB) stored 24 h; `/health` probe checks Redis; runs as non-root (`USER 65534`) |
| **Frontend** (`frontend/`) | **nginx 1.27-alpine** static site (HTML/CSS/vanilla JS) | Polls `/api/messages` every 2 s; nginx proxies `/api` → backend (URL injected at boot via `envsubst` in `entrypoint.sh`) |
| **Cache / store** | **Redis 7-alpine** | Password-protected; not built — pulled as infra image |

Backend API endpoints:
`GET /health`, `GET /info`, `GET /api/messages`, `POST /api/messages`
(`{username, text}`, optional `attachment {type, url}`), `DELETE /api/messages`,
`POST /api/upload` (multipart), `GET /api/files/<id>`.

Frontend shows a `v1.1.0 · GitOps (ArgoCD + Jenkins)` footer.

## 2. Infrastructure

The pipeline runs on a single **EC2 host** (`ubuntu@3.110.147.28`,
Ubuntu 22.04) that also hosts a **kind** Kubernetes cluster.

### Kubernetes cluster (on the EC2 host)

- **kind** (Kubernetes in Docker), **Kubernetes v1.36.3**
- 3 nodes: `demo-cluster-control-plane` + 2 workers (2 vCPU / 8 GB each)
- Managed from the host via `kubectl`

### Exposed ports

| Port | Service |
|------|---------|
| 22 | SSH |
| 8080 | Jenkins |
| 3000 | Grafana |
| 9090 | Prometheus |
| 30083 | ArgoCD UI (NodePort) |
| 5000 | Chat app backend API |
| 8081 | Chat app frontend UI |

## 3. What is installed inside the EC2 machine

| Tool | Purpose |
|------|---------|
| Docker | Container runtime + image builds |
| kind + kubectl | Kubernetes cluster + client (Helm v4.2.3) |
| git | Repo checkout / pushes |
| **Jenkins** (systemd service, job `demo-kube`) | CI/CD engine, port 8080 |
| **ArgoCD v3.5.0** (`argocd` namespace) | GitOps controller / CD |
| **Demo chat app** (`demo` namespace) | Redis + backend ×2 + frontend ×2 (Deployments with readiness/liveness probes, resource requests/limits) |
| **kube-prometheus-stack v88.3.0** (`monitoring` namespace) | Prometheus, Grafana, AlertManager, kube-state-metrics, node-exporter (daemonset), prometheus-operator |

## 4. Where the secrets are stored

Secrets are **never committed to git**. Locations:

| Secret | Stored in | Used for |
|--------|-----------|----------|
| **GitHub PAT** (`github-pat`) | Jenkins credential store (`/var/lib/jenkins/credentials.xml`, jenkins user only) | Pushing manifest-tag bumps to the `manifests` branch |
| **Docker Hub credentials** (`dockerhub-creds`) | Jenkins credential store | `docker login` + pushing images |
| **Redis password** (`backend-secret`) | Kubernetes Secret in `demo` namespace | Backend ↔ Redis auth |
| **Grafana admin password** | Kubernetes Secret `kube-prometheus-stack-grafana` (`monitoring` ns); pinned `admin`/`admin` via `monitoring/kube-prometheus-stack-values.yaml` | Grafana login |
| **SSH key** | Local `C:/Users/NAYAN/Downloads/Kind_key.pem` | EC2 access |

- **Jenkins webhook** (id `665159979`): `http://3.110.147.28:8080/github-webhook/`
  (JSON, push events) — points GitHub → Jenkins.
- Kubernetes Secrets are base64-encoded in cluster **etcd**; Jenkins credentials
  are AES-encrypted in `credentials.xml`.

## 5. CI/CD tools and how the pipeline works

- **Source control**: GitHub (`Nayannyk/demo-kube`), branch split:
  - `main` → application code only (`app/`, `frontend/`, `Jenkinsfile`)
  - `manifests` → `k8s/` + `argocd/` manifests that **ArgoCD watches**
- **CI**: **Jenkins** ("Pipeline from SCM", job `demo-kube`, branch `*/main`),
  triggered by the **GitHub webhook** (`githubPush()`) with SCM polling as
  fallback
- **Registry**: **Docker Hub** (`nayannyk/demo-backend`, `nayannyk/demo-frontend`)
- **CD**: **ArgoCD (GitOps)** — `ApplicationSet demo-backend`:
  `repoURL = demo-kube`, `targetRevision = manifests`, `path = k8s`,
  auto-sync + self-heal + prune

### Pipeline stages (Jenkinsfile)

| # | Stage | What it does |
|---|-------|--------------|
| 1 | **Checkout** | `checkout scm` (main) |
| 2 | **Detect App Changes** | If only `k8s/`/`argocd/`/docs changed → skip build (prevents the self-bump from looping) |
| 3 | **Unit Test** | Python syntax check (`app/`) + frontend test script |
| 4 | **Build Image** | Reads last image tag from `k8s/backend.yaml` on `manifests`, patch-increments it → tag = **sequential semver** (`0.0.1`, `0.0.2`, …), then `docker build` backend + frontend |
| 5 | **Push Image** | `docker login` (dockerhub-creds) + push both images to Docker Hub |
| 6 | **Update Manifest & Commit** | Idempotent: checks out `manifests` branch, `sed`-bumps image tags in `k8s/backend.yaml` + `k8s/frontend.yaml` (and `APP_VERSION` in `k8s/app-config.yaml`) to the new semver, commits `chore(ci): bump …` only if changed, pushes via `github-pat` |
| 7 | **Ensure ArgoCD ApplicationSet** | `git show manifests:argocd/appset.yaml \| kubectl apply -f -` |
| 8 | **Expose Chat App** | `kubectl port-forward` frontend `:8081` + backend `:5000` on the host |

### End-to-end flow

```
git push (app/frontend change) on main
  → GitHub webhook → Jenkins build #N
  → Unit Test → docker build/push nayannyk/demo-{backend,frontend}:<semver>
  → bump image tags on the manifests branch + push
  → ArgoCD detects the manifests-branch change → auto-syncs Deployments
  → app rolled out → port-forwards refreshed (8081 / 5000)
```

`manifests`-branch commits (created by the pipeline itself) do **not** re-trigger
builds, so there is no infinite loop.

## 6. Container images

| Image | Base | Contents | Notes |
|-------|------|----------|-------|
| `nayannyk/demo-backend:<semver>` | `python:3.12-slim` | Flask app (`app.py`) | Non-root, `HEALTHCHECK /health`, exposes 5000 |
| `nayannyk/demo-frontend:<semver>` | `nginx:1.27-alpine` | static chat UI + `app.js` + nginx conf template | `entrypoint.sh` runs `envsubst` for `BACKEND_URL`, exposes 80 |
| `redis:7-alpine` | — | infra dependency | used as-is, requires password |

Tags are **sequential semantic versions** (`0.0.1`, `0.0.2`, …). The pipeline reads
the current image tag from `k8s/backend.yaml` on the `manifests` branch and
increments the patch version for each build; if the current tag is not a semver
(e.g. an older git SHA) it starts from `0.0.1`.

## 7. Monitoring (Prometheus + Grafana)

- GitOps-managed: `monitoring/application.yaml` on the `manifests` branch →
  ArgoCD installs **kube-prometheus-stack** (Helm chart `88.3.0`) into
  `monitoring`
- **Prometheus**: `http://3.110.147.28:9090` — 22+ scrape targets up
  (node-exporter ×3, kube-state-metrics, kubelet, API server, CoreDNS,
  Prometheus/AlertManager/Grafana). Scrapes the cluster itself plus the
  operators' ServiceMonitors.
- **Grafana**: `http://3.110.147.28:3000` — login **admin / admin**, ships
  **29 pre-built dashboards** (Kubernetes API server, Compute Resources
  Cluster/Node/Pod/Namespace, etcd, CoreDNS, Alertmanager, Grafana …)
- Components: Prometheus, AlertManager, Grafana, prometheus-operator,
  kube-state-metrics, node-exporter
- Note: the chart's CRDs are installed out-of-band (the `crds` sub-chart is
  disabled and `Prune=false`) because ArgoCD cannot client-side apply these
  large CRDs.

## 8. Repo layout

```
app/           Flask backend + Dockerfile + tests
frontend/      nginx chat UI + Dockerfile + tests
k8s/           Kubernetes manifests — one file per resource (namespace.yaml, app-config.yaml, app-secret.yaml, redis.yaml, backend.yaml, backend-service.yaml, frontend.yaml, frontend-service.yaml, frontend-config.yaml)
argocd/        ArgoCD ApplicationSet (targets k8s/ on the manifests branch)
monitoring/    ArgoCD Application + values for kube-prometheus-stack
Jenkinsfile    CI/CD pipeline (webhook-triggered, self-bump + GitOps)
```

## 9. Local run

```bash
docker compose up --build
# Chat UI http://localhost:8081 · Backend API http://localhost:5000
# Health http://localhost:5000/health
```
