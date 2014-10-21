---
layout: docs
title: Features
prev_section: _auto_
next_section: _auto_
permalink: /docs/features/
---


### So what is ClusterRunner?

ClusterRunner is a tool designed to serve a single, critical purpose - to execute tests in the fastest way possible.


#### What we do

1. Simple, expressive interfaces to define and trigger jobs
2. Manage the status of a worker-node fleet
3. Real-time scaling of job-clusters based on fleet availability
4. Uses historic test-execution data to optimize cluster-groupings
5. Aggregate and return test result artifacts

#### What we don't do
We've specifically avoided trying to replace functionality provided by the common CI platforms 
(Jenkins/Travis/etc).  This includes:

1. Process and present the results of a job
2. Manage relationships between test jobs
3. Schedule the execution of jobs
4. ... many other CI things.

In summary, whenever you run a test by calling a shell command, ClusterRunner can likely execute those same tests 
faster, safer, and more efficiently.
