#!/usr/bin/env bash
set -x # print all commands
set -e # exit when any command fails

rm -rf build/tribler
rm -rf dist/tribler
rm -rf build/debian/tribler/usr/share/tribler

# ----- Install dependencies before the build
python3 -m pip install --upgrade PyGObject==3.50.0
if [ "$TRIBLER_BUILD_MODE" = "standalone" ]; then
  python3 -m pip install PySide6 python-mpv qasync
  sed -i 's/Package: tribler/Package: tribler-standalone/g' ./build/debian/tribler/debian/control
  sed -i 's/Source: tribler/Source: tribler-standalone/g' ./build/debian/tribler/debian/control
  sed -i 's/tribler/tribler-standalone/g' ./build/debian/tribler/debian/changelog
fi

# ----- Update version
python3 ./build/debian/update_metainfo.py

# ----- Build binaries
python3 build/setup.py build

# ----- Build dpkg
cp -r ./dist/tribler ./build/debian/tribler/usr/share/tribler

# Compose the changelog
cd ./build/debian/tribler

export DEBEMAIL="info@tribler.org"
export DEBFULLNAME="Tribler"

PACKAGE_NAME="tribler"
if [ "$TRIBLER_BUILD_MODE" = "standalone" ]; then
  PACKAGE_NAME="tribler-standalone"
fi
dch --package "$PACKAGE_NAME" -v $GITHUB_TAG "New release"
dch -r "" --force-distribution -D stable "See https://github.com/Tribler/tribler/releases/tag/v$GITHUB_TAG for more info"

dpkg-buildpackage -b -rfakeroot -us -uc
