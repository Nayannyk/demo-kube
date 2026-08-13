# demo-backend (chat-app)

Flask backend + nginx frontend chat app with Redis as a service dependency,
Dockerized and deployed to Kubernetes.

## Stack

- **Backend**: Python Flask (`app/`) with a Redis-backed chat API and Redis as a
  service dependency
- **Frontend**: nginx-served chat UI (`frontend/`) that polls the backend API
  (nginx proxies `/api/` to the backend, so the browser only talks to the frontend)
- **Dependency**: Redis (`redis:7-alpine`) with password auth
- **Registry**: Docker Hub (`nayannyk/demo-backend`, `nayannyk/demo-frontend`) via Jenkins CI
- **Deployment**: Kubernetes manifests in `k8s/` (ArgoCD GitOps)

## Repo layout

```
app/          Flask application + Dockerfile + tests
frontend/     Chat UI (static nginx site) + Dockerfile + tests
k8s/          Kubernetes manifests (namespace, config, secret, redis, backend, frontend)
Jenkinsfile   CI/CD pipeline (build -> push registry -> bump manifest tag -> git push)
```

## Local run (docker-compose)

```bash
docker compose up --build
```

- Chat UI: http://localhost:8081
- Backend API: http://localhost:5000
- Health: http://localhost:5000/health
- Info: http://localhost:5000/info
- Messages API: `GET /api/messages`, `POST /api/messages` (`{username, text}`,
  optional `attachment` `{type: image|video, url}`)
- Attachments: `POST /api/upload` (multipart `file`, images/videos ≤ 10 MB,
  stored in Redis for 24h) + `GET /api/files/<id>`

## Docker build

```bash
docker build -t demo-backend:local ./app
docker run -d --name demo-redis -p 6379:6379 \
  redis:7-alpine --requirepass demo-pass-123
docker run -d --name demo-backend -p 5000:5000 \
  -e REDIS_HOST=host.docker.internal \
  -e REDIS_PASSWORD=demo-pass-123 \
  demo-backend:local

docker build -t demo-frontend:local ./frontend
docker run -d --name demo-frontend -p 8081:80 \
  -e BACKEND_URL=http://host.docker.internal:5000 \
  demo-frontend:local
```

## Kubernetes deployment

```bash
cd k8s
kubectl apply -f namespace.yaml
kubectl apply -f app-secret.yaml
kubectl apply -f app-config.yaml
kubectl apply -f redis.yaml
kubectl apply -f app.yaml
kubectl apply -f frontend.yaml

kubectl -n demo rollout status deployment/backend
kubectl -n demo rollout status deployment/frontend
kubectl -n demo get pods,svc

# Access the chat UI directly via NodePort:
#   http://<node-ip>:30080
```

## Port forwarding

### Local kubectl (ClusterIP services)

```bash
# Chat UI  -> http://localhost:8081
kubectl -n demo port-forward svc/frontend 8081:80

# Backend API -> http://localhost:5000
kubectl -n demo port-forward svc/backend 5000:80

# Redis (optional, e.g. redis-cli)
kubectl -n demo port-forward svc/redis 6379:6379
```

### SSH tunnel to the EC2 pipeline host (kind cluster)

If the cluster is on the EC2 host and you want a private tunnel (no NodePort):

```bash
# Chat UI  -> http://localhost:8081
ssh -i C:/Users/NAYAN/Downloads/Kind_key.pem -L 8081:localhost:30080 ubuntu@<public-ip>

# Backend API -> http://localhost:5000
ssh -i C:/Users/NAYAN/Downloads/Kind_key.pem -L 5000:localhost:30080 ubuntu@<public-ip>

# Multiple tunnels at once
ssh -i C:/Users/NAYAN/Downloads/Kind_key.pem \
  -L 8081:localhost:30080 -L 5000:localhost:30080 ubuntu@<public-ip>
```

### Direct from the EC2 host

```bash
kubectl -n demo port-forward svc/frontend 8081:80   # on the host
# then open http://<public-ip>:8081 (SG opens port 8081)
```

> Note: 8080 is reserved for Jenkins, so the chat UI uses 8081 (compose) /
> NodePort 30080 (cluster).

## Pipeline flow (Jenkins)

```
git push (app/frontend change)
      -> Jenkins builds & pushes nayannyk/demo-backend:<sha> + nayannyk/demo-frontend:<sha>
      -> Jenkins bumps image tags in k8s/app.yaml + k8s/frontend.yaml and commits
      -> ArgoCD detects change, auto-syncs Deployments
      -> Jenkins port-forwards frontend (8081) + backend (5000) on the host
```

## Notes

- Backend image tag in `k8s/app.yaml` (`nayannyk/demo-backend:<tag>`) and
  frontend image tag in `k8s/frontend.yaml` (`nayannyk/demo-frontend:<tag>`)
  are bumped automatically by the Jenkins pipeline.
- Probes: `/health` readiness/liveness on backend (checks Redis), TCP probes on
  Redis, `/` probes on the frontend.
- Chat messages are kept in a Redis list (`chat:messages`, max 100) and the
  frontend polls `/api/messages` every 2s.