[![Project Status](http://opensource.box.com/badges/active.svg)](http://opensource.box.com/badges)
[![Build Status](https://travis-ci.org/box/ClusterRunner.svg?branch=master)](https://travis-ci.org/box/ClusterRunner)
[![Build status](https://ci.appveyor.com/api/projects/status/gwei54m8anlbxwhn/branch/master?svg=true)](https://ci.appveyor.com/project/josephharrington/clusterrunner)
[![Coverage Status](https://coveralls.io/repos/box/ClusterRunner/badge.svg?branch=master)](https://coveralls.io/r/box/ClusterRunner?branch=master)

# ClusterRunner

ClusterRunner makes it easy to execute test suites across your infrastructure in the fastest and most efficient way possible.

By using ClusterRunner in your testing pipeline, you will be able to easily:

- Make long-running, single-threaded test jobs run in parallel.
- Consistently utilize 100% of your testing infrastructure.
- Get test feedback faster.
- Completely isolate tests from each other, avoiding nasty global state.

The entire process of installing, initializing, and executing tests through ClusterRunner should take about 8 minutes!

Give it a shot by starting at our [documentation](https://www.clusterrunner.com) site.

## Read the Docs

You can find all our official documentation at [clusterrunner.com](https://www.clusterrunner.com).

- [Getting Started](https://www.clusterrunner.com/docs/home/)
- [Tutorials](https://www.clusterrunner.com/docs/configuring-your-project/)

For a quick visual overview, check out the [infographic][1] we presented at the PyCon 2015 poster session:

<p align="center">
<img src="https://cloud.box.com/shared/static/7a14br3d73in7vb75278090tnni78rag.jpg" width="350px">
</p>

## Visualize

ClusterRunner currently has no built-in UI, but its extensive API allows you to create detailed dashboards so you
can monitor your cluster and see what it's doing.
 
We've open-sourced a few of the dashboards we use internally at Box for monitoring our own clusters. Check out the
[ClusterRunner-Dashboard](https://github.com/box-labs/ClusterRunner-Dashboard) repo for the code and documentation.

<a href="https://github.com/box-labs/ClusterRunner-Dashboard" target="_blank"><p align="center">
<img src="https://cloud.box.com/shared/static/kh4gdu7u3chl61o1k5ljtx5d2wbirx9h.gif" width="400px">
<img src="https://cloud.box.com/shared/static/vy0o8oajkud3pf5e8bw1oiifbhgmw255.png" width="400px">
</p></a>

## Contribute

We :heart: external contributors! You can run ClusterRunner entirely locally and it has a comprehensive functional test suite, so
it's easy to get started. Take a look at our open issues to get an idea of where you can help out.

- [Developer Setup](/test/README.md)
- [Development Guide](https://www.clusterrunner.com/docs/development-guide/)
- [Open Issues](https://github.com/box/ClusterRunner/issues)

## Get Help

We're happy to answer any questions you have around setting up ClusterRunner in your own org. Create a [new issue](https://github.com/box/ClusterRunner/issues/new) on this repo, or email oss@box.com and be sure to include 
"ClusterRunner" in the subject.

## Copyright and License

Copyright 2014 Box, Inc. All rights reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.


[1]: https://raw.githubusercontent.com/box/ClusterRunner/gh-pages/img/clusterrunner_pycon_poster_2015.jpg
