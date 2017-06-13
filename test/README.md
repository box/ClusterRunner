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
pyenv install 3.4.5  # use latest 3.4.X

# Use pyenv-virtualenv to manage venvs (https://github.com/pyenv/pyenv-virtualenv)
brew install pyenv-virtualenv
echo 'eval "$(pyenv virtualenv-init -)"' >> ~/.bash_profile  # replace .bash_profile with whatever you use (.bashrc, .profile, etc.) 

# Create a virtualenv for ClusterRunner
cd ClusterRunner
pyenv virtualenv 3.4.5 cr
pyenv local cr  # auto-activate virtualenv when entering this directory
make init-dev
```


Set up Python 3.4 using virtualenv (outdated!)
----------------
```bash
# Install Python 3.4
brew update
brew install python3  # Note! This is now out of date and will install a later version of python. :(
python3 -V  # should be 3.4.x

# Install pip, virtualenv, virtualenvwrapper if you don't have them
wget https://bootstrap.pypa.io/get-pip.py
python get-pip.py
pip install virtualenv
pip install virtualenvwrapper

# Add the next two lines to your shell startup file (.bashrc, .profile, etc.)
export WORKON_HOME=$HOME/.virtualenvs  # add to .bashrc
source virtualenvwrapper.sh  # add to .bashrc

# Create your ClusterRunner virtualenv
mkvirtualenv -p /usr/local/bin/python3.4 clusterrunner

# Install ClusterRunner dependencies into virtualenv
workon clusterrunner
make init-dev
```
