---
layout: docs
title: Configuring Your Job
prev_section: _auto_
next_section: _auto_
permalink: /docs/configuring-your-project/
---

If you followed the [Quick Start](/docs/quickstart), you should have the ClusterRunnerDemo project checked 
out in your home directory. If you haven't, we suggest you go back and do that first. 

In this tutorial, we'll walk through configuring the 'Simple' job you ran in the ClusterRunnerDemo 
project. In order to keep the Simple job simple, we created an example that requires no additional packages to 
be installed on your machine. 

The Simple job will simulate running 10 tests concurrently, with each test taking 10 seconds to run and echoing 
all of the integers between 1 and 10.

### clusterrunner.yaml

Before you start configuring your jobs, you'll need to create a config file. ClusterRunner looks 
for a file named [clusterrunner.yaml](/docs/job-configuration) in your root project directory.

{% highlight bash %}
~ $ cd ~/ClusterRunnerDemo
~ $ vim clusterrunner.yaml
{% endhighlight %}

### Job Name

Next, give your job a name. Because this is a simple job created for demonstration, we have chosen 
the name 'Simple'. Creative, no?

{% highlight yaml %}
Simple:
{% endhighlight %}

This is a root-level yaml element. The next yaml sections we're going to add should be indented one level from here.

### setup_build:

What setup step do we need for our simple job? Nothing really, but for demonstrative purposes, let's output a
simple message.

{% highlight yaml %}
setup_build:
    - echo 'Performing setup'
{% endhighlight %}

Typically, this is where you would ensure that all necessary services are started, as well as run *make* 
if needed. 

### teardown_build:

Similarly, we don't have any necessary teardown steps to clean up after this build. But lets add one anyway.

{% highlight yaml %}
teardown_build:
    - echo 'Performing teardown'
{% endhighlight %}

In more complex jobs, you would undo any global state that was set on this machine during the build.

### atomizers:

Now we're getting to the good stuff! Here's where you tell ClusterRunner how to "atomize", or break apart, your tests
into individually runnable units. 

Your atomizer command should generate a list of parameter values that will then each be fed into the *commands* section.
For this example, we want to run ten "tests" where each test just echoes a number between 1 and 10. We do that by exporting
an environment variable, which we named `$TOKEN`, to contain each of the values 1 through 10. 

{% highlight yaml %}
atomizers:
    - TOKEN: seq 1 10
{% endhighlight %}

This means that the *commands* section will be executed ten times, with each execution having the `$TOKEN` environment
variable set to one of the values 1 through 10.

(In the command above, `seq` is [a Unix utility](http://en.wikipedia.org/wiki/Seq_(Unix)) for generating ranges.)

### commands:

This is the most signficant part of the configuration where you specify how to run your test. As stated 
earlier, the Simple job will simulate a 10 second test that echoes one of the numbers between 1 and 10 to the console. 

{% highlight yaml %}
commands:
    - cd $PROJECT_DIR
    - sleep 10
    - echo $TOKEN
{% endhighlight %}

Notice how we incorporated the environment variable, `$TOKEN`, from the *atomizers* section.
This is how the *atomizers* and the *commands* sections interact.

### max_executors:

You could set this to blank, but because we are demonstrating...
 
{% highlight yaml %}
max_executors: 10
{% endhighlight %}

Obviously, because we are only running 10 tests, there is never going to be a need to use more than 10
executors for this particular job. 

By default, if you don't specify *max_executors*, ClusterRunner will allocate every executor available 
on the slaves until the job runs out of atoms to work on. It may sound desirable to never specify 
*max_executors*, but if you are running jobs that have diminishing returns as you scale horizontally,
you may want to restrict the number of executors that a single build can hog so that other builds can utilize 
those executors instead.

## The finished product

Putting it all together, your clusterrunner.yaml file will look like this:

{% highlight yaml %}
Simple:
    max_executors: 10

    setup_build:
        - echo 'Performing setup'

    teardown_build:
        - echo 'Performing teardown'

    commands:
        - cd $PROJECT_DIR
        - sleep 10
        - echo $TOKEN

    atomizers:
        - TOKEN: seq 1 10
{% endhighlight %}

The order of the sections does not matter.

You should take some time to tweak the Simple job configuration and see how it affects the build artifact 
you get returned. Be adventurous!

Try:

 - writing some files to $ARTIFACT_DIR/ 
 - writing some invalid shell commands
 - performing a random 'exit 1'

and just run: 

{% highlight bash %}
~ $ clusterrunner build --job-name Simple
{% endhighlight %}

to check out the new results! The ./build_results/ directory should be updated every time you execute a build.
See the [Build Result Format](/docs/build-result-format) page for details.
 
## More practical examples

The Simple job just spins ClusterRunner's wheels. If you'd like to view a real test suite, inspect the 
'PHPUnit' and 'Nose' jobs in ClusterRunnerDemo's `clusterrunner.yaml`.

Make sure you have [phpunit](https://phpunit.de/manual/current/en/installation.html) and/or [nosetests](https://nose.readthedocs.org/en/latest/) installed, and try running the respective ClusterRunner jobs! 

{% highlight bash %}
~ $ clusterrunner build --job-name PHPUnit
~ $ clusterrunner build --job-name Nose
{% endhighlight %}
