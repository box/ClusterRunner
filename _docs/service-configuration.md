---
layout: docs
title: Service Configuration
prev_section: _auto_
next_section: _auto_
permalink: /docs/service-configuration/
---

The ClusterRunner service can be configured via the <code>~/.clusterrunner/clusterrunner.conf</code> file,
or by using options to override the default values via the following command:

{% highlight bash %}
~ $ clusterrunner deploy [options]
{% endhighlight %}

<div class="note info">
    <p>Deployment and configuration commands should be run from the ClusterMaster host</p>
</div>

#### Configuration Options

<div class="mobile-side-scroller">
<table>
  <thead>
    <tr>
      <th>Setting</th>
      <th>
        <span class="option">Options</span> and <span class="flag">Flags</span>
      </th>
    </tr>
  </thead>
  <tbody>
    <tr class="setting">
      <td>
        <p class="name"><strong>Slaves</strong></p>
        <p class="description">A list of <a>SSH-ready</a> hostnames the master will initialize as slaves</p>
        <p class="default">default: localhost</p>
      </td>
      <td class="align-center">
        <p><code class="option">[general]slaves: HOST1 [HOST2 ...]</code></p>
        <p><code class="flag">-s, --slaves HOST [HOST2 ...]</code></p>
      </td>
    </tr>
    <tr class="setting">
      <td>
        <p class="name"><strong>Executors per Slave</strong></p>
        <p class="description">The number of test processes allowed to execute concurrently per slave host</p>
        <p class="default">default: 1 (safest)</p>
      </td>
      <td class="align-center">
        <p><code class="option">[slave]num_executors: INT</code></p>
        <p><code class="flag">-n, --num-executors INT</code></p>
      </td>
    </tr>
    <tr class="setting">
      <td>
        <p class="name"><strong>Master Hostname</strong></p>
        <p class="description">The hostname of the master</p>
        <p class="default">default: localhost (recommended)</p>
      </td>
      <td class="align-center">
        <p><code class="option">[general]hostname: HOSTNAME</code></p>
        <p><code class="flag">-m, --master HOSTNAME</code></p>
      </td>
    </tr>
    <tr class="setting">
      <td>
        <p class="name"><strong>Master Port</strong></p>
        <p class="description">The port the master process will bind</p>
        <p class="default">default: 43000 (recommended)</p>
      </td>
      <td class="align-center">
        <p><code class="option">[master]port: INT</code></p>
        <p><code class="flag">--master-port INT</code></p>
      </td>
    </tr>
    <tr class="setting">
      <td>
        <p class="name"><strong>Slave Port</strong></p>
        <p class="description">The port the slave process will bind</p>
        <p class="default">default: 43001 (recommended)</p>
      </td>
      <td class="align-center">
        <p><code class="option">[slave]port: INT</code></p>
        <p><code class="flag">--slave-port INT</code></p>
      </td>
    </tr>
    <tr class="setting">
      <td>
        <p class="name"><strong>Log Level</strong></p>
        <p class="description">Log level for master and slave processes with options of DEBUG, INFO, NOTICE, 
        WARNING, ERROR, and CRITIAL</p>
        <p class="default">default: WARNING (recommended)</p>
      </td>
      <td class="align-center">
        <p><code class="option">[general]log_level: STRING</code></p>
      </td>
    </tr>
  </tbody>
</table>
</div>
