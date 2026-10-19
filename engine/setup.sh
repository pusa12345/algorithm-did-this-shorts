#!/usr/bin/env bash
# One-time setup of the free video engine in a fresh workspace (~2-3 min).
set -e
cd "$(dirname "$0")"
python3 -c "import onnxruntime, numpy, scipy, PIL" 
if [ ! -x espeak/bin/espeak-ng ]; then
  rm -rf espeak-src && git clone -q --depth 1 https://github.com/espeak-ng/espeak-ng.git espeak-src
  cmake -S espeak-src -B espeak-src/build -DCMAKE_INSTALL_PREFIX="$PWD/espeak" -DUSE_ASYNC=OFF -DUSE_MBROLA=OFF \
    -DUSE_LIBSONIC=OFF -DUSE_LIBPCAUDIO=OFF -DUSE_KLATT=OFF -DUSE_SPEECHPLAYER=OFF >/dev/null
  cmake --build espeak-src/build -j8 >/dev/null && cmake --install espeak-src/build >/dev/null
fi
R=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
[ -s kokoro.onnx ] || curl -sSL -o kokoro.onnx $R/kokoro-v1.0.int8.onnx
[ -s voices.bin ] || curl -sSL -o voices.bin $R/voices-v1.0.bin
echo "engine ready"
