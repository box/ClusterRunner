Quick setup for OS X
-----------
```bash
# Clone repo
git clone https://github.com/box/ClusterRunner.git
cd ClusterRunner

# Create a Python 3.4 virtualenv using your preferred method.
# See below for steps on doing this via Pyenv.

# Install ClusterRunner dependencies
make init-dev
```


Run tests
--------------
```bash
make test
# or...
nosetests test/unit/
nosetests test/functional/

# or run the functional tests with verbose logging
export CR_VERBOSE=1
nosetests -s -v test/functional/
```

Run tests in docker (no need for any setup on local machine)
--------------
```bash
make docker-test
# or...
docker build --target builder -t productivity/clusterrunner-tests -f Dockerfile .
docker run --rm productivity/clusterrunner-tests make lint
docker run --rm productivity/clusterrunner-tests make test-unit
docker run --rm productivity/clusterrunner-tests test-integration
docker run --rm productivity/clusterrunner-tests test-functional

# or run the functional tests with verbose logging
docker build --target builder -t productivity/clusterrunner-tests -f Dockerfile .
docker run -e CR_VERBOSE=1 --rm productivity/clusterrunner-tests nosetests -s -v test/functional/
```


Set up Python 3.4 using Pyenv
---------------
This is the preferred method since installing Python 3.4 via Homebrew is no longer easy.
```bash
# Install pyenv (Instructions from https://github.com/pyenv/pyenv#installation)
brew update
brew install pyenv

# Add pyenv init to your shell startup file
echo 'eval "$(pyenv init -)"' >> ~/.bash_profile  # replace .bash_profile with whatever you use (.bashrc, .profile, etc.)

# Install Python 3.4
pyenv install 3.4.8  # use latest 3.4.X

# Use pyenv-virtualenv to manage venvs (https://github.com/pyenv/pyenv-virtualenv)
brew install pyenv-virtualenv
echo 'eval "$(pyenv virtualenv-init -)"' >> ~/.bash_profile  # replace .bash_profile with whatever you use (.bashrc, .profile, etc.)

# Create a virtualenv for ClusterRunner
cd ClusterRunner
pyenv virtualenv 3.4.8 cr
pyenv local cr  # auto-activate virtualenv when entering this directory
make init-dev
```
