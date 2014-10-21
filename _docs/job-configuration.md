---
layout: docs
title: Job Configuration
prev_section: _auto_
next_section: _auto_
permalink: /docs/job-configuration/
---


ClusterRunner jobs are defined via <code>clusterrunner.yaml</code>, a file that lives in the root of 
your project. All configuration is done in shell.

There are only two required sections in the configuration file other than the job name, 
which is the root element for that yaml section. You can configure multiple jobs in 
<code>clusterrunner.yaml</code>.

<div class="mobile-side-scroller">
<table>
  <thead>
    <tr>
      <th>Setting</th>
      <th>Description</th>
    </tr>
  </thead>
  <tbody>
    <tr class="setting">
      <td>
        <p class="name"><strong>job name</strong></p>
        <p>string</p>
      </td>
      <td>
        <p>The name of the defined job. The job name should be unique within this file. Unlike 
        the other yaml sections, the job name itself is the key yaml element, and isn’t the value.</p>
      </td>
    </tr>
    <tr class="setting">
      <td>
        <p class="name"><strong>commands</strong></p>
        <p>list, multi-line ok</p>
      </td>
      <td>
        <p>The shell commands to execute a single test. Any build artifact generation should 
        be done here. If any command here exits with a non-zero exit code, the test will be marked as a failure.</p>
      </td>
    </tr>
    <tr class="setting">
      <td>
        <p class="name"><strong>atomizers</strong></p>
        <p>- VARIABLE: &lt;command&gt;</p>
      </td>
      <td>
        <p>The shell command to find all of the units of work, or ‘atoms’, that will be run in the commands section. 
        Each line output to stdout by this command will be set as the value for the environment variable specified 
        to the left.</p>
        <p>This exported environment variable will be available in all lines of the <i>commands</i> section.</p>
        <p>ClusterRunner currently only supports one variable being set in the <i>atomizers</i> section.</p>
      </td>
    </tr>
    <tr class="setting">
      <td>
        <p class="name"><strong>[OPTIONAL] setup_build</strong></p>
        <p>list, multi-line ok</p>
      </td>
      <td>
        <p>The shell commands to execute once at the beginning of each build on each machine executing this build.</p>
      </td>
    </tr>
    <tr class="setting">
      <td>
        <p class="name"><strong>[OPTIONAL] teardown_build</strong></p>
        <p>list, multi-line ok</p>
      </td>
      <td>
        <p>The shell commands to execute once at the end of each build on each machine executing this build.</p>
      </td>
    </tr>
    </tr>
    <tr class="setting">
      <td>
        <p class="name"><strong>[OPTIONAL] max_executors</strong></p>
        <p>int</p>
      </td>
      <td>
        <p>The max number of executors to allocate for this job. Once the number of executors running for this 
        build reaches max_executors, ClusterRunner will stop allocating executors. If this setting is not set, 
        ClusterRunner will continue allocating executors until all available executors are depleted or there 
        is no more work to do for the build.</p>
      </td>
    </tr>
  </tbody>
</table>
</div>

In order to help you effectively configure your job, ClusterRunner exports several environment variables into your
job script. All the following environment variables are available for use in the *commands* configuration section.

<div class="mobile-side-scroller">
<table>
  <thead>
    <tr>
      <th>Name</th>
      <th>Description</th>
    </tr>
  </thead>
  <tbody>
    <tr class="setting">
      <td>
        <p class="name"><strong>ARTIFACT_DIR</strong></p>
      </td>
      <td>
        <p>The directory to store build artifacts (if your job generates any). All files found in $ARTIFACT_DIR 
        will be returned to the user in a tarball.</p>
      </td>
    </tr>
    <tr class="setting">
      <td>
        <p class="name"><strong>PROJECT_DIR</strong></p>
      </td>
      <td>
        <p>The path to the root project directory. You should rarely need to specify any absolute paths in 
        clusterruner.yaml; they should all be relative to $PROJECT_DIR. (This is also available in the
        <em>setup_build</em> and <em>teardown_build</em> configuration sections.)</p>
      </td>
    </tr>
    <tr class="setting">
      <td>
        <p class="name"><strong>EXECUTOR_INDEX</strong></p>
      </td>
      <td>
        <p>The unique numeric ID of the current executor. If running multiple executors per slave, 
        $EXECUTOR_INDEX can come in handy when your testsuites have global state that needs to be partitioned 
        with a unique token.</p>
      </td>
    </tr>
  </tbody>
</table>
</div>