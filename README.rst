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

    ./run.sh run -k master^!

Daily cron::

    su -s /bin/sh -c "/PATH/TO/HERE/cron.sh" - USER
