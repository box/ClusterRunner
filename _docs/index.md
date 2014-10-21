---
layout: docs
title: Welcome
next_section: installation
permalink: /docs/home/
---

ClusterRunner makes it easy to execute test suites across your infrastructure in the fastest and most efficient way 
possible.

By using ClusterRunner in your testing pipeline, you will be able to easily:

* Make linear (i.e.: single-threaded) test jobs run in parallel
* Consistently utilize 100% of your testing infrastructure
* Get test feedback faster

In other words, if you ever find yourself typing:

{% highlight bash %}
~ $ phpunit test/
~ $ nose test/
~ $ sbt test
{% endhighlight %}
	
... we recommend you start typing:
	
{% highlight bash %}
~ $ clusterrunner build --job-name <job name>
{% endhighlight %}

# Give it a shot

The entire process of installing, initializing, and executing tests through ClusterRunner should take about 8 minutes!

<center><i>Just hit "Next" to begin.</i></center>