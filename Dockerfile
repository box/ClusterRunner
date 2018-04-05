#
# Docker workflow for building and packaging ClusterRunner to an RPM.
#

# STAGE 1: Python-Manylinux (RHEL5) base with Python 3.4 enabled to create linux_x86_64 pex.
FROM quay.io/pypa/manylinux1_x86_64@sha256:1fc8ee3bc9d668222a519d84d8c3b3e2bbc3eabe4595a1661d7b037a038d2e87 AS stage1
ENV PATH="/opt/python/cp34-cp34m/bin:${PATH}"

WORKDIR /ClusterRunner

COPY Makefile *requirements.txt ./
RUN make init-dev wheels
COPY . .
RUN make dist/clusterrunner

# STAGE 2: CentOS 7 base w/ fpm to package pex into an rpm.
FROM cdrx/fpm-centos:7

WORKDIR /root
RUN yum install epel-release -y && yum install git python34 python34-pip -y
COPY . .
COPY --from=stage1 /ClusterRunner/dist/clusterrunner ./dist/
RUN ./setup.py --version
RUN make rpm
