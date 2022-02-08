library("jenkins-pipeline-library")

pipeline {
    agent { label 'docker' }

    stages {
        stage('Build') {

            steps {
                sh 'make clean docker-rpm'
            }
        }
        stage('Release') {
            steps {
                script {
                    def rpmFiles = findFiles(glob: 'dist/*.rpm').each { f -> f.path }
                    publishRPM(fileList: rpmFiles, repoName: 'productivity', repoPath: 'com/box/clusterrunner', noRpmNamePath: true)
                }
            }
        }
    }
}
