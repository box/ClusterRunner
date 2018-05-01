pipeline {
    agent none

    stages {
        stage('Build') {
            agent { label 'rosie' }
            steps {
                sh 'make clean docker-rpm'

                // Copy the RPM and PKG-INFO file to the next stage.
                stash name: 'rpm', includes: 'dist/*.rpm'
                stash name: 'pkg-info', includes: 'clusterrunner.egg-info/PKG-INFO'
            }
        }
        stage('Release') {
            agent { label 'pe-builder' }
            steps {
                // Write the RPM and PKG-INFO file from the previous stage.
                unstash 'rpm'
                unstash 'pkg-info'

                sh 'make release-signed'
            }
        }
    }
}
