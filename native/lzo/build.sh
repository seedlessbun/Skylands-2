#!/bin/sh
# Builds the LZO helper for players (Windows x64 DLL) and for tests (Linux .so).
set -e
cd "$(dirname "$0")"
out=../../setup/skylands_setup/bin
mkdir -p "$out"
x86_64-w64-mingw32-g++ -O2 -std=c++14 -shared -static -static-libgcc -static-libstdc++ \
  -o "$out/skylands_lzo.dll" skylands_lzo.cpp lzokay.cpp
g++ -O2 -std=c++14 -shared -fPIC -o "$out/skylands_lzo.so" skylands_lzo.cpp lzokay.cpp
