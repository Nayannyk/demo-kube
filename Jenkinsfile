pipeline {
    agent any

    environment {
        REGISTRY   = 'localhost:5000'
        IMAGE      = 'localhost:5000/demo-backend'
        GIT_BRANCH = 'main'
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
                    echo "Building ${IMAGE}:${env.IMAGE_TAG}"
                }
                sh 'docker build -t "$IMAGE:$IMAGE_TAG" app/'
            }
        }

        stage('Push Image') {
            when { expression { env.SKIP_BUILD == 'false' } }
            steps {
                sh 'docker push "$IMAGE:$IMAGE_TAG"'
            }
        }

        stage('Update Manifest & Commit') {
            when { expression { env.SKIP_BUILD == 'false' } }
            steps {
                script {
                    sh '''
                        sed -i "s|image: $IMAGE:.*|image: $IMAGE:$IMAGE_TAG|" k8s/app.yaml
                        git config user.name  "jenkins-cd"
                        git config user.email "jenkins@demo.local"
                        git add k8s/app.yaml
                        git commit -m "chore(ci): bump demo-backend image tag to $IMAGE_TAG"
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
                        git push "https://x-access-token:${GH_PAT}@github.com/Nayannyk/demo-kube.git" HEAD:main
                    '''
                }
            }
        }
    }

    post {
        success {
            script {
                if (env.SKIP_BUILD == 'false') {
                    echo "Deployment handled by ArgoCD (GitOps) - syncing ${env.IMAGE}:${env.IMAGE_TAG}"
                }
            }
        }
    }
}
