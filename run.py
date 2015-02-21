#!/usr/bin/env python
"""
run.py [command]

Run Airspeed Velocity benchmark inside a virtual machine

commands:

   init               initial run
   cron               run cron job (benchmark new commits)
   populate           run for several commits throughout the history
   <asv command>      any ASV command

"""
from __future__ import division, absolute_import, print_function
import os
import sys
import re
import shutil
import argparse
import json
import subprocess
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
RESULTS_REPO = 'git@github.com:pv/scipy-bench.git'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('command', nargs='+')
    args = p.parse_args()

    os.chdir(os.path.dirname(__file__))

    if args.command[0] == 'init':
        do_initial_run()
    elif args.command[0] == 'cron':
        do_cron()
    elif args.command[0] == 'populate':
        do_populate()
    else:
        run_vm_asv(args.command)


def do_initial_run():
    run_vm_asv(['run', '-k', 'master^!'])


def do_cron():
    print("-- Starting initial run")
    with open('benchmark.log', 'wb') as f:
        with redirect_stream(sys.stdout, f):
            with redirect_stream(sys.stderr, sys.stdout):
                run_vm_asv('run', '-k', 'NEW')


def do_populate():
    run_vm_asv(['run', '-k', '--steps', '11', 'v0.5.0^..master'])
    run_vm_asv(['run', '-k', '--steps', '11', 'v0.7.0^..master'])
    run_vm_asv(['run', '-k', '--steps', '21', 'v0.9.0^..master'])
    run_vm_asv(['run', '-k', '--steps', '51', 'v0.5.0^..master'])


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
    if not os.path.isfile('hostname'):
        print("ERROR: Create a file 'hostname' with the desired hostname")
        sys.exit(1)

    if not os.path.isfile('deploy-key'):
        print("WARNING: SSH deployment key for uploads is missing; run ssh-keygen -f deploy-key")
        print("Upload will not be perfomed on this run!")
        upload = False

    do_init_box()

    print("-- Doing an ASV run")

    env = {
        'WORKDIR': os.getcwd(),
        'GIT_SSH': os.getcwd() + '/git-ssh'
    }

    if not os.path.isdir('scipy-bench'):
        run(['git', 'clone', RESULTS_REPO, 'scipy-bench'])

    if os.path.exists('html'):
        shutil.rmtree('html')
    os.makedirs('html')

    if not os.path.isdir('results'):
        os.makedirs('results')

    run(['rsync', '-a', '--delete', 'scipy-bench/results/', 'results/'])

    cmd = ['sudo', '--', '/usr/local/bin/run-benchmarks'] + cmd

    run(['vagrant', 'up'])
    try:
        run(['vagrant', 'ssh', '-c', " ".join(quote(x) for x in cmd)])
    finally:
        run(['vagrant', 'suspend'])

    run(['git', '-C', 'scipy-bench', 'pull', '--ff-only', 'origin', 'master'])
    run(['rsync', '-a', '--delete', 'results/', 'scipy-bench/results/'])

    run("""
    git add -u results
    git add results
    git commit -m "New results" -a || true
    """, cwd='scipy-bench')

    if upload:
        run("git push origin master", cwd='scipy-bench')
        run("""
        rm -rf scipy-bench-html
        git clone -b master scipy-bench scipy-bench-html
        """)
        run("""
        git remote rm origin
        git remote add origin git@github.com:pv/scipy-bench.git
        git branch -D gh-pages || true
        git checkout --orphan gh-pages
        rsync -a ../html/ ./
        git add -f .
        git commit -m "Generated from sources"
        git push -f origin gh-pages
        """, cwd='scipy-bench-html')
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
    
    print("$", " ".join(cmd))
    if not output:
        subprocess.check_call(cmd, **kw)
        return None
    else:
        return subprocess.check_output(cmd, **kw)


@contextmanager
def redirect_stream(stream, to):
    stream_fd = stream.fileno
    with os.fdopen(os.dup(stream_fd), 'wb') as copied: 
        stream.flush()
        os.dup2(to.fileno, stream_fd)
        try:
            yield stream
        finally:
            stream.flush()
            os.dup2(copied.fileno(), stream_fd)


if __name__ == "__main__":
    main()
