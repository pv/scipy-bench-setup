scipy-bench-setup
=================

Simple VM setup for running benchmarks. You need working installations of
``virtualbox`` and ``vagrant``. The script will download and use a 64-bit
Ubuntu VM image.

Benchmarks and output generation are run inside the VM, uploading results is
done outside the VM.

Setting up::

    echo MY-HOSTNAME > hostname
    ssh-keygen -f deploy-key   # don't set a passphrase

The ssh deployment key is needed to push changes to the results repository.
Github allows repository specific deployment keys, which are very suitable
here.  The key needs to be added to the list of allowed keys for the
``scipy-bench`` results repository.

Running benchmarks::

    ./run.py run -k master^!

Daily cron::

    su -s /bin/sh -c "/PATH/TO/HERE/run.py cron" - USER


Environment
===========

The scripts supports two approaches to the environment:

1. Vagrant-based virtual machine ``run.py -j vagrant ...``

2. No isolation ``run.py -j cmd ...``

The VM based one uses settings from ``Vagrantfile`` and
``bin/run-cmd-vagrant``.

The "no isolation" approach runs commands via
``bin/run-cmd-user``. You can however use an Apparmor profile (example
in ``run-cmd-user.apparmor``) to sandbox it.
