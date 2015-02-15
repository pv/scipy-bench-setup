#!/bin/bash
set -e -u
pushd "$(dirname "$0")"
exec ./run.sh run -k
