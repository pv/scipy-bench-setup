#!/bin/bash
set -e -u
cd "$(dirname "$0")"
exec ./run.sh run -k NEW > benchmark.log 2>&1
