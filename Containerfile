FROM debian:12-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        autoconf \
        automake \
        bison \
        ca-certificates \
        dh-python \
        flex \
        g++ \
        gcc \
        git \
        libpcap-dev \
        libpcre3-dev \
        libprotobuf-dev \
        libtool \
        libxml2-dev \
        make \
        pkg-config \
        protobuf-compiler \
        python3-protobuf \
        python3-setuptools \
        uuid-dev \
    && rm -rf /var/lib/apt/lists/*

FROM builder AS emane

ARG EMANE_VERSION=1.5.3
RUN git clone \
    -c advice.detachedHead=false \
    -b v${EMANE_VERSION} \
    --depth 1 \
    https://github.com/adjacentlink/emane.git \
    /usr/local/src/emane

RUN cd /usr/local/src/emane \
    && ./autogen.sh \
    && ./configure --disable-dependency-tracking --prefix=/usr/local \
    && make -j $(nproc) install

FROM builder AS olsrd

RUN git clone \
    -c advice.detachedHead=false \
    --depth 1 \
    https://github.com/OLSR/olsrd.git \
    /usr/local/src/olsrd

RUN cd /usr/local/src/olsrd \
    && make -j $(nproc) \
    && make -j $(nproc) install

FROM debian:12-slim

COPY --from=emane /usr/local/bin/ /usr/local/bin/
COPY --from=emane /usr/local/lib/ /usr/local/lib/
COPY --from=emane /usr/local/share/emane /usr/local/share/emane
COPY --from=olsrd /usr/local/sbin/olsrd /usr/local/sbin/olsrd

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        iproute2 \
        iputils-ping \
        libpcap0.8 \
        libpcre3 \
        libprotobuf32 \
        libxml2 \
        python3 \
        python3-lxml \
        python3-protobuf \
        python3-setuptools \
        python3-tabulate \
    && rm -rf /var/lib/apt/lists/*

COPY *.xml /data/
COPY --chmod=+x entrypoint.py /

STOPSIGNAL SIGINT

ENTRYPOINT [ "/entrypoint.py" ]
