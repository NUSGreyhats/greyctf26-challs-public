from ubuntu@sha256:6fee4abc5fe6a21f40022199b2d5063eb591743c80d3d2f5fadf620a98cbae0d as builder

run apt-get -y update && apt-get -y install git gcc make

workdir /build

# cpython
run git clone https://github.com/python/cpython --depth 1 --revision 0fb18b02c8ad56299d6a2910be0bab8ad601ef24 --no-tags

workdir /build/cpython
copy ./build/Setup.local ./Modules/
copy ./build/chall.patch ./
run git apply ./chall.patch && ./configure --disable-shared --without-static-libpython --disable-test-modules && make -j$(nproc)

workdir /build
copy ./build/run.c .
run gcc -o ./run ./run.c

# move necessary stuff to the /app directory and delete the build folder
workdir /app
run mv /build/cpython/python . \
  && mv /build/cpython/Lib /usr/local/lib/python3.12  \
  && mkdir /usr/local/lib/python3.12/lib-dynload \
  && mv /build/cpython/Modules/*.so /usr/local/lib/python3.12/lib-dynload \
  && mv /build/run .           \
  && rm -rf /build/

# setup the jail
from pwn.red/jail

env JAIL_TMP_SIZE 8M
env JAIL_TIME 600
env JAIL_PIDS 16
env JAIL_MEM 16M

copy --from=builder / /srv

workdir /srv/app

copy ./flag.txt ./flag.txt
run chmod 755 ./run    \
  && chmod 755 ./python \
  && chmod 444 ./flag.txt
