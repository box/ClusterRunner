#!/usr/bin/env python3

from pip.req import parse_requirements
from setuptools import find_packages, setup

from app.util import autoversioning

version = autoversioning.get_version()
autoversioning.write_package_version_file(version)

# bdist_pex runs in a temp dir, therefore requirements.txt must be added to data_files.
requirements = [str(r.req) for r in parse_requirements('requirements.txt', session=False)]

name = 'clusterrunner'

setup(
    name=name,
    version=version,
    description="ClusterRunner makes it easy to execute test suites across your "
                "infrastructure in the fastest and most efficient way possible.",
    maintainer="Box",
    maintainer_email="productivity@box.com",
    url="https://github.com/box/ClusterRunner",
    license="ASL 2.0",

    python_requires='>=3.4',
    packages=find_packages(exclude=('test', 'test.*')),
    # Data files are packaged into the wheel using the following defines.
    data_files=[
        ('', ['requirements.txt']),
        ('bin', ['bin/git_askpass.sh', 'bin/git_ssh.sh']),
        ('conf', ['conf/default_clusterrunner.conf']),
    ],
    install_requires=requirements,
    entry_points={
        'console_scripts': ['{} = app.__main__:main'.format(name)],
    },
)

autoversioning.restore_original_package_version_file()
