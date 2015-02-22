#!/usr/bin/env python
"""
Run Airspeed Velocity benchmark or Sphinx document build inside a
virtual machine
"""
from __future__ import division, absolute_import, print_function
import os
import sys
import re
import shutil
import argparse
import json
import subprocess
import time
import lxml.etree
import uuid
from contextlib import contextmanager
try:  # py3
    from shlex import quote
except ImportError:  # py2
    from pipes import quote

IMG_BASEFN = "trusty-server-cloudimg-amd64-vagrant-disk1.box"
IMG_URL = "https://cloud-images.ubuntu.com/vagrant/trusty/current/"+IMG_BASEFN
BOX_NAME = 'scipy-bench-trusty64'
RESULTS_REPO_CLONEURL = 'https://github.com/pv/scipy-bench.git'
RESULTS_REPO_UPLOADURL = 'git@github.com:pv/scipy-bench.git'


def main():
    p = argparse.ArgumentParser(description=__doc__.strip())
    sp = p.add_subparsers(dest="command", help="command to run")
    p_run = sp.add_parser('run',
        description=("Run benchmarks via ASV. This clones the scipy-bench repository "
                     "under 'scipy-bench/' and commits the results obtained into it. "
                     "HTML output is also generated under 'html/'. If 'deploy-key' is "
                     "present, the results are also pushed via Git, to master and "
                     "gh-pages."),
        help="run benchmarks and upload results")
    p_run.add_argument('args', metavar="ARGS", nargs=argparse.REMAINDER,
        help="arguments to pass on to asv run")
    p_cron = sp.add_parser('cron',
        help="run cron job (benchmark new commits, output log file)",
        description="Do './run.py run -k NEW > benchmark.log 2>&1'"
        )
    p_populate = sp.add_parser('populate',
        help="run for several commits throughout the history",
        description="Run for several commits throughout Scipy history")
    p_init_box = sp.add_parser('init-box',
        help="initialize Vagrant box",
        description="Create and add Vagrant box 'scipy-bench-trusty64', "
        "which is a 5GB Virtualbox VM based on Ubuntu trusty64 Vagrant image.")
    p_doc = sp.add_parser('docs',
        help="build docs with sphinx",
        description="Build Scipy docs using Sphinx. Output goes to 'doc/'")
    p_doc.add_argument('tag', metavar='TAG', default='master', nargs='?',
        help="tag/commit at which to build the docs")
    args = p.parse_args()

    os.chdir(os.path.dirname(__file__))

    if args.command == 'init-box':
        do_init_box()
    elif args.command == 'cron':
        do_cron()
    elif args.command == 'populate':
        do_populate()
    elif args.command == 'run':
        if args.args and args.args[0] == '--':
            args.args = args.args[1:]
        run_vm_asv(['run'] + args.args)
    elif args.command == 'docs':
        do_docs(args.tag)
    else:
        # should never happen
        raise ValueError()


def do_cron():
    with open('benchmark.log', 'wb') as f:
        with redirect_stream(sys.stdout, f):
            with redirect_stream(sys.stderr, sys.stdout):
                run_vm_asv(['run', '-k', 'NEW'])


def do_populate():
    run_vm_asv(['run', '-k', '--steps', '11', 'v0.5.0^..master'])
    run_vm_asv(['run', '-k', '--steps', '11', 'v0.7.0^..master'])
    run_vm_asv(['run', '-k', '--steps', '21', 'v0.9.0^..master'])
    run_vm_asv(['run', '-k', '--steps', '51', 'v0.5.0^..master'])


def do_docs(commit):
    with main_lock():
        with _vagrant_up():
            cmd = ['sudo', '--', '/usr/local/bin/run-cmd', 'docs', commit]
            run(['vagrant', 'ssh', '-c', " ".join(quote(x) for x in cmd)])


