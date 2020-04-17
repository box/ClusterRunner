---
layout: docs
title: Integrating with CI
prev_section: _auto_
next_section: _auto_
permalink: /docs/ci-integration/
---

Operating at scale is where ClusterRunner really shines, and with ClusterRunner in your testing pipeline you can start taking fast feedback for granted.

Follow the steps below and you'll have a lovely Cluster of your own.

## Overview

Simply put, ClusterRunner integrates with your existing infrastructure by transforming CI slaves into ClusterSlaves,
and using the ClusterMaster as the entry-point for executing jobs.

From the users point of view, the CI systems behave exactly in the same way – just faster.

The change can be visualized in the following way:

<img src="/img/cr-arch-high-level2.png" width="100%">

## Prerequisites

Before you can set up a distributed cluster, there are a few things you need to take care of first:

1. Choose the hosts you'll use as a ClusterMaster and ClusterSlaves
1. Confirm SSH daemon running on all hosts in cluster
1. Exchange SSH keys between master/slaves
1. Exchange SSH keys with Git server

### 1. Take inventory of your CI executors

The first step when building out a Cluster is to know what machines you have available.

Take a bit of time to review your hosts, catalog their Operating Systems, and choose which one will be a
ClusterMaster and which will be ClusterSlaves.

<div class="note unreleased">
  <h5>Master & Slave Operating Systems</h5>
  <p>At this time the master and slaves must all use the same type of operating system. We plan to add support
  for heterogeneous environments in the future.</p>
</div>

### 2. Enable SSH access on hosts

#### OS X setup

To enable SSH on OS X, use these [instructions](https://support.apple.com/kb/PH13759).

#### Linux Setup

SSH access is enabled out-of-the-box for most Linux installs. If you find that it is not, please check the manual for your distro.

### 3. Exchange master/slave SSH keys

ClusterRunner relies on SSH to dynamically deploy and configure slaves. Password prompts will halt the
process.

#### OS X and Linux

Set up <a target="_blank" href="https://www.linuxproblem.org/art_9.html">passwordless SSH</a> between your
master and slaves.

<div class="note info">
    <p>It should take about a minute to manually exchange keys between the ClusterMaster and the first ClusterSlave (and faster for each subsequent slave). This is a one-time setup.</p>
</div>

### 4. Exchange SSH keys with Git

ClusterSlaves fetch code from your repository – and ClusterRunner uses SSH as the primary Git communication protocol.

In order for ClusterRunner to operate smoothly, we strongly recommend you exchange SSH keys between your slaves and your Git server.

<div class="note info">
    <p>For any Git infrastructure, we recommend you generate a single private key (~/.ssh/id_rsa) on your master, and then push that file to all of your slaves.</p>
</div>

#### GitHub

GitHub provides a comprehensive [set of instructions](https://help.github.com/articles/generating-ssh-keys/) for key exchange.

#### Self-hosted Git

Please refer to someone knowledgeable in the configuration of your Git service. Different Git services (git, gitolite, gitlab, etc.) handle user-key management in different ways, so we're unable to provide guidance for this step.

## Steps to Integrate ClusterRunner

### 1. Deploy and test the ClusterRunner service

To start your first distributed cluster, SSH to your ClusterMaster and run the commands below:

{% highlight bash %}
# Make sure you've done the "installation instructions" above

# Start the ClusterMaster process and specify the hostnames of your ClusterSlaves
~ $ clusterrunner deploy --slaves hostname1 hostname2 hostname3

# Run the tests for our "Simple job"
~ $ clusterrunner build git --url git@github.com:boxengservices/ClusterRunnerDemo.git --branch master --job-name Simple

# The exit code indicates success/failure!
{% endhighlight %}

<!--
<div class="note">
  <h5>Using CI to start up ClusterRunner</h5>
  <p>We recommend that you eventually have an automated process setup to start/keep-running your Cluster. This can
  be as easy as a CI job that executes the commands on your CR Master, or as thorough as a config rule (such as in
  Chef/Puppet) to keep the service alive.
  </p>
</div>
-->

Validate that the above "build" command was successful by checking the console output.

*Now take a moment to celebrate that you have an fully-functioning distributed test cluster. Hooray.*

### 3. Label your ClusterMaster

Triggering ClusterRunner jobs is done via executing CLI commands on the ClusterMaster. In order to do that, you must
identify the ClusterMaster in some way.

In Jenkins, this is done by editing the Node configuration as follows:

<center><img src="/img/ci-jenkins-label.png" height="150"></center>

### 4. Modify your jobs to use ClusterRunner

Now that you have an operating Cluster in place, it's time to reconfigure a CI job to leverage the resource.

#### 4.1 Invoke ClusterRunner

Transitioning a CI job to use ClusterRunner is incredibly simple – and often only a single line of code in your CI job:

{% highlight bash %}
~ $ clusterunner build git --url <url to git repo> --branch <branch> --hash <hash> --job-name <job name>
{% endhighlight %}

The "job name" represents any job you've defined in your project's [job configuration](/docs/job-configuration/).

The "hash" is optional.

<div class="note">
  <h5>Performance Hint</h5>
  <p>If you use the "--url" argument, your CI system does not need to check out your repo's code into the build workspace. (The ClusterMaster will do this automatically.)
  This can save you seconds of execution time!</p>
</div>

<div class="note info">
    <p>Don't forget to restrict this job to run only on CI nodes with the "cluster-master" label!</p>
</div>




#### 4.2 Publish build results in CI

Build results for any invocation of <code>clusterrunner build</code> are aggregated into the
<code>./build_results/</code> directory.

To consume these results, simply configure your CI system to publish the appropriate pattern of results in that
directory. In Jenkins, this looks like:

<center><img src="/img/ci-build-results.png" height="150"></center>

### 5. [optional] Unmount ClusterSlaves from your CI system

We recommend that you disconnect ClusterSlaves from your CI Master.

Since ClusterRunner wil be using these hosts to their full capacity, we recommend that you try to avoid running Jenkins
jobs on them directly while they are operating as ClusterSlaves.

<i>How we do it at Box: If you do choose to keep these mounted, we recommend adding a special label to them (such as
"clusterslave") so you can exclude them from other job definitions.</i>

### 6. Profit!

Sit back and enjoy the effects of ClusterRunners' capabilities.

As you increase your Cluster size and add more work to the system, you'll be amazed at how efficiently ClusterRunner
utilizes the resources you have available and provides faster test feedback.
