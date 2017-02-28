## TODO for Dockerization

* User Guide/Docs in [Docker Hub](https://hub.docker.com/r/yamaszone/clusterrunner/) (Container usage scenarios with when and when not)
* Technical Docs (Workflow: DEV-TEST-STG-PROD, Build, Versioning, Support/Maintenance)
* Add more assertions for tests
* Add maintainer
* Lean-ify image (consider tiny base e.g. busybox, alpine, etc.)
* Reorganize directory structure (cleaner project root preferred)

## Requirements

* [Docker Engine](https://docs.docker.com/installation/) version 1.12.x+
* [Docker Compose](https://docs.docker.com/compose/) version 1.11.x+ with API version 2.1


## Prerequisite Setup

#### Install docker-compose on CoreOS
```sh
$ sudo su -
$ curl -L https://github.com/docker/compose/releases/download/1.11.2/docker-compose-`uname -s`-`uname -m` > /opt/bin/docker-compose
$ chmod +x /opt/bin/docker-compose
```

