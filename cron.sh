#!/bin/bash
cd $(dirname "$0")
source $HOME/env/bin/activate
asv-bwrap --upload --lock=$HOME/lock config.toml run NEW --cpu-affinity=3 -k -e --steps=11 --durations
