---
layout: docs
title: Security
prev_section: _auto_
next_section: _auto_
permalink: /docs/security/
---

ClusterRunner was designed to be general-purpose (runs any shell command) and easy to
setup/operate (deploys across machines automatically, provides an HTTP REST API).  Any system with these properies
is going to raise security concerns, and ClusterRunner is no exception. Below are the security considerations you
should be aware of.

Message Authentication
----------------------

If an attacker could send arbitrary requests to a ClusterRunner slave, she could instuct the slave to clone any
repository and execute malicious commands from the repo's clusterrunner.yaml.  To defend against this, each API route
which could result in arbitrary command execution requires a hashed message authentication digest.  These
digests are generated using a shared secret, stored in clusterrunner.conf. **Slaves cannot communicate with a master
unless both machines have the same secret in their clusterrunner.conf.** Using ```clusterrunner deploy``` automatically
distributes the secret to slaves via SSH.

To protect the secret, ClusterRunner requires the permissions for clusterrunner.conf to be ```0x600```
(read/write for the owner only).

Deploying Slaves
----------------

ClusterRunner uses SSH to deploy slave services to remote machines when ```clusterrunner deploy``` is run. This requires
you to have passwordless SSH configured between the local machine and each slave, password-authenticated SSH is not an option.

<div class="note warning">
  <h5>Unknown host warnings ignored</h5>
  <p>Any "unknown host" warnings produced by SSH are ignored by default. If you are concerned that the identity
  of your slave hosts may be spoofed, set git_strict_host_key_checking = true in your
   ~/.clusterrunner/clusterrunner.conf file.  You will need to manually SSH to each slave first and approve its addition
   to known_hosts.
  </p>
</div>
