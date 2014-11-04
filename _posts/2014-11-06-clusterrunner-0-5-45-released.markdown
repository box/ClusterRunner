---
layout: news_item
title: 'Easy Fast Test Feedback with ClusterRunner'
date: 2014-11-06 10:00:00 -0800
author: timbozo
categories: [news]
---
Delivering fast test feedback is a common challenge for rapidly-growing projects and engineering teams. And every engineer knows that when we're spending time waiting for test results, we're not spending time doing what matters: writing awesome code.  

<img style="float:right; width:150px; margin-left:10px; margin-bottom:20px;" src="/img/box_clusterrunner_lrg.png">

At Box, the Tools & Frameworks team (owners of the Box [SDLC](http://en.wikipedia.org/wiki/Software_development_process) machinery) takes pride in trying to give engineers the right information, right away, whenever they need it. To achieve this, we built [ClusterRunner](http://www.clusterrunner.com), a tool that allows us to easily run any test job while promising to provide the fastest and most efficient results. And today we're happy to announce that we've open sourced it.

Our approach to building ClusterRunner was shaped by a handful of factors present at Box:

- Diversity of languages (PHP, Scala, Python, Node/JS)
- 100,000+ tests of many different types
- 1500+ test suite invocations per day
- New test jobs and test technologies added regularly

In order to add value across all our teams, we needed a platform that was programming language agnostic, supported any test technology<sup><a href="#1">[1]</a></sup>, could run a huge number of tests, and worked well under load. With those requirements in place, we began building ClusterRunner to make it super easy to horizontally scale your test execution, guided by the principle "Do one thing, and do it well."  

To keep the product simple and agile, we focused entirely on the core clustering technology, a robust set of RESTful APIs, skipping web interfaces, and making an easy-to-use (API consuming) command-line client—all while valuing performance above all else. The idea being that whenever you type a command to run a test, ClusterRunner provides a drop-in replacement for that command with no extra fluff and super low overhead.

ClusterRunner has been put to the test<sup><a href="#2">[2]</a></sup> here at Box. For our largest project, with more than 60,000 tests (that take roughly 8 hours to run if invoked normally), ClusterRunner delivers feedback in less than 4 minutes. As the test suite continues to grow, we can simply scale infrastructure to keep feedback fast. 

## Architecture
At the heart of ClusterRunner is the concept of "atomization," the idea of taking a single command, breaking it into many smaller commands, and then horizontally distributing those "atoms." Once ClusterRunner has individual atoms in hand, it begins to store and analyze metadata associated with those atoms (historical test times, overall suite runtime, overhead on test commands, etc.) to build an image of the best execution strategy for your tests now and in the future. The "ClusterMaster" handles these responsibilities, which are then distributed to the "ClusterSlaves" as visualized below:

![test](/img/cr-blog-atomization.png)

ClusterRunner's ability to manage a fleet of ClusterSlaves allows us to scale any test job dynamically as machine capacity changes. The value of this approach can be described in a simple use case: multiple requests are queued, jobs start and then scale even before the previous job is completely done. 

At first it seems obvious and simple to just "always run tests on available nodes" and "run a bunch of tests individually," but we actually found this pretty challenging to get right while still keeping it both performant and easy to use. ClusterRunner strives to abstract away those complications while giving you a set of easy and intuitive interfaces.

## Wrapping Up

If your team is already running at scale, the value of ClusterRunner is it's ability to speed up test feedback while using test infrastructure efficiently. If you're just starting up, ClusterRunner can guarantee your test feedback stays quick as your teams (and test suites!) grow. Regardless of your organization size, ClusterRunner can enable you to deliver fast test results while making it easy to keep them fast over the long-haul. 

Get started at [clusterrunner.com](http://www.clusterrunner.com/)

## Footnotes

<a name="1">[1]</a> Mobile testing are a bit of an outlier in the testing world - at this time we can't promise ClusterRunner will help you with running iOS or Android tests (although if it works for you, let us know!)

<a name="2">[2]</a> ... [put to the test](/img/meme-duck.gif)...
