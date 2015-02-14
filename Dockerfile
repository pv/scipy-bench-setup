FROM Fedora-Docker-Base-20141203-21.x86_64

RUN \
    yum update -y && \
    yum install -y numpy atlas-devel gcc-gfortran ccache python-pip gcc-c++ git python-virtualenv python-six && \
    yum clean all && \
    adduser --system --home-dir /srv/asv --create-home asv && \
    mkdir -p /srv/results && \
    chown asv /srv/results && \
    su -c 'git clone --depth 1 https://github.com/spacetelescope/asv.git /srv/asv/asv && pip install --user --upgrade setuptools && pip install --user --no-index /srv/asv/asv' - asv

ADD benchmark-run /usr/local/bin/benchmark-run

VOLUME ["/srv/results"]

ENV HOME /srv/asv

USER asv

WORKDIR /srv/asv

CMD ["/usr/local/bin/benchmark-run"]
