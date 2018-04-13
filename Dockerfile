#
# Docker workflow for building and packaging ClusterRunner to an RPM.
#

# STAGE 1: Official PEP 513 Python Manylinux (RHEL5) base with Python 3.4 enabled to create
#          linux_x86_64 pex.
#          NOTE: To update image run: "docker pull quay.io/pypa/manylinux1_x86_64:latest"
FROM quay.io/pypa/manylinux1_x86_64@sha256:1fc8ee3bc9d668222a519d84d8c3b3e2bbc3eabe4595a1661d7b037a038d2e87 AS stage1
ENV PATH="/opt/python/cp34-cp34m/bin:${PATH}"

WORKDIR /ClusterRunner

COPY Makefile *requirements.txt ./
RUN make init-dev wheels

COPY . .
RUN make dist/clusterrunner

# STAGE 2: CentOS 7 base w/ fpm to package pex into an rpm.
#          NOTE: To update image run: "docker pull cdrx/fpm-centos:7"
FROM cdrx/fpm-centos@sha256:fd314b5b8fdc78f714ba6d3e83d45ae58dd8dfff7f21320e55ec854587b01c2f AS stage2
WORKDIR /root
COPY . .
COPY --from=stage1 /ClusterRunner/dist/clusterrunner ./dist/
COPY --from=stage1 /ClusterRunner/clusterrunner.egg-info/PKG-INFO ./clusterrunner.egg-info/
RUN make rpm
