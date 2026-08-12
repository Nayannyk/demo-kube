# demo-backend (chat-app)

Flask backend with Redis as a service dependency, Dockerized and deployed to Kubernetes.
Content mirrors the `demo-kube` reference repository.

## Stack

- **App**: Python Flask backend (`app/`) with Redis as a service dependency
- **Dependency**: Redis (`redis:7-alpine`) with password auth
- **Registry**: `localhost:5000` (insecure, local) via Jenkins CI
- **Deployment**: Kubernetes manifests in `k8s/` (ArgoCD GitOps)

## Repo layout

```
app/          Flask application + Dockerfile + tests
k8s/          Kubernetes manifests (namespace, config, secret, redis, app)
Jenkinsfile   CI/CD pipeline (build -> push registry -> bump manifest tag -> git push)
```

## Local run (docker-compose)

```bash
cd chat-app
docker compose up --build
```

- App: http://localhost:5000
- Health: http://localhost:5000/health
- Info: http://localhost:5000/info

## Docker build

```bash
cd chat-app/app
docker build -t demo-backend:local .
docker run -d --name demo-redis -p 6379:6379 \
  redis:7-alpine --requirepass demo-pass-123
docker run -d --name demo-backend -p 5000:5000 \
  -e REDIS_HOST=host.docker.internal \
  -e REDIS_PASSWORD=demo-pass-123 \
  demo-backend:local
```

## Kubernetes deployment

```bash
cd chat-app/k8s
kubectl apply -f namespace.yaml
kubectl apply -f app-secret.yaml
kubectl apply -f app-config.yaml
kubectl apply -f redis.yaml
kubectl apply -f app.yaml

kubectl -n demo rollout status deployment/backend
kubectl -n demo get pods,svc

# Access (port-forward ClusterIP):
kubectl -n demo port-forward svc/backend 80:80
# then curl http://localhost:80
```

## Pipeline flow (Jenkins)

```
git push (app change)
      -> Jenkins builds & pushes localhost:5000/demo-backend:<sha>
      -> Jenkins bumps image tag in k8s/app.yaml and commits
      -> ArgoCD detects change, auto-syncs Deployment
```

## Notes

- Backend image tag in `k8s/app.yaml` (`localhost:5000/demo-backend:<tag>`) is
  bumped automatically by the Jenkins pipeline.
- Probes: `/health` readiness/liveness on backend (checks Redis), TCP probes on Redis.
