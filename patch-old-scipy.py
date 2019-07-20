#!/usr/bin/python3
import os
import tempfile
import subprocess

with tempfile.NamedTemporaryFile(suffix=".sh") as f:
    f.write(b"""
set -e -x

if test -f scipy/spatial/qhull.pyx; then
    # Patch old Scipy sources for Cython >=0.28 compatibility
    sed -i -E -e '/^(Delaunay|Voronoi|ConvexHull)\.add_points\.__func__\.__doc__/d;' scipy/spatial/qhull.pyx
fi

if test -f scipy/io/matlab/streams.pxd; then
    sed -i -e 's/cpdef long int tell(self):/cpdef long int tell(self) except -1:/' scipy/io/matlab/streams.pyx
fi

if test -f scipy/io/matlab/streams.pyx; then
    sed -i -e 's/cpdef long int tell(self):/cpdef long int tell(self) except -1:/' scipy/io/matlab/streams.pxd
fi
""")
    f.flush()

    subprocess.check_call(['bash', os.path.abspath(f.name)])
