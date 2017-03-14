## TODO for Dockerization
* Add maintainer
  - Maintainer for CR Dockerfile needs to be added after pull request is merged. Ideally the maintainer should be someone from official team with appropriate Docker Hub permission to tag image as `box/clusterrunner:latest`. I can volunteer if needed but will require collaborator permission for Docker Hub.
* Lean-ify image (consider tiny base e.g. busybox, alpine, etc.)
  - Currently `Dockerfile.src` uses `python:3.4-slim` as the base. I attempted `python:alpine` as the base but it didn't feel like worth the [trouble](https://github.com/docker/docker/issues/27940). My docker version is `1.12.6` but the problem might have been fixed in `1.13.0+`. I will revisit this in the future.
* Reorganize directory structure (cleaner project root preferred)
  - I was considering potential restructure of CR project root directory similar to [this](https://gist.github.com/yamaszone/6a4304069652a4a01ecdacdd4e7c7df1) so that:
    - Only relevant project artefacts can be easily added into Docker image excluding non-PROD dependencies like tests, docs, Dockerfiles, docker-compose.yaml, and so on...
    - Non-PROD tools/libs installation inside Docker container is excluded by splitting `requirements.txt` into `requirements-prod.txt` and `requirements-non-prod.txt` to deal with security/maintenance aspects of production dependencies as a priority basis 
    - Readability can be improved
    - ... :)
  - I will hold off on this as it will potentially require breaking changes. Also allowing more time to rethink this!

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
