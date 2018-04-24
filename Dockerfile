#
# Docker workflow for building and packaging ClusterRunner to an RPM.
#

# STAGE 1: Official PEP 513 Python Manylinux (RHEL5) base with Python 3.4 enabled to create
#          linux_x86_64 pex.
FROM quay.io/pypa/manylinux1_x86_64:latest AS stage1
ENV PATH="/opt/python/cp34-cp34m/bin:${PATH}"

WORKDIR /ClusterRunner

COPY Makefile *requirements.txt ./
RUN make init-dev wheels

COPY . .
RUN make dist/clusterrunner

# STAGE 2: CentOS 7 base w/ fpm to package pex into an rpm.
FROM cdrx/fpm-centos:7 AS stage2
WORKDIR /root
COPY . .
COPY --from=stage1 /ClusterRunner/dist/clusterrunner ./dist/
COPY --from=stage1 /ClusterRunner/clusterrunner.egg-info/PKG-INFO ./clusterrunner.egg-info/
RUN make rpm
