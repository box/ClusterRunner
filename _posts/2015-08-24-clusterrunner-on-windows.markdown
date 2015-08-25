---
layout: news_item
title: 'ClusterRunner Now Supports Windows!'
date: 2015-08-24 10:00:00 -0800
author: aptxkid
categories: [release]
---
Tests are usually tightly coupled with test environments in some way. If you're building an iOS app, you test the app on iOS. ClusterRunner parallelizes tests execution on a cluster of machines to bring you the fastest test feedback possible. But it only supports Linux and Mac. What if you are building an app on Windows and want fastest test feedback on Windows as well?

Today, I am glad to announce that ClusterRunner officially supports Windows as well as Linux and Mac! Here are some highlights.

### Easy Ansible Deployable

![deploy](/img/cr-windows-deploy.png)

We make few assumptions on the target Windows machines being deployed to. Windows doesn't support SSH natively. We provide an Ansible playbook so you can deploy ClusterRunner to a Windows Cluster with a single command!

### CI on Appveyor

![appveyor](/img/cr-appveyor.png)

We are all very familiar with Travis-CI, which provides Linux testing infrastructure for our Github projects. Appveyor is Travis-CI for Windows. We set it up to prevent any regressions on Windows. All tests (unit, functional, integration) get kicked off on every Pull Request and Merge.

### Easy Install

ClusterRunner tries to make installation really easy. We borrowed the idea from [Chocolatey](https://chocolatey.org/), that all you need to do to install ClusterRunner on Windows is to run this command on your Windows machine (no git clone required!):

{% highlight bash %}
C:\> @powershell -NoProfile -ExecutionPolicy Bypass -Command "iex ((new-object net.webclient).DownloadString('https://cloud.box.com/shared/static/snpz1xcan76rpy112rdu33xjrvdmkcnk.ps1'))"
{% endhighlight %}

### Enjoy!!