def do_init_box(force=False):
    print("-- Initializing Vagrant box")

    out = run(['vagrant', 'box', 'list'], output=True)
    if BOX_NAME in out:
        if force:
            run(['vagrant', 'box', 'remove', BOX_NAME])
        else:
            print("Box already exists.")
            return

    if not os.path.isfile(IMG_BASEFN):
        run(['curl', '-o', IMG_BASEFN, IMG_URL])

    # Resize the ubuntu image --- it contains a 4G partition that is resized
    # automatically on the first boot to match the size of the VM disk
    # For us, the default 40GB disk is way too big, so reduce the size
    run("rm -rf boxmod; mkdir boxmod")
    run(['tar', 'xf', '../' + IMG_BASEFN], cwd='boxmod')
    run("""
    qemu-img convert -O raw box-disk1.vmdk tmp.raw
    qemu-img resize tmp.raw 5G
    rm -f box-disk1.vmdk
    qemu-img convert -O vdi tmp.raw tmp.vdi
    rm -f tmp.raw
    VBoxManage clonehd tmp.vdi box-disk1.vmdk --format VMDK --variant Stream
    rm -f tmp.vdi
    """, cwd='boxmod')

    # Get disk image info
    info = json.loads(run(['qemu-img', 'info', '--output=json', 'box-disk1.vmdk'], output=True, cwd='boxmod'))
    virtual_size = info['virtual-size']
    vboxinfo = run(['vboxmanage', 'showhdinfo', 'box-disk1.vmdk'], output=True, cwd='boxmod')
    for line in vboxinfo.splitlines():
        m = re.match(r'^UUID:\s+([a-z0-9-]+)\s*$', line)
        if m:
            disk_uuid = m.group(1)
            break
    else:
        raise ValueError("vboxmanag showhdinfo did not return UUID?")

    # Substitute variables to ovf
    namespaces = {
        'ovf': 'http://schemas.dmtf.org/ovf/envelope/1',
        'vbox': 'http://www.virtualbox.org/ovf/machine',
        'vssd': 'http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_VirtualSystemSettingData'
    }
    our_id = "ubuntu-cloudimg-trusty-vagrant-amd64-scipy-bench"
    our_uuid = uuid.uuid4()
    tree = lxml.etree.parse('boxmod/box.ovf')
    disk, = tree.xpath('//ovf:Disk', namespaces=namespaces)
    disk.attrib['{http://schemas.dmtf.org/ovf/envelope/1}capacity'] = str(virtual_size)
    disk.attrib['{http://www.virtualbox.org/ovf/machine}uuid'] = disk_uuid
    image, = tree.xpath('//ovf:Image', namespaces=namespaces)
    image.attrib['uuid'] = '{' + disk_uuid + '}'
    vsystem, = tree.xpath('//ovf:VirtualSystem', namespaces=namespaces)
    vsystem.attrib['{http://schemas.dmtf.org/ovf/envelope/1}id'] = our_id
    vsysid, = tree.xpath('//vssd:VirtualSystemIdentifier', namespaces=namespaces)
    vsysid.text = our_id
    machine, = tree.xpath('//vbox:Machine', namespaces=namespaces)
    machine.attrib['name'] = our_id
    machine.attrib['uuid'] = '{%s}' % (our_uuid,)
    tree.write('boxmod/box.ovf')

    # Generate output box
    run(['tar', 'cf', '../%s.box' % (BOX_NAME,), '.'], cwd="boxmod")
    shutil.rmtree('boxmod')

    # Add to vagrant
    run("vagrant box add scipy-bench-trusty64 scipy-bench-trusty64.box")
    os.remove("scipy-bench-trusty64.box")


def run_vm_asv(cmd, upload=True):
    with main_lock():
        _run_vm_asv(cmd, upload)


@contextmanager
def main_lock():
    lock = LockFile('lockfile')
    if not lock.acquire(block=False):
        print("ERROR: another process is currently running")
        print("Wait until it is done, or remove 'lockfile'")
        sys.exit(1)
    try:
        yield
    finally:
        lock.release()


@contextmanager
def _vagrant_up():
    do_init_box()

    if not os.path.isdir('scipy-bench'):
        run(['git', 'clone', RESULTS_REPO_CLONEURL, 'scipy-bench'])
        run(['git', 'remote', 'add', 'upload', RESULTS_REPO_UPLOADURL],
            cwd='scipy-bench')

    if os.path.exists('html'):
        shutil.rmtree('html')
    os.makedirs('html')
    if os.path.exists('doc'):
        shutil.rmtree('doc')
    os.makedirs('doc')

    if not os.path.isdir('results'):
        os.symlink('scipy-bench/results', 'results')

    run(['vagrant', 'up'])
    try:
        yield
    finally:
        run(['vagrant', 'suspend'])


