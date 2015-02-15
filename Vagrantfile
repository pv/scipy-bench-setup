# -*- mode: ruby -*-
# vi: set ft=ruby :

# Vagrantfile API/syntax version. Don't touch unless you know what you're doing!
VAGRANTFILE_API_VERSION = "2"

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  if !File.exists?('hostname')
    raise "Create a file 'hostname' that contains the host name desired"
  end
  f = File.open('hostname')
  hostname = f.read().strip()
  f.close()
  bootstrap = <<__EOF__
set -e
echo "#{hostname}" > /etc/hostname
hostname "#{hostname}"
apt-get install -y python2.7-dev python-numpy libatlas-base-dev gfortran git python-six python-pip ccache python-virtualenv
apt-get --purge remove -y nfs-common rpcbind
adduser --system --uid 510 --home /srv/benchmarks runner
sudo -H -u runner git clone --depth 2 https://github.com/spacetelescope/asv.git /srv/benchmarks/asv
sudo -H -u runner pip install --no-index --user /srv/benchmarks/asv
cat <<EOF > /usr/local/bin/run-benchmarks
#!/bin/bash
set -e
run() {
    pushd /srv/benchmarks
    if test ! -d /srv/benchmarks/scipy; then
        sudo -H -u runner git clone https://github.com/scipy/scipy.git scipy
        ln -s /srv/results scipy/benchmarks/results
    fi
    pushd scipy/benchmarks
    sudo -H -u runner git pull --ff-only
    while true; do echo; done | exec sudo -H -u runner PATH=\\$PATH:/srv/benchmarks/.local/bin python run.py --current-repo "\\$@"
}
run "\\$@"
EOF
chmod a+rx /usr/local/bin/run-benchmarks
__EOF__

  config.vm.box = "ubuntu/trusty64"
  config.vm.box_url = "https://cloud-images.ubuntu.com/vagrant/trusty/current/trusty-server-cloudimg-amd64-vagrant-disk1.box"
  config.vm.provision :shell, inline: bootstrap
  config.vm.synced_folder ".", "/vagrant", disabled: true
  config.vm.synced_folder "results", "/srv/results", owner: 510

  config.vm.provider "virtualbox" do |vb|
    vb.customize ["modifyvm", :id, "--memory", "2000"]
  end
end
