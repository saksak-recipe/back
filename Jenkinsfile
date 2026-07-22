pipeline {
    agent any

    environment {
        GIT_URL = 'https://github.com/saksak-recipe/back.git'
        DOCKER_IMAGE = 'augustzer0/saksak'
        GIT_CRED_ID = 'github-login'
        DOCKER_CRED_ID = 'dockerhub-login'
        ENV_CRED_ID = 'saksak-env-file'
        DISCORD_CRED_ID = 'discord-webhook-url'
        DEPLOY_PATH = '/home/augustzer0/zer0/saksak'
    }

    stages {
        stage('1. Checkout') {
            steps {
                echo 'Checkout saksak-recipe/back main'
                git branch: 'main', credentialsId: "${GIT_CRED_ID}", url: "${GIT_URL}"
            }
        }

        stage('2. Create .env File') {
            steps {
                script {
                    echo 'Materialize workspace .env from Secret File (not DEPLOY_PATH)'
                    withCredentials([file(credentialsId: "${ENV_CRED_ID}", variable: 'SECRET_ENV')]) {
                        sh 'cp "$SECRET_ENV" .env'
                    }
                }
            }
        }

        stage('3. Build Image') {
            steps {
                echo "Build ${DOCKER_IMAGE}:latest"
                sh "docker build -t ${DOCKER_IMAGE}:latest ."
            }
        }

        stage('4. Test (pytest)') {
            steps {
                echo 'Run pytest inside ephemeral container (dev group)'
                sh """
                    docker run --rm ${DOCKER_IMAGE}:latest \
                      sh -c "uv sync --frozen --group dev --no-cache && uv run pytest"
                """
            }
        }

        stage('5. Push to Docker Hub') {
            steps {
                script {
                    echo "Push ${DOCKER_IMAGE}:latest"
                    withCredentials([usernamePassword(
                        credentialsId: "${DOCKER_CRED_ID}",
                        usernameVariable: 'DOCKER_USER',
                        passwordVariable: 'DOCKER_PW'
                    )]) {
                        sh 'echo "$DOCKER_PW" | docker login -u "$DOCKER_USER" --password-stdin'
                        sh "docker push ${DOCKER_IMAGE}:latest"
                    }
                }
            }
        }

        stage('6. Migrate (alembic)') {
            steps {
                dir("${DEPLOY_PATH}") {
                    echo 'Pull app image and run alembic upgrade head'
                    sh 'docker compose pull app'
                    sh 'docker compose run --rm app uv run alembic upgrade head'
                }
            }
        }

        stage('7. Deploy (compose app)') {
            steps {
                dir("${DEPLOY_PATH}") {
                    echo 'Recreate app service only'
                    sh 'docker compose up -d app'
                    sh 'docker image prune -f'
                }
            }
        }

        stage('8. Health Check') {
            steps {
                script {
                    echo 'Wait then probe FastAPI inside saksak-back'
                    sleep 10
                    sh '''
                        docker exec saksak-back python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')"
                    '''
                }
            }
        }
    }

    post {
        always {
            echo 'Remove workspace secrets and local docker login session'
            sh 'rm -f .env discord-payload.json'
            sh 'docker logout || true'
        }
        success {
            script {
                withCredentials([string(credentialsId: "${DISCORD_CRED_ID}", variable: 'DISCORD_WEBHOOK')]) {
                    writeFile file: 'discord-payload.json', text: """{
  "embeds": [{
    "title": "saksak-backend deploy success",
    "color": 5763719,
    "description": "Build #${env.BUILD_NUMBER} succeeded.\\n${env.BUILD_URL}"
  }]
}"""
                    sh 'curl -sS -X POST -H "Content-Type: application/json" -d @discord-payload.json "$DISCORD_WEBHOOK"'
                    sh 'rm -f discord-payload.json'
                }
            }
        }
        failure {
            script {
                withCredentials([string(credentialsId: "${DISCORD_CRED_ID}", variable: 'DISCORD_WEBHOOK')]) {
                    writeFile file: 'discord-payload.json', text: """{
  "embeds": [{
    "title": "saksak-backend deploy FAILED",
    "color": 15548997,
    "description": "Build #${env.BUILD_NUMBER} failed.\\nSummary: check console for failed stage.\\nBuild: ${env.BUILD_URL}\\nConsole: ${env.BUILD_URL}console"
  }]
}"""
                    sh 'curl -sS -X POST -H "Content-Type: application/json" -d @discord-payload.json "$DISCORD_WEBHOOK"'
                    sh 'rm -f discord-payload.json'
                }
            }
        }
    }
}