def _run_vm_asv(cmd, upload=True):
    if not os.path.isfile('hostname'):
        print("ERROR: Create a file 'hostname' with the desired hostname")
        sys.exit(1)

    if not os.path.isfile('deploy-key'):
        print("WARNING: SSH deployment key for uploads is missing; run ssh-keygen -f deploy-key")
        print("Upload will not be perfomed on this run!")
        upload = False

    env = dict(os.environ)
    env.update({
        'WORKDIR': os.getcwd(),
        'GIT_SSH': os.getcwd() + '/git-ssh'
    })

    with _vagrant_up():
        print("-- Doing an ASV run")
        run(['git', '-C', 'scipy-bench', 'pull', 'origin', 'master'])
        cmd = ['sudo', '--', '/usr/local/bin/run-cmd', 'benchmarks'] + cmd
        run(['vagrant', 'ssh', '-c', " ".join(quote(x) for x in cmd)])

    print("-- Adding results")
    run("""
    git pull origin master
    git checkout master
    git add -u results
    git add results
    git commit -m "New results" -a || true
    """, cwd='scipy-bench')

    if upload:
        print("-- Uploading results")
        run("git push upload master", cwd='scipy-bench', env=env)
        run("""
        rm -rf scipy-bench-html
        git clone -b master scipy-bench scipy-bench-html
        """)
        run(['git', 'remote', 'rm', 'origin'], cwd='scipy-bench-html')
        run(['git', 'remote', 'add', 'origin', RESULTS_REPO_UPLOADURL], cwd='scipy-bench-html')
        run("""
        git branch -D gh-pages || true
        git checkout --orphan gh-pages
        rsync -a ../html/ ./
        git add -f .
        git commit -m "Generated from sources"
        git push -f origin gh-pages
        """, cwd='scipy-bench-html', env=env)
        run("rm -rf scipy-bench-html")


def run(cmd, output=False, **kw):
    if isinstance(cmd, str):
        if output:
            raise ValueError()
        for line in cmd.splitlines():
            line = line.strip()
            if line:
                run([line], shell=True, **kw)
        return

    if kw.get('shell'):
        cmd_msg = " ".join(cmd)
    else:
        cmd_msg = " ".join(quote(x) for x in cmd)

    if 'cwd' in kw:
        print(kw['cwd'], "$", cmd_msg)
    else:
        print("$", cmd_msg)

    if not output:
        subprocess.check_call(cmd, **kw)
        return None
    else:
        return subprocess.check_output(cmd, **kw)


@contextmanager
def redirect_stream(stream, to):
    # Disable buffering from stdout and stderr
    stream_unbuffer = None
    old_stream = stream
    if stream is sys.stdout:
        stream_unbuffer = 'stdout'
        sys.stdout = os.fdopen(stream.fileno(), 'w', 0)
    elif stream is sys.stderr:
        stream_unbuffer = 'stderr'
        sys.stderr = os.fdopen(stream.fileno(), 'w', 0)

    try:
        # Redirect stream fd
        stream_fd = stream.fileno()
        with os.fdopen(os.dup(stream_fd), 'wb', 0) as copied:
            stream.flush()
            os.dup2(to.fileno(), stream_fd)
            try:
                yield stream
            finally:
                stream.flush()
                os.dup2(copied.fileno(), stream_fd)
    finally:
        # Restore original buffered streams
        if stream_unbuffer == 'stdout':
            sys.stdout = old_stream
        elif stream_unbuffer == 'stderr':
            sys.stderr = old_stream


class LockFile(object):
    # XXX: posix-only

    def __init__(self, filename):
        self.filename = filename
        self.pid = os.getpid()
        self.count = 0

    def __enter__(self):
        self.acquire()

    def __exit__(self, exc_type, exc_value, traceback):
        self.release()

    def acquire(self, block=True):
        if self.count > 0:
            self.count += 1
            return True

        while True:
            try:
                lock_pid = os.readlink(self.filename)
                if not os.path.isdir('/proc/%s' % lock_pid):
                    # dead lock; delete under lock to avoid races
                    sublock = LockFile(self.filename + '.lock')
                    sublock.acquire()
                    try:
                        os.unlink(self.filename)
                    finally:
                        sublock.release()
            except OSError, exc:
                pass

            try:
                os.symlink(repr(self.pid), self.filename)
                break
            except OSError, exc:
                if exc.errno != 17: raise

            if not block:
                return False
            time.sleep(1)

        self.count += 1
        return True

    def release(self):
        if self.count == 1:
            if os.path.islink(self.filename):
                os.unlink(self.filename)
        elif self.count < 1:
            raise RuntimeError('Invalid lock nesting')
        self.count -= 1


if __name__ == "__main__":
    main()
