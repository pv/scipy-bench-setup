#!/usr/bin/env python
import os
import re
import subprocess
import hashlib

DOWNLOAD_URL = "http://download.fedoraproject.org/pub/fedora/linux/releases/21/Docker/x86_64/Fedora-Docker-Base-20141203-21.x86_64.tar.gz"
CHECKSUM = """
-----BEGIN PGP SIGNED MESSAGE-----
Hash: SHA256

65b7de3d0f06f084099e415ad24e6331e5f366b1827bff7a0da89ac91f0f8471 *Fedora-Docker-Base-20141203-21.x86_64.tar.gz
-----BEGIN PGP SIGNATURE-----
Version: GnuPG v1.4.11 (GNU/Linux)

iQIcBAEBCAAGBQJUgifeAAoJEImtToeVpD9UXPwQAJPWHYQr8GuX6fBxRW0Nrqa9
839WuVUiGrCrpV8YBYburWaCdaSRsSZs3q0do+NrBKe6g/9bSqB6nAtWU0l7fGRS
+00QiBb1GV27TaAHW974t6WhATesFFARiNu3M7BS0CqzvB8JyqrDX66lcdwF3IC7
RS+Cihvo7tDqVJ6L5dG0mHzd5DytvqyWoGRictsEfbZtmm4jABx//puQdp2JzZm2
k6i7XqWvVx7MxYTl7/Wok9Oyyj/pjfCoa+L2YtYnk/DrXS2b4fdEWZyYlZChmd/l
85kjbFvpmcaVWShUaa82C2Kbx0cM+TWoIT/b9YXBdEPO7/fqnDukzBRcm9cfkmpt
zLJk9WAealXtxaXAUYHi281iWEfFxQ5zg0h0yTExaC4TkMDtbyPDZcl3IuxZr2P8
L5ltGuAAKrFrRXHLdbf+t10SilYbJI/ZP2j7Cu6Vr2kRO4AN14BQJnk/4hSrmgzV
butzS0BKuiMEhgjkmTnGfGtiD8p+dliy5ZGFaXIJEqDDZkJIBsQQpr/SXx9Z82bd
eFXBOI3v54T7f4t2vcBwvhkbTcUov/tVysRqStr/j50OIS7i4hnql37n5tFA0JCZ
nBDzBzYQ050HGyezHZvae+A8jpfZhoik2WHVWPolibOjp7T65xkM2fCV2+hZ66X7
oJLoRt8tPszm4kuGTkDL
=AmsE
-----END PGP SIGNATURE-----
"""


def download_image():
    filename = re.sub('.*/', '', DOWNLOAD_URL)
    if not os.path.isfile(filename):
        run(['curl', '-L', '-O', DOWNLOAD_URL])

    hasher = hashlib.sha256()
    with open(filename, 'rb') as fp:
        while True:
            block = fp.read(131072)
            if not block:
                break
            hasher.update(block)
    digest = hasher.hexdigest()

    p = subprocess.Popen(['gpg', '--verify'], stdin=subprocess.PIPE)
    p.communicate(CHECKSUM)
    if p.returncode != 0:
        raise RuntimeError("GPG signature check failed!")

    for line in CHECKSUM.splitlines():
        if line.strip() == "{0} *{1}".format(digest, filename):
            print("SHA256 checksum OK!")
            break
    else:
        raise RuntimeError("Invalid checksum in archive!")

    return filename


def main():
    filename = download_image()
    run(['sudo', 'docker', 'load', '-i', filename])


def run(cmd, **kw):
    print("$ " + " ".join(cmd))
    return subprocess.check_call(cmd, **kw)


if __name__ == "__main__":
    main()
