pipeline {
    agent { label 'rosie' }

    stages {
        stage('Build') {
            steps {
                sh 'make docker-rpm'
            }
        }
        stage('Release') {
            steps {
                withCredentials([usernameColonPassword(credentialsId: 'artifactory', variable: 'ARTIFACTORY')]) {
                    sh 'make docker-release'
                }
            }
        }
    }
}
