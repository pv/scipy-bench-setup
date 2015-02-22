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
mv run-cmd /usr/local/bin/run-cmd
chown root.root /usr/local/bin/run-cmd
chmod a+rx /usr/local/bin/run-cmd
apt-get install -y --no-install-recommends build-essential python2.7-dev python-numpy libopenblas-dev liblapack-dev gfortran git python-six python-pip ccache python-virtualenv rsync subversion python-sphinx texlive-latex-recommended libjs-mathjax texlive-fonts-recommended texlive-latex-extra cython
apt-get --purge remove -y nfs-common rpcbind mlocate apt-xapian-index aptitude unattended-upgrades
apt-get clean
echo 'APT::Periodic::Update-Package-Lists "0";' > /etc/apt/apt.conf.d/10periodic
adduser --system --uid 510 --home /srv/runner runner
sudo -H -u runner git clone --depth 2 https://github.com/spacetelescope/asv.git /srv/runner/asv
sudo -H -u runner pip install --no-index --user /srv/runner/asv
__EOF__

  config.vm.box = "scipy-bench-trusty64"
  config.vm.provision "file", source: "bin/run-cmd", destination: "run-cmd"
  config.vm.provision :shell, inline: bootstrap
  config.vm.synced_folder ".", "/vagrant", disabled: true
  config.vm.synced_folder "results", "/srv/results", owner: 510
  config.vm.synced_folder "html", "/srv/html", owner: 510
  config.vm.synced_folder "doc", "/srv/doc", owner: 510

  config.vm.provider "virtualbox" do |vb|
    vb.customize ["modifyvm", :id, "--memory", "2000"]
  end
end
