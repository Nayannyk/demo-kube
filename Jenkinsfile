pipeline {
    agent any

    parameters {
        string(name: 'IMAGE_NAME', defaultValue: 'nayannyk/demo-backend', description: 'Docker Hub image name (namespace/repo)')
        string(name: 'GIT_REPO_URL', defaultValue: 'github.com/Nayannyk/demo-kube.git', description: 'GitHub repo path')
        string(name: 'GIT_BRANCH', defaultValue: 'main', description: 'Branch to push the manifest bump to')
        string(name: 'GIT_IDENTITY', defaultValue: 'jenkins-cd <jenkins@demo.local>', description: 'git author: "Name <email>"')
        string(name: 'CLUSTER_NAME', defaultValue: '172.31.40.76:33893', description: 'Cluster name as registered in ArgoCD')
        string(name: 'CLUSTER_SERVER', defaultValue: 'https://172.31.40.76:33893', description: 'Kubernetes API server URL of the ArgoCD cluster')
        string(name: 'KUBECONFIG_PATH', defaultValue: '/home/ubuntu/.kube/config', description: 'Path to the kubeconfig file on the Jenkins agent')
    }

    environment {
        IMAGE_NAME = "${params.IMAGE_NAME ?: 'nayannyk/demo-backend'}"
        GIT_REPO_URL = "${params.GIT_REPO_URL ?: 'github.com/Nayannyk/demo-kube.git'}"
        GIT_BRANCH = "${params.GIT_BRANCH ?: 'main'}"
        GIT_IDENTITY = "${params.GIT_IDENTITY ?: 'jenkins-cd <jenkins@demo.local>'}"
        CLUSTER_NAME = "${params.CLUSTER_NAME ?: '172.31.40.76:33893'}"
        CLUSTER_SERVER = "${params.CLUSTER_SERVER ?: 'https://172.31.40.76:33893'}"
        KUBECONFIG_PATH = "${params.KUBECONFIG_PATH ?: '/home/ubuntu/.kube/config'}"
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

        // Avoid an infinite CI loop: manifest-only commits (made by this pipeline)
        // must NOT trigger a rebuild. Only app/ code or the Jenkinsfile trigger builds.
        stage('Detect App Changes') {
            steps {
                script {
                    def changed = sh(
                        script: "git diff --name-only HEAD~1 HEAD 2>/dev/null || git show --name-only --format='' HEAD",
                        returnStdout: true
                    ).trim().readLines()
                    echo "Changed files: ${changed}"
                    def appChanged = changed.any {
                        it.startsWith('app/') || it == 'Jenkinsfile'
                    }
                    if (!appChanged) {
                        echo "Only Kubernetes manifests changed -> nothing to build."
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
                        docker push "$IMAGE_NAME:$IMAGE_TAG"
                    '''
                }
            }
        }

        stage('Update Manifest & Commit') {
            when { expression { env.SKIP_BUILD == 'false' } }
            steps {
                script {
                    sh '''
                        sed -i "s|image: .*|image: $IMAGE_NAME:$IMAGE_TAG|" k8s/app.yaml
                        GIT_NAME=$(echo "$GIT_IDENTITY" | sed -E 's/ <.*>//')
                        GIT_EMAIL=$(echo "$GIT_IDENTITY" | sed -E 's/.*<([^>]+)>.*/\1/')
                        git config user.name  "$GIT_NAME"
                        git config user.email "$GIT_EMAIL"
                        git add k8s/app.yaml
                        git commit -m "chore(ci): bump backend image tag to $IMAGE_TAG"
                    '''
                    // Store commit SHA to push after ArgoCD sync check
                    env.MANIFEST_COMMIT = sh(script: "git rev-parse HEAD", returnStdout: true).trim()
                }
            }
        }

        stage('Push to GitHub') {
            when { expression { env.SKIP_BUILD == 'false' } }
            steps {
                withCredentials([
                    string(credentialsId: 'github-pat', variable: 'GH_PAT')
                ]) {
                    sh '''
                        git push "https://x-access-token:${GH_PAT}@${GIT_REPO_URL}" HEAD:${GIT_BRANCH}
                    '''
                }
            }
        }

        stage('Deploy to Cluster') {
            steps {
                script {
                    env.KUBECONFIG = env.KUBECONFIG_PATH
                }
                sh '''
                    kubectl apply -f argocd/appset.yaml
                    kubectl -n argocd get applicationset demo-backend
                '''
            }
        }
    }

    post {
        success {
            script {
                if (env.SKIP_BUILD == 'false') {
                    echo "Deployment handled by ArgoCD (GitOps) - syncing ${env.IMAGE_NAME}:${env.IMAGE_TAG}"
                }
            }
        }
    }
}
