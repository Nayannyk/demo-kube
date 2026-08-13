# Manifests branch (ArgoCD GitOps)

This branch is the source of truth for the Kubernetes manifests. ArgoCD syncs
the `k8s/` directory from this branch (`targetRevision: manifests`).

## Flow

1. `main` branch: application code (`app/`, `frontend/`, `Jenkinsfile`).
   Pushes here trigger the Jenkins pipeline, which builds + pushes
   `nayannyk/demo-backend:<sha>` / `nayannyk/demo-frontend:<sha>` **and**
   `...:latest`.
2. Argo CD Image Updater (running in the cluster) watches Docker Hub. When a
   new `latest` tag is pushed it updates the image tags in `k8s/*.yaml` and
   commits them to this branch (write-back: git).
3. ArgoCD detects the change and auto-syncs the Deployments.

Manual manifest edits are also made here (any push to this branch triggers
ArgoCD auto-sync; Jenkins skips the build for manifest-only changes).

## Image Updater credentials

The updater writes back to git using the `argocd/image-updater-creds` secret
in the `argocd` namespace:

```bash
kubectl -n argocd create secret generic image-updater-creds \
  --from-literal=username=<github-user> \
  --from-literal=password=<github-pat-with-repo-write>
```

## Configuration

Annotations live on the ApplicationSet template in `argocd/appset.yaml`:

- `image-list`: which images to track
- `<name>.update-strategy`: `latest` (track the `:latest` tag)
- `write-back-method`: `git:secret:argocd/image-updater-creds`
- `git-branch`: `manifests` (branch to commit image tag updates to)
