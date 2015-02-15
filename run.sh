#!/bin/bash
set -e -u

pushd "$(dirname "$0")"

if test ! -f 'hostname'; then
    echo "Create a file 'hostname' with the desired hostname"
    exit 1
fi

if test ! -f 'deploy-key'; then
    echo "Create SSH deployment key for uploads, running ssh-keygen -f deploy-key"
    exit 1
fi

export WORKDIR="$PWD"
export GIT_SSH="$PWD/git-ssh"

if test ! -d scipy-bench; then
    git clone git@github.com:pv/scipy-bench.git scipy-bench
fi

rm -rf html
mkdir -p results html
rsync -a --delete scipy-bench/results/ results/

vagrant up
vagrant ssh -c "sudo -- /usr/local/bin/run-benchmarks $*"
vagrant suspend

git -C scipy-bench pull --ff-only origin master

rsync -a --delete results/ scipy-bench/results/ 

pushd scipy-bench
git add -u results
git add results
git commit -m "New results" -a || true
git push origin master
popd

if test -f html/index.json; then
    rm -rf scipy-bench-html
    git clone -b master scipy-bench scipy-bench-html
    pushd scipy-bench-html
    git remote rm origin
    git remote add origin git@github.com:pv/scipy-bench.git
    git branch -D gh-pages || true
    git checkout --orphan gh-pages
    rsync -a ../html/ ./
    git add -f .
    git commit -m "Generated from sources"
    git push -f origin gh-pages
    popd
    rm -rf scipy-bench-html
fi
