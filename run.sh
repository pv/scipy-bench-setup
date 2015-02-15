#!/bin/bash
set -e -u

pushd "$(dirname "$0")"

if test ! -f 'hostname'; then
    echo "Create a file 'hostname' with the desired hostname"
    exit 1
fi

if test ! -f 'deploy-key'; then
    echo "Create a file 'deploy-key' containing the SSH deployment key for uploads"
    exit 1
fi

export WORKDIR="$PWD"
export GIT_SSH="$PWD/git-ssh"

if test ! -d scipy-bench; then
    git clone git@github.com:pv/scipy-bench.git scipy-bench
fi

mkdir -p results
rsync -a --delete scipy-bench/results/ results/

vagrant up
vagrant ssh -c "sudo -- /usr/local/bin/run-benchmarks $*"
vagrant suspend

rsync -a --delete results/ scipy-bench/results/ 

pushd scipy-bench
git add -u results
git commit -m "New results" -a
git push
