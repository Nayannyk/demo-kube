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

The pipeline runs on a single **EC2 host** (`ubuntu`,
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

## 4. Step-by-step setup of the entire machine

Below is the exact order used to bring up the EC2 host from scratch: OS → Docker →
kubectl → kind cluster → Helm → Jenkins (with plugins) → ArgoCD → Prometheus/Grafana →
then the repo + pipeline. Run every command as the `ubuntu` user unless noted.

### 4.1 Prerequisites

- EC2 instance **Ubuntu 22.04**, recommended `t3.large` (2 vCPU / 8 GB)
- Security group must open: `22`, `8080` (Jenkins), `3000` (Grafana),
  `9090` (Prometheus), `30083` (ArgoCD NodePort), `5000` + `8081` (chat app)

### 4.2 Step 1 — Update the OS

```bash
sudo apt update && sudo apt upgrade -y
```

### 4.3 Step 2 — Install Docker

```bash
sudo apt install -y docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
newgrp docker        # apply the group change without logging out
docker version
```

### 4.4 Step 3 — Install git

```bash
sudo apt install -y git
git --version
```

### 4.5 Step 4 — Install kubectl

```bash
curl -fsSL -o kubectl "https://dl.k8s.io/release/$(curl -fsSL https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
sudo install -m 755 kubectl /usr/local/bin/kubectl
kubectl version --client
```

### 4.6 Step 5 — Install kind and create the cluster

The cluster binds the Kubernetes API server to the EC2 **private IP** on port
`33893` so Jenkins and ArgoCD can reach it. The config lives in
[`kind.yaml`](./kind.yaml) at the repo root — replace `<your private IP>` first.

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
networking:
  apiServerAddress: "<your private IP>"   # run `hostname -I` or check the EC2 dashboard
  apiServerPort: 33893
nodes:
  - role: control-plane
    image: kindest/node:v1.33.1
  - role: worker
    image: kindest/node:v1.33.1
  - role: worker
    image: kindest/node:v1.33.1
```

```bash
# install kind
curl -Lo kind "https://github.com/kubernetes-sigs/kind/releases/latest/download/kind-linux-amd64"
chmod +x kind
sudo install -m 755 kind /usr/local/bin/kind
kind version

# create the cluster
hostname -I                                       # e.g. 172.31.19.178 -> edit kind.yaml
kind create cluster --name demo-cluster --config kind.yaml
kind get clusters
kubectl cluster-info
kubectl get nodes -o wide
```

### 4.7 Step 6 — Install Helm

```bash
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
helm version
```

### 4.8 Step 7 — Install Jenkins

```bash
sudo apt install -y openjdk-17-jre-headless fontconfig

curl -fsSL https://pkg.jenkins.io/debian-stable/jenkins.io-2023.key | sudo tee /usr/share/keyrings/jenkins-keyring.asc > /dev/null
echo "deb [signed-by=/usr/share/keyrings/jenkins-keyring.asc] https://pkg.jenkins.io/debian-stable binary/" | sudo tee /etc/apt/sources.list.d/jenkins.list > /dev/null
sudo apt update
sudo apt install -y jenkins

sudo systemctl enable --now jenkins
sudo systemctl status jenkins
sudo cat /var/lib/jenkins/secrets/initialAdminPassword   # first-time unlock code
```

Jenkins runs as a systemd service on port `8080`. Open
`http://<server-public-ip>:8080`, enter the initial admin password and install
the **suggested plugins**.

Give the `jenkins` user access to Docker and kubectl (the pipeline runs
`docker build`/`push` and `kubectl`):

```bash
sudo usermod -aG docker jenkins
sudo mkdir -p /var/lib/jenkins/.kube
sudo cp ~/.kube/config /var/lib/jenkins/.kube/config
sudo chown -R jenkins:jenkins /var/lib/jenkins/.kube
sudo systemctl restart jenkins
```

### 4.9 Step 8 — Jenkins plugins used by this pipeline

| Plugin | Used for |
|--------|----------|
| **Pipeline** | Declarative `pipeline { }` in the Jenkinsfile |
| **Git** | `checkout scm` |
| **GitHub** | `githubPush()` trigger + `/github-webhook/` |
| **Credentials Binding** | `withCredentials(usernamePassword … / string …)` |
| **Timestamper** | `timestamps()` log output |
| **Docker Pipeline** (optional) | `docker.build()` convenience steps (this repo calls the `docker` CLI via `sh` instead) |

Install via **Manage Jenkins → Plugins → Available plugins** (or the suggested
list already includes most of them).

### 4.10 Step 9 — Create the Jenkins job, credentials and webhook

1. **Job**: New Item → Pipeline → name `demo-kube`
2. **Definition**: *Pipeline script from SCM*
   - SCM: **Git**
   - Repository URL: `https://github.com/Nayannyk/demo-kube.git`
   - Branches to build: `*/main`
   - Script Path: `Jenkinsfile`
3. **Credentials** (Manage Jenkins → Credentials → Global → Add credentials):
   - `github-pat` — Secret text (GitHub PAT used to push tag bumps to `manifests`)
   - `dockerhub-creds` — Username with password (Docker Hub `docker login`/push)
4. **Webhook**: GitHub repo → Settings → Webhooks → Add webhook
   `http://<server-public-ip>:8080/github-webhook/`, content type
   `application/json`, trigger on **push** events

### 4.11 Step 10 — Install ArgoCD (GitOps CD)

```bash
# install ArgoCD server-side (stable channel, includes ApplicationSet CRD)
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# expose the UI as NodePort 30083
kubectl patch svc argocd-server -n argocd -p '{"spec":{"type":"NodePort","ports":[{"name":"http","port":80,"targetPort":8080,"nodePort":30083},{"name":"https","port":443,"targetPort":8080,"nodePort":30084}]}}'
# serve plain HTTP (avoid https redirect loop behind the SG)
kubectl patch cm argocd-cmd-params-cm -n argocd --type merge -p '{"data":{"server.insecure":"true"}}'
kubectl rollout restart deploy argocd-server -n argocd

# ArgoCD CLI
curl -sSL -o argocd https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
sudo install -m 755 argocd /usr/local/bin/argocd
argocd version --client

# initial admin password
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo
```

Register the kind cluster with ArgoCD so the `ApplicationSet` (which targets
`https://172.31.40.76:33893`, i.e. the private IP + `apiServerPort` from
`kind.yaml`) can deploy into it:

```bash
argocd login 172.31.40.76:33893 --insecure          # admin + the password above
argocd cluster add kind-demo-cluster --insecure     # kind context name = kind-<cluster-name>
argocd app list                                     # demo-backend + kube-prometheus-stack appear here
```

### 4.12 Step 11 — Install Prometheus + Grafana

This repo manages monitoring as **GitOps** — an ArgoCD `Application`
(`monitoring/application.yaml` on the `manifests` branch) that renders the
`kube-prometheus-stack` Helm chart `88.3.0` with the repo's values file. Nothing
needs to be installed by hand; push the manifests and ArgoCD syncs:

```bash
git add monitoring/ argocd/
git commit -m "monitoring: add kube-prometheus-stack Application + values"
git push origin manifests

kubectl get app -n argocd                            # watch kube-prometheus-stack -> Synced/Healthy
kubectl get pods -n monitoring
kubectl get svc -n monitoring
```

Direct (non-GitOps) equivalent, for reference:

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  --version 88.3.0 \
  --values monitoring/kube-prometheus-stack-values.yaml
```

Expose the UIs (already reachable on ports `3000`/`9090` if your security group
routes them to a NodePort, otherwise port-forward):

```bash
kubectl -n monitoring port-forward svc/kube-prometheus-stack-grafana 3000:80
kubectl -n monitoring port-forward svc/prometheus-operated 9090:9090
# Grafana login: admin / admin (pinned via monitoring/kube-prometheus-stack-values.yaml)
```

### 4.13 Step 12 — Create the repo, folder structure and pipeline

```bash
mkdir -p demo-kube/{app,frontend,k8s,argocd,monitoring}
cd demo-kube
git init -b main
git branch manifests
git remote add origin https://github.com/Nayannyk/demo-kube.git
git add .
git commit -m "chore: initial repo + folder structure"
git push -u origin main manifests
```

Folder structure (see also section 9 "Repo layout"):

```
app/           Flask backend + Dockerfile + tests
frontend/      nginx chat UI + Dockerfile + tests
k8s/           Kubernetes manifests — one file per resource
argocd/        ApplicationSet (targets k8s/ on the manifests branch)
monitoring/    ArgoCD Application + values for kube-prometheus-stack
kind.yaml      kind cluster config (replace <your private IP>)
Jenkinsfile    CI/CD pipeline (webhook-triggered, self-bump + GitOps)
```

Then add the `Jenkinsfile` (this repo's pipeline), commit and push to `main`.
The GitHub webhook triggers Jenkins, which builds/pushes images, bumps the tags
on `manifests`, and ArgoCD rolls the new version out.

## 5. Where the secrets are stored

Secrets are **never committed to git**. Locations:

| Secret | Stored in | Used for |
|--------|-----------|----------|
| **GitHub PAT** (`github-pat`) | Jenkins credential store (`/var/lib/jenkins/credentials.xml`, jenkins user only) | Pushing manifest-tag bumps to the `manifests` branch |
| **Docker Hub credentials** (`dockerhub-creds`) | Jenkins credential store | `docker login` + pushing images |
| **Redis password** (`backend-secret`) | Kubernetes Secret in `demo` namespace | Backend ↔ Redis auth |
| **Grafana admin password** | Kubernetes Secret `kube-prometheus-stack-grafana` (`monitoring` ns); pinned `admin`/`admin` via `monitoring/kube-prometheus-stack-values.yaml` | Grafana login |
| **SSH key** | Local `C:/Users/NAYAN/Downloads/Kind_key.pem` | EC2 access |

- **Jenkins webhook** (id `665159979`): `http://<server-public-ip>:8080/github-webhook/`
  (JSON, push events) — points GitHub → Jenkins.
- Kubernetes Secrets are base64-encoded in cluster **etcd**; Jenkins credentials
  are AES-encrypted in `credentials.xml`.

## 6. CI/CD tools and how the pipeline works

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

## 7. Container images

| Image | Base | Contents | Notes |
|-------|------|----------|-------|
| `nayannyk/demo-backend:<semver>` | `python:3.12-slim` | Flask app (`app.py`) | Non-root, `HEALTHCHECK /health`, exposes 5000 |
| `nayannyk/demo-frontend:<semver>` | `nginx:1.27-alpine` | static chat UI + `app.js` + nginx conf template | `entrypoint.sh` runs `envsubst` for `BACKEND_URL`, exposes 80 |
| `redis:7-alpine` | — | infra dependency | used as-is, requires password |

Tags are **sequential semantic versions** (`0.0.1`, `0.0.2`, …). The pipeline reads
the current image tag from `k8s/backend.yaml` on the `manifests` branch and
increments the patch version for each build; if the current tag is not a semver
(e.g. an older git SHA) it starts from `0.0.1`.

## 8. Monitoring (Prometheus + Grafana)

- GitOps-managed: `monitoring/application.yaml` on the `manifests` branch →
  ArgoCD installs **kube-prometheus-stack** (Helm chart `88.3.0`) into
  `monitoring`
- **Prometheus**: `http://<server-public-ip>:9090` — 22+ scrape targets up
  (node-exporter ×3, kube-state-metrics, kubelet, API server, CoreDNS,
  Prometheus/AlertManager/Grafana). Scrapes the cluster itself plus the
  operators' ServiceMonitors.
- **Grafana**: `http://<server-public-ip>:3000` — login **admin / admin**, ships
  **29 pre-built dashboards** (Kubernetes API server, Compute Resources
  Cluster/Node/Pod/Namespace, etcd, CoreDNS, Alertmanager, Grafana …)
- Components: Prometheus, AlertManager, Grafana, prometheus-operator,
  kube-state-metrics, node-exporter
- Note: the chart's CRDs are installed out-of-band (the `crds` sub-chart is
  disabled and `Prune=false`) because ArgoCD cannot client-side apply these
  large CRDs.

## 9. Repo layout

```
app/           Flask backend + Dockerfile + tests
frontend/      nginx chat UI + Dockerfile + tests
k8s/           Kubernetes manifests — one file per resource (namespace.yaml, app-config.yaml, app-secret.yaml, redis.yaml, backend.yaml, backend-service.yaml, frontend.yaml, frontend-service.yaml, frontend-config.yaml)
argocd/        ArgoCD ApplicationSet (targets k8s/ on the manifests branch)
monitoring/    ArgoCD Application + values for kube-prometheus-stack
kind.yaml      kind cluster config (set `apiServerAddress` to the EC2 private IP)
Jenkinsfile    CI/CD pipeline (webhook-triggered, self-bump + GitOps)
```

## 10. Local run

```bash
docker compose up --build
# Chat UI http://localhost:8081 · Backend API http://localhost:5000
# Health http://localhost:5000/health
```
