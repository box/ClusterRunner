---
layout: docs
title: API Docs
prev_section: _auto_
next_section: _auto_
permalink: /docs/api-docs/
---

ClusterRunner is built around a REST API. We use HMAC along with a configurable application
secret for securing communication between service components. JSON is returned in all responses,
and is used in POST requests.

Authentication
--------------

You authenticate a request by providing a header key-value pair for
ClusterRunner-Message-Authentication-Digest.  The value of the HMAC is generated using
the body of the request along with a secret is located in clusterrunner.conf.

Responses
---------

ClusterRunner uses HTTP response codes to indicate success or failure as well as a JSON body
for additional information.  The JSON response will include request specific information, along
with a STATUS field that will either be SUCCESS or FAILURE.

Versioning
----------

We version all of our APIs and make a major version bump whenever we make incompatible changes.
Currently we are on v1.


Builds
------

The build endpoint is located on the ClusterRunner master.

**List all builds**

Request

<code>GET /build</code>

Response

<pre>
{
  "builds": [
    {
      ...
    }
  ],
  "child_routes": {
    ...
  }
}
</pre>

**Get information about a single build**

Request

<code>GET /build/1/ </code>

Response

<pre>
"build": {
    "details": "534 of 637 subjobs are complete (83.8%).",
    "num_subjobs": 637,
    "failed_atoms": null,
    "artifacts": null,
    "status": "BUILDING",
    "result": null,
    "num_atoms": 2684,
    "id": 1,
    "error_message": null
}
</pre>

**Creating a new build**

To run a new build, you create a new build object.  The response will contain the
id of the new build object, which you can can later poll for the status of your
build.  A build can have a status of either BUILDING, SUCCESS, or FAILURE.
While a request is building, certain fields on the object may remain
null.  On completion, all the fields will contain their actual values.

Request

<code>POST /build</code>

Creating a new build object requires properly authenticating your request with the correct HMAC,
(see Authentication), and providing a JSON body that defines your build.  Here are the available
arguments for creating a build:


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
        <p class="name"><strong>type</strong></p>
      </td>
      <td>
        <p style="color:red">Required</p>
        <p>The project type of the new build. Should be set to "git".</p>
      </td>
    </tr>
    <tr class="setting">
      <td>
        <p class="name"><strong>job_name</strong></p>
      </td>
      <td>
        <p style="color:red">Required</p>
        <p>The name of the job to run on the new build.</p>
      </td>
    </tr>
    <tr class="setting">
      <td>
        <p class="name"><strong>url</strong></p>
      </td>
      <td>
        <p style="color:red">Required</p>
        <p>url to the git repo</p>
      </td>
    </tr>
    <tr class="setting">
      <td>
        <p class="name"><strong>remote</strong></p>
      </td>
      <td>
        <p>Optional</p>
        <p>The git remote name to fetch from</p>
      </td>
    </tr>
    <tr class="setting">
      <td>
        <p class="name"><strong>branch</strong></p>
      </td>
      <td>
        <p>Optional</p>
        <p>The git remote branch name to fetch from</p>
      </td>
    </tr>
    <tr class="setting">
      <td>
        <p class="name"><strong>hash</strong></p>
      </td>
      <td>
        <p>Optional</p>
        <p>The git hash on the remote to reset hard to</p>
      </td>
    </tr>
    <tr class="setting">
      <td>
        <p class="name"><strong>remote_files</strong></p>
      </td>
      <td>
        <p>Optional</p>
        <p>JSON dictionary that maps downloadable URI's to output file names.
            If present, each URI will be downloaded into the build workspace under the
            specified name.  </p>
      </td>
    </tr>
  </tbody>
</table>
</div>

Response

<code>202 ACCEPTED</code>

<pre>
{"build_id": 1, "STATUS": "SUCCESS"}
</pre>
