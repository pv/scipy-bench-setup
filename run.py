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


BOX_NAME = 'numpy-bench-trusty'
RESULTS_REPO_CLONEURL = 'https://github.com/pv/numpy-bench.git'
RESULTS_REPO_UPLOADURL = 'git@github.com:pv/numpy-bench.git'


def main():
    p = argparse.ArgumentParser(description=__doc__.strip())
    p.add_argument('-j', '--jail', action="store", dest="jail", default='vagrant',
                   help="jail to use", choices=('vagrant', 'cmd'))
    p.add_argument('-l', '--lockfile', action="store", dest="lockfile", default='lockfile',
                   help="filename of the lock file to use")
    sp = p.add_subparsers(dest="command", help="command to run")
    p_run = sp.add_parser('run',
        description=("Run benchmarks via ASV. This clones the numpy-bench repository "
                     "under 'numpy-bench/' and commits the results obtained into it. "
                     "HTML output is also generated under 'html/'. If 'deploy-key' is "
                     "present, the results are also pushed via Git, to master and "
                     "gh-pages."),
        help="run benchmarks and upload results")
    p_run.add_argument('args', metavar="ARGS", nargs=argparse.REMAINDER,
        help="arguments to pass on to asv run")
    p_cron = sp.add_parser('cron',
        help="run cron job (benchmark new commits, output log file)",
        description="Do './run.py run -e -k NEW --steps 5 > benchmark.log 2>&1'"
        )
    p_populate = sp.add_parser('populate',
        help="run for several commits throughout the history",
        description="Run for several commits throughout numpy history")
    p_init_box = sp.add_parser('setup',
        help="initialize Vagrant box",
        description="Create and add Vagrant box '{}', "
        "which is a 5GB Virtualbox VM based on Ubuntu trusty Vagrant image.".format(BOX_NAME))
    p_doc = sp.add_parser('docs',
        help="build docs with sphinx",
        description="Build numpy docs using Sphinx. Output goes to 'doc/'")
    p_doc.add_argument('tag', metavar='TAG', default='master', nargs='?',
        help="tag/commit at which to build the docs")
    args = p.parse_args()

    os.chdir(os.path.dirname(__file__))

    jails = {
        'vargant': VagrantJail,
        'cmd': NoJail,
    }

    with main_lock(args.lockfile):
        jail = jails[args.jail]()

        if args.command == 'setup':
            jail.setup()
        elif args.command == 'cron':
            do_cron(jail)
        elif args.command == 'populate':
            do_populate(jail)
        elif args.command == 'run':
            if args.args and args.args[0] == '--':
                args.args = args.args[1:]
            run_vm_asv(jail, ['run'] + args.args)
        elif args.command == 'docs':
            do_docs(jail, args.tag)
        else:
            # should never happen
            raise ValueError()


def do_cron(jail):
    with open('benchmark.log', 'wb') as f:
        with redirect_stream(sys.stdout, f):
            with redirect_stream(sys.stderr, sys.stdout):
                run_vm_asv(jail, ['run', '-k', '-e', 'NEW', '--steps', '5'])


def do_populate(jail):
    run_vm_asv(jail, ['run', '-k', '--steps', '11', 'v0.5.0^..master'])
    run_vm_asv(jail, ['run', '-k', '--steps', '11', 'v0.7.0^..master'])
    run_vm_asv(jail, ['run', '-k', '--steps', '21', 'v0.9.0^..master'])
    run_vm_asv(jail, ['run', '-k', '--steps', '51', 'v0.5.0^..master'])


def do_docs(jail, commit):
    with with_jail_up(jail):
        jail.run(['docs', commit])


def is_vtx_available():
    with open('/proc/cpuinfo') as f:
        for line in f:
            if line.startswith('flags'):
                p = line.split()
                if 'vmx' in p or 'svm' in p:
                    return True
    return False


def run_vm_asv(jail, cmd, upload=True):
    _run_vm_asv(jail, cmd, upload)


@contextmanager
def main_lock(filename):
    lock = LockFile(filename)
    if not lock.acquire(block=False):
        print("ERROR: another process is currently running")
        print("Wait until it is done, or remove '{0}'".format(filename))
        sys.exit(1)
    try:
        yield
    finally:
        lock.release()


