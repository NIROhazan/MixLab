#!/bin/bash
set -e

# Build directory
BUILD_DIR="AudioAnalyzerBridge/build_macos"

mkdir -p $BUILD_DIR
cd $BUILD_DIR

cmake ..
make -j$(sysctl -n hw.ncpu)

# Copy the built dylib to DjApp for easy access
cp libAudioAnalyzerBridge.dylib ../../DjApp/

cd ../../DjApp

# Install Python dependencies
if command -v python3 &>/dev/null; then
    python3 -m pip install --upgrade pip
    python3 -m pip install -r requirements.txt
else
    echo "python3 not found. Please install Python 3.8+ and run: pip install -r requirements.txt"
fi

echo "Build complete. libAudioAnalyzerBridge.dylib copied to DjApp/ and Python dependencies installed." 