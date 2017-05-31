Quick setup for OS X
-----------
```bash
# clone repo
git clone https://github.com/box/ClusterRunner.git
cd ClusterRunner

# verify you have Python 3.4
brew update
brew install python3
python3 -V  # should be 3.4.x

# install pip, virtualenv, virtualenvwrapper if you don't have them
wget https://bootstrap.pypa.io/get-pip.py
python get-pip.py
pip install virtualenv
pip install virtualenvwrapper

# add the next two lines to your shell startup file (.bashrc, .profile, etc.)
export WORKON_HOME=$HOME/.virtualenvs  # add to .bashrc
source virtualenvwrapper.sh  # add to .bashrc

# create your ClusterRunner virtualenv
mkvirtualenv -p /usr/local/bin/python3.4 clusterrunner

# install ClusterRunner dependencies into virtualenv
workon clusterrunner
pip install -r dev-requirements.txt
```

Run tests
--------------
```bash
nosetests test/unit/
nosetests test/functional/

# or run the functional tests with verbose logging
export CR_VERBOSE=1
nosetests -s -v test/functional/
```
