#!/bin/bash

# MixLab DJ - Linux Build Script for AudioAnalyzerBridge
# This script builds the AudioAnalyzerBridge shared library for Linux

set -e  # Exit on any error

echo "=== MixLab DJ - Linux Build Script ==="
echo

# Check if we're in the right directory
if [ ! -f "AudioAnalyzerBridge/CMakeLists.txt" ]; then
    echo "Error: This script should be run from the MixLab root directory"
    echo "Expected to find: AudioAnalyzerBridge/CMakeLists.txt"
    echo ""
    echo "Please make sure the folder is named 'AudioAnalyzerBridge' not 'AudioAnalyzerBridgeDLL'"
    exit 1
fi

# Check for required tools
echo "Checking for required build tools..."

if ! command -v cmake &> /dev/null; then
    echo "Error: cmake is not installed"
    echo "Please install cmake: sudo apt-get install cmake"
    exit 1
fi

if ! command -v make &> /dev/null; then
    echo "Error: make is not installed"  
    echo "Please install build-essential: sudo apt-get install build-essential"
    exit 1
fi

if ! command -v g++ &> /dev/null; then
    echo "Error: g++ is not installed"
    echo "Please install build-essential: sudo apt-get install build-essential"
    exit 1
fi

echo "✓ All required tools found"
echo

# Create build directory
echo "Creating build directory..."
cd AudioAnalyzerBridge
mkdir -p build
cd build

# Configure with cmake
echo "Configuring build with CMake..."
cmake .. -DCMAKE_BUILD_TYPE=Release

# Build the library
echo "Building AudioAnalyzerBridge shared library..."
make -j$(nproc)

# Check if the library was built successfully
if [ -f "../../DjApp/libAudioAnalyzerBridge.so" ]; then
    echo
    echo "✓ Build successful!"
    echo "✓ Library created: DjApp/libAudioAnalyzerBridge.so"
    
    # Show library info
    echo
    echo "Library information:"
    file "../../DjApp/libAudioAnalyzerBridge.so"
    ls -la "../../DjApp/libAudioAnalyzerBridge.so"
    
    echo
    echo "=== Build Complete ==="
    echo "You can now run the DJ application with: cd DjApp && python3 djapp.py"
    
else
    echo
    echo "✗ Build failed - library not found"
    echo "Expected: DjApp/libAudioAnalyzerBridge.so"
    echo "Current directory: $(pwd)"
    echo "Checking path: ../../DjApp/libAudioAnalyzerBridge.so"
    exit 1
fi 

# Copy the built so to DjApp for easy access
cp libAudioAnalyzerBridge.so ../../DjApp/

cd ../../DjApp

# Install Python dependencies
if command -v python3 &>/dev/null; then
    python3 -m pip install --upgrade pip
    python3 -m pip install -r requirements.txt
else
    echo "python3 not found. Please install Python 3.8+ and run: pip install -r requirements.txt"
fi

echo "Build complete. libAudioAnalyzerBridge.so copied to DjApp/ and Python dependencies installed." 