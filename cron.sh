#!/bin/bash
set -e -x
cd $(dirname "$0")
source $HOME/env/bin/activate
asv-bwrap --upload --lock=$HOME/lock config.toml run NEW --cpu-affinity=3 -k -e --steps=6 --durations
