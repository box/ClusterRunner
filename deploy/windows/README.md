# Deploy ClusterRunner on Windows

We provide an option to deploy ClusterRunner on Windows via [Ansible](http://docs.ansible.com/ansible/intro.html).

## Prerequisites

### Prepare Your Machine

- Install Ansible on your machine (not Windows machines that will be running ClusterRunner). More about installing Anislbe can be found [here](http://docs.ansible.com/ansible/intro_installation.html).
- (optional) Install ClusterRunner on your machine (Linux or Mac). This is optional but handy if you want to send jobs to ClusterRunner from your machine.

### Prepare the Windows Machines

Ansible requires Windows machines to meet certain requirements to work. Two things specifically:
- Install Powershell 4.0 or higher.
- Install [Microsoft Visual C++ 2010 Redistributable Package (x86)](https://www.microsoft.com/en-us/download/details.aspx?id=5555).
- Run the [ConfigureRemotingForAnsible.ps1](https://github.com/ansible/ansible/blob/devel/examples/scripts/ConfigureRemotingForAnsible.ps1) on the Windows machines.
- More details about preparing the Windows machines for Ansible can be found [here](http://docs.ansible.com/ansible/intro_windows.html).

## Config Ansible for Your Environment

- Override files/clusterrunner.conf with your conf file that you want to deploy to all the Windows cluster nodes.
- Edit group\_vars/clusterrunner\_nodes.yml with proper username/password for your Windows nodes.
- Edit hosts file with more the information about the cluster (which node will be the master, which nodes will be the slaves, etc.)

## Deploy!

Type
```bash
make deploy
```
and enjoy ClusterRunner on Windows!
