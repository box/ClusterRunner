---
layout: docs
title: Installation
prev_section: home
next_section: _auto_
permalink: /docs/installation/
---

We've done our best to make installing ClusterRunner insanely fast and easy.  This should take less than a minute.

## Install self-contained package
Pick a set of instructions based on your operating system.

**OS X**

{% highlight bash %}
~ $ mkdir -p ~/.clusterrunner/dist && cd ~/.clusterrunner && curl -L https://cloud.box.com/shared/static/pqln47ur9ektad5hxq4a.tgz > clusterrunner.tgz && tar -zxvf clusterrunner.tgz -C ./dist && cp ./dist/conf/default_clusterrunner.conf clusterrunner.conf && chmod 600 clusterrunner.conf
{% endhighlight %}

**Linux**

{% highlight bash %}
~ $ mkdir -p ~/.clusterrunner/dist && cd ~/.clusterrunner && curl -L https://cloud.box.com/shared/static/2pl4pi6ykvrbb9d06t4m.tgz > clusterrunner.tgz && tar -zxvf clusterrunner.tgz -C ./dist && cp ./dist/conf/default_clusterrunner.conf clusterrunner.conf && chmod 600 clusterrunner.conf
{% endhighlight %}

**Windows**

- Download ClusterRunner from [here](https://cloud.box.com/shared/static/u91zg1fmmlxo2reqo8mwi3hjv7kaeazz.zip)
- Unzip to %HOME%\\.clusterrunner\\dist
- Copy .\\dist\\conf\\default\_clusterrunner.conf to clusterrunner.conf inside .clusterrunner folder

## Bash Alias

We suggest you add an alias for the clusterrunner binary to your shell startup file in order to easily execute ClusterRunner.

{% highlight bash %}
# Add this line to your ~/.bash_profile:
~ $ alias clusterrunner='~/.clusterrunner/dist/clusterrunner'
{% endhighlight %}

