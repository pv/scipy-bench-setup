#!/bin/bash
set -e -x
cd $(dirname "$0")
source $HOME/env/bin/activate
asv-bwrap --lock=$HOME/lock config.toml xslow run --cpu-affinity=3 --date-period=20d --durations=all -e -k "--first-parent v1.10.0^..origin/master"
asv-bwrap --upload --lock=$HOME/lock config.toml run NEW --cpu-affinity=3 -k -e --steps=6 --durations