@contextmanager
def with_jail_up(jail):
    if not os.path.isdir('numpy-bench'):
        run(['git', 'clone', RESULTS_REPO_CLONEURL, 'numpy-bench'])
        run(['git', 'remote', 'add', 'upload', RESULTS_REPO_UPLOADURL],
            cwd='numpy-bench')

    if os.path.exists('html'):
        shutil.rmtree('html')
    os.makedirs('html')
    if os.path.exists('doc'):
        shutil.rmtree('doc')
    os.makedirs('doc')

    if not os.path.isdir('results'):
        os.symlink('numpy-bench/results', 'results')

    jail.setup()

    with jail.activate():
        yield


def _run_vm_asv(jail, cmd, upload=True):
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

    with with_jail_up(jail):
        print("-- Doing an ASV run")
        run(['git', '-C', 'numpy-bench', 'pull', 'origin', 'master'])
        jail.run(['benchmarks'] + cmd)

    print("-- Adding results")
    run("""
    git pull origin master
    git checkout master
    git add -u results
    git add results
    git commit -m "New results" -a || true
    """, cwd='numpy-bench')

    if upload:
        print("-- Uploading results")
        run("git push upload master", cwd='numpy-bench', env=env)
        run("""
        rm -rf numpy-bench-html
        git clone -b master numpy-bench numpy-bench-html
        """)
        run(['git', 'remote', 'rm', 'origin'], cwd='numpy-bench-html')
        run(['git', 'remote', 'add', 'origin', RESULTS_REPO_UPLOADURL], cwd='numpy-bench-html')
        run("""
        git branch -D gh-pages || true
        git checkout --orphan gh-pages
        rsync -a ../html/ ./
        git add -f .
        git commit -m "Generated from sources"
        git push -f origin gh-pages
        """, cwd='numpy-bench-html', env=env)
        run("rm -rf numpy-bench-html")


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


class VagrantJail(object):
    def setup(self, force=False):
        print("-- Initializing Vagrant box")

        out = run(['vagrant', 'box', 'list'], output=True)
        if BOX_NAME in out:
            if force:
                run(['vagrant', 'box', 'remove', BOX_NAME])
            else:
                print("Box already exists.")
                return

        box_fn = "{}.box".format(BOX_NAME)
        if os.path.exists(box_fn):
            print("Using a previously built box: {}".format(box_fn))
            run("vagrant box add {} {}.box".format(BOX_NAME, BOX_NAME))
            return

        img_url, img_basefn, is_64bit = self.get_vm_image()

        if not os.path.isfile(img_basefn):
            run(['curl', '-o', img_basefn, img_url])

        # Resize the ubuntu image --- it contains a 4G partition that is resized
        # automatically on the first boot to match the size of the VM disk
        # For us, the default 40GB disk is way too big, so reduce the size
        run("rm -rf boxmod; mkdir boxmod")
        run(['tar', 'xf', '../' + img_basefn], cwd='boxmod')
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
        our_id = "ubuntu-cloudimg-trusty-vagrant-numpy-bench"
        our_uuid = uuid.uuid4()
        tree = lxml.etree.parse('boxmod/box.ovf')
        if not is_64bit:
            # Ensure longmode is disabled
            cpu, = tree.xpath('//ovf:CPU', namespaces=namespaces)
            for el in list(cpu.xpath('ovf:LongMode', namespaces=namespaces)):
                cpu.remove(el)
            lxml.etree.SubElement(cpu, '{%s}LongMode' % namespaces['ovf'], attrib=dict(enabled="false"))
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
        run("vagrant box add {} {}.box".format(BOX_NAME, BOX_NAME))

    def get_vm_image(self):
        if is_vtx_available():
            # can use 64-bit image
            basefn = "trusty-server-cloudimg-amd64-vagrant-disk1.box"
            is_64bit = True
        else:
            # fall back to 32-bit
            basefn = "trusty-server-cloudimg-i386-vagrant-disk1.box"
            is_64bit = False
        url = "https://cloud-images.ubuntu.com/vagrant/trusty/current/" + basefn
        return url, basefn, is_64bit

    @contextmanager
    def activate(self):
        self.setup()
        run(['vagrant', 'up'])
        try:
            yield
        finally:
            run(['vagrant', 'suspend'])

    def run(self, cmd):
        cmd = ['sudo', '--', '/usr/local/bin/run-cmd'] + cmd
        run(['vagrant', 'ssh', '-c', " ".join(quote(x) for x in cmd)])


class NoJail(object):
    def setup(self, force=False):
        pass

    @contextmanager
    def activate(self):
        yield

    def run(self, cmd):
        cmd = [os.path.join(os.path.dirname(__file__), 'bin', 'run-cmd-user')] + cmd
        run(cmd)


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
