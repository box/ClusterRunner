---
layout: docs
title: Quick Start
prev_section: _auto_
next_section: _auto_
permalink: /docs/quickstart/
---

Now that you've installed ClusterRunner it's time to get down to business.

In this section we'll leverage the [ClusterRunnerDemo](https://github.com/boxengservices/ClusterRunnerDemo) project to
show you how the pieces fit together.  After playing with this demo you'll be ready hook ClusterRunner into your own
projects and pipelines.

### Running tests on localhost
The easiest way to try out ClusterRunner is on a single machine - with a master and slave running locally.


{% highlight bash %}
# Grab the demo project
~ $ git clone git@github.com:boxengservices/ClusterRunnerDemo.git ~/ClusterRunnerDemo/
~ $ cd ~/ClusterRunnerDemo

# Run the tests for our "Simple" job
~ $ clusterrunner build --job-name Simple

# The exit code indicates success/failure!
# Navigate to ./build_results/ to view the artifacts.
{% endhighlight %}

It's that easy!
 
You've just seen a ClusterMaster and ClusterSlave work together, and have run the tests defined by the demo project's
"Simple" job.

<div class="note info">
    <p>If you'd like to see what work the "Simple" job is defined to do, open up 
    <a href="https://github.com/boxengservices/ClusterRunnerDemo">ClusterRunnerDemo/clusterrunner.yaml</a> and take a look.</p>
</div>

Using these basic principles you can begin to leverage the power of ClusterRunner.

Next, we'll go through a tutorial where we [define our own ClusterRunner job](/docs/configuring-your-project). 
