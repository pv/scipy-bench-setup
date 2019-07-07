#!/bin/bash
set -v -e -x
cd $(dirname "$0")
source $HOME/env/bin/activate
exec asv-bwrap --upload --lock=$HOME/lock config.toml run --cpu-affinity=3 --date-period=30d -e -k v0.17.0..origin/master
