pipeline {
    agent any

    parameters {
        string(name: 'IMAGE_NAME', defaultValue: 'nayannyk/demo-backend', description: 'Docker Hub image name (namespace/repo)')
        string(name: 'FRONTEND_IMAGE_NAME', defaultValue: 'nayannyk/demo-frontend', description: 'Docker Hub frontend image name (namespace/repo)')
        string(name: 'GIT_REPO_URL', defaultValue: 'github.com/Nayannyk/demo-kube.git', description: 'GitHub repo path')
        string(name: 'MANIFESTS_BRANCH', defaultValue: 'manifests', description: 'Branch ArgoCD syncs from (k8s/ + argocd/ manifests)')
        string(name: 'CLUSTER_NAME', defaultValue: '172.31.40.76:33893', description: 'Cluster name as registered in ArgoCD')
        string(name: 'CLUSTER_SERVER', defaultValue: 'https://172.31.40.76:33893', description: 'Kubernetes API server URL of the ArgoCD cluster')
    }

    environment {
        IMAGE_NAME = "${params.IMAGE_NAME ?: 'nayannyk/demo-backend'}"
        FRONTEND_IMAGE_NAME = "${params.FRONTEND_IMAGE_NAME ?: 'nayannyk/demo-frontend'}"
        GIT_REPO_URL = "${params.GIT_REPO_URL ?: 'github.com/Nayannyk/demo-kube.git'}"
        MANIFESTS_BRANCH = "${params.MANIFESTS_BRANCH ?: 'manifests'}"
        CLUSTER_NAME = "${params.CLUSTER_NAME ?: '172.31.40.76:33893'}"
        CLUSTER_SERVER = "${params.CLUSTER_SERVER ?: 'https://172.31.40.76:33893'}"
        KUBECONFIG_PATH = '/var/lib/jenkins/.kube/config'
    }

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        // Branching strategy:
        //   main      -> app code only (app/, frontend/, Jenkinsfile). Pushes trigger the build.
        //   manifests -> k8s/ + argocd/ only. ArgoCD auto-syncs on every push.
        //                Manifest-only pushes must NOT trigger a rebuild.
        stage('Detect App Changes') {
            steps {
                script {
                    def changed = sh(
                        script: "git diff --name-only HEAD~1 HEAD 2>/dev/null || git show --name-only --format='' HEAD",
                        returnStdout: true
                    ).trim().readLines()
                    echo "Changed files: ${changed}"
                    def appChanged = changed.any {
                        it.startsWith('app/') || it.startsWith('frontend/') || it == 'Jenkinsfile'
                    }
                    if (!appChanged) {
                        echo "Only Kubernetes manifests changed -> nothing to build (ArgoCD will sync)."
                        env.SKIP_BUILD = 'true'
                    } else {
                        env.SKIP_BUILD = 'false'
                    }
                }
            }
        }

        stage('Unit Test') {
            when { expression { env.SKIP_BUILD == 'false' } }
            steps {
                sh '''
                    cd app
                    python3 -c "import ast; ast.parse(open('app.py').read()); print('syntax OK')"
                '''
                sh 'sh frontend/tests/check.sh'
            }
        }

        stage('Build Image') {
            when { expression { env.SKIP_BUILD == 'false' } }
            steps {
                script {
                    env.IMAGE_TAG = sh(script: "git rev-parse --short HEAD", returnStdout: true).trim()
                    echo "Building ${env.IMAGE_NAME}:${env.IMAGE_TAG}"
                }
                sh 'docker build -t "$IMAGE_NAME:$IMAGE_TAG" app/'
                sh 'docker build -t "$FRONTEND_IMAGE_NAME:$IMAGE_TAG" frontend/'
            }
        }

        stage('Push Image') {
            when { expression { env.SKIP_BUILD == 'false' } }
            steps {
                withCredentials([
                    usernamePassword(credentialsId: 'dockerhub-creds', usernameVariable: 'DOCKER_USER', passwordVariable: 'DOCKER_PASS')
                ]) {
                    sh '''
                        echo "$DOCKER_PASS" | docker login -u "$DOCKER_USER" --password-stdin
                        # immutable SHA tag + rolling latest tag for Argo CD Image Updater
                        docker tag "$IMAGE_NAME:$IMAGE_TAG" "$IMAGE_NAME:latest"
                        docker tag "$FRONTEND_IMAGE_NAME:$IMAGE_TAG" "$FRONTEND_IMAGE_NAME:latest"
                        docker push "$IMAGE_NAME:$IMAGE_TAG"
                        docker push "$IMAGE_NAME:latest"
                        docker push "$FRONTEND_IMAGE_NAME:$IMAGE_TAG"
                        docker push "$FRONTEND_IMAGE_NAME:latest"
                    '''
                }
            }
        }

        // Image tag updates in k8s/*.yaml are handled automatically by
        // Argo CD Image Updater (write-back: git) on the manifests branch.
        stage('Ensure ArgoCD ApplicationSet') {
            steps {
                script {
                    env.KUBECONFIG = env.KUBECONFIG_PATH
                }
                sh '''
                    git fetch origin "${MANIFESTS_BRANCH}"
                    git show "origin/${MANIFESTS_BRANCH}:argocd/appset.yaml" > /tmp/appset.yaml
                    kubectl apply -f /tmp/appset.yaml
                    kubectl -n argocd get applicationset demo-backend
                '''
            }
        }

        stage('Expose Chat App (port-forward)') {
            steps {
                script {
                    env.KUBECONFIG = env.KUBECONFIG_PATH
                }
                sh '''
                    PF_PID_FILE=/tmp/demo-chat-port-forwards.pid

                    # stop stale port-forwards from a previous run
                    if [ -f "$PF_PID_FILE" ]; then
                        while read -r pid; do kill "$pid" 2>/dev/null || true; done < "$PF_PID_FILE"
                        rm -f "$PF_PID_FILE"
                    fi

                    # wait for ArgoCD to create the Services
                    for i in $(seq 1 60); do
                        if kubectl -n demo get svc frontend backend >/dev/null 2>&1; then break; fi
                        sleep 5
                    done

                    # wait until at least one pod of each app is Ready
                    kubectl -n demo wait --for=condition=available deploy/frontend --timeout=180s || true
                    kubectl -n demo wait --for=condition=available deploy/backend  --timeout=180s || true

                    # background port-forwards (bound to all interfaces; SG opens 8081/5000)
                    nohup kubectl -n demo port-forward --address 0.0.0.0 svc/frontend 8081:80 > /tmp/pf-frontend.log 2>&1 &
                    echo $! > "$PF_PID_FILE"
                    nohup kubectl -n demo port-forward --address 0.0.0.0 svc/backend  5000:80 > /tmp/pf-backend.log 2>&1 &
                    echo $! >> "$PF_PID_FILE"

                    sleep 5
                    echo "----------------------------------------------------------"
                    echo " Chat UI     : http://$(curl -s ifconfig.me):8081"
                    echo " Backend API : http://$(curl -s ifconfig.me):5000"
                    echo "----------------------------------------------------------"
                    tail -n 2 /tmp/pf-frontend.log
                    tail -n 2 /tmp/pf-backend.log
                '''
            }
        }
    }

    post {
        success {
            script {
                if (env.SKIP_BUILD == 'false') {
                    echo "Images pushed: ${env.IMAGE_NAME}:${env.IMAGE_TAG} / ${env.FRONTEND_IMAGE_NAME}:${env.IMAGE_TAG}"
                    echo "Argo CD Image Updater will tag the k8s manifests on ${env.MANIFESTS_BRANCH}; ArgoCD auto-syncs."
                }
            }
        }
    }
}
