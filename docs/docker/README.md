## TODO for Dockerization
* Add maintainer
* Lean-ify image (consider tiny base e.g. busybox, alpine, etc.)
* Reorganize directory structure (cleaner project root preferred)

## User Guide
#### Usage Scenarios
[ClusterRunner container](https://hub.docker.com/r/yamaszone/clusterrunner/) is a good choice if your application runtime environment supports [Docker Engine](https://docs.docker.com/engine/installation/). For example, if your application under test is running on macOS with Docker Engine installed, then you can easily use the ClusterRunner Docker container to run tests in parallel. 
To see ClusterRunner CLI help, run the following command:

`docker run --rm -v /path/to/system/under/test:/sut -w /sut yamaszone/clusterrunner:bin -h`

See [Quick Start](http://www.clusterrunner.com/docs/quickstart/) guide to configure your project to use ClusterRunner.

**NOTE**: ClusterRunner container is yet to add parallel testing support easily for applications that run as containers.

## Developer Guide
Currently we are maintaining two flavors of Dockerfiles for ClusterRunner: 
* `Dockerfile.bin`: Build ClusterRunner image from binary with minimal image size
* `Dockerfile.src`: Build ClusterRunner image from source
In the future, we plan to maintain `Dockerfile.src` only after simplifying some dependencies mentioned [here](https://github.com/box/ClusterRunner/issues/328).

#### Requirements
* [Docker Engine](https://docs.docker.com/engine/installation/) version 1.12.x+
* [Docker Compose](https://docs.docker.com/compose/) version 1.11.x+ with API version 2.1

#### Requirements Setup
* Install docker-compose on CoreOS
```sh
$ sudo su -
$ curl -L https://github.com/docker/compose/releases/download/1.11.2/docker-compose-`uname -s`-`uname -m` > /opt/bin/docker-compose
$ chmod +x /opt/bin/docker-compose
```
* For other platforms, see instructions [here](https://docs.docker.com/compose/install/)
```
$ curl -L "https://github.com/docker/compose/releases/download/1.11.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
$ chmod +x /usr/local/bin/docker-compose
```

#### Development/Test Workflow
We use `docker-compose` to maintain two flavors of Docker images: `docker-compose-bin.yml` for `Dockerfile.bin` and `docker-compose-src.yml` for `Dockerfile.src`. Project root contains a convenient script `run-cr` to easily build/test/push Docker images (see `./run-cr help`):
* Build
  - Run `./run-cr build` to build both flavors of ClusterRunner containers
* Test
  - Run `./run-cr test-bats` to run sanity tests for the ClusterRunner containers. We use lightweight [BATS](https://github.com/sstephenson/bats) framework to write automated tests (see `test/bats`) for the ClusterRunner images.
* Push
  - Run `./run-cr push` to push ClusterRunner images to Docker Hub
* Image Versions
  - Currently [ClusterRunner images](https://hub.docker.com/r/yamaszone/clusterrunner/tags/) are tagged as `bin` and `src`. To improve maintainability of these images, we will concatenate ClusterRunner versions with the container tags in the future.
