@echo off
setlocal enabledelayedexpansion

REM MixLab DJ - Windows Build Script for AudioAnalyzerBridge
REM This script builds the AudioAnalyzerBridge DLL for Windows

echo === MixLab DJ - Windows Build Script ===
echo.

REM Check if we're in the right directory
if not exist "AudioAnalyzerBridge\CMakeLists.txt" (
    echo Error: This script should be run from the MixLab root directory
    echo Expected to find: AudioAnalyzerBridge\CMakeLists.txt
    echo.
    echo Please make sure the folder is named "AudioAnalyzerBridge" not "AudioAnalyzerBridgeDLL"
    pause
    exit /b 1
)

REM Check for required tools
echo Checking for required build tools...

REM Check for CMake
cmake --version >nul 2>&1
if errorlevel 1 (
    echo Error: cmake is not installed or not in PATH
    echo Please install CMake from: https://cmake.org/download/
    echo Make sure to add CMake to your system PATH during installation
    pause
    exit /b 1
)

REM Check for Visual Studio Build Tools
echo Checking for Visual Studio Build Tools...
set "VS_FOUND=0"

REM Check for Visual Studio 2022
if exist "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC" (
    set "VS_FOUND=1"
    set "VS_VERSION=2022"
    set "VS_PATH=C:\Program Files\Microsoft Visual Studio\2022\Community"
)
if exist "C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Tools\MSVC" (
    set "VS_FOUND=1"
    set "VS_VERSION=2022"
    set "VS_PATH=C:\Program Files\Microsoft Visual Studio\2022\Professional"
)
if exist "C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Tools\MSVC" (
    set "VS_FOUND=1"
    set "VS_VERSION=2022"
    set "VS_PATH=C:\Program Files\Microsoft Visual Studio\2022\Enterprise"
)

REM Check for Visual Studio 2019
if !VS_FOUND! == 0 (
    if exist "C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Tools\MSVC" (
        set "VS_FOUND=1"
        set "VS_VERSION=2019"
        set "VS_PATH=C:\Program Files (x86)\Microsoft Visual Studio\2019\Community"
    )
    if exist "C:\Program Files (x86)\Microsoft Visual Studio\2019\Professional\VC\Tools\MSVC" (
        set "VS_FOUND=1"
        set "VS_VERSION=2019"
        set "VS_PATH=C:\Program Files (x86)\Microsoft Visual Studio\2019\Professional"
    )
)

REM Check for Build Tools for Visual Studio
if !VS_FOUND! == 0 (
    if exist "C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\VC\Tools\MSVC" (
        set "VS_FOUND=1"
        set "VS_VERSION=2019 Build Tools"
        set "VS_PATH=C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools"
    )
)

if !VS_FOUND! == 0 (
    echo Error: Visual Studio or Build Tools not found
    echo Please install one of the following:
    echo - Visual Studio Community 2019 or later ^(free^)
    echo - Build Tools for Visual Studio ^(free^)
    echo Download from: https://visualstudio.microsoft.com/downloads/
    echo.
    echo Make sure to install the "C++ build tools" workload
    pause
    exit /b 1
)

echo ^+ CMake found
echo ^+ Visual Studio !VS_VERSION! found
echo.

REM Create build directory
echo Creating build directory...
cd AudioAnalyzerBridge
if exist build (
    echo Removing existing build directory...
    rmdir /s /q build
)
mkdir build
cd build

REM Configure with CMake
echo Configuring build with CMake...
if !VS_VERSION! == 2022 (
    cmake .. -G "Visual Studio 17 2022" -A x64 -DCMAKE_BUILD_TYPE=Release
) else (
    cmake .. -G "Visual Studio 16 2019" -A x64 -DCMAKE_BUILD_TYPE=Release
)

if errorlevel 1 (
    echo Error: CMake configuration failed
    pause
    exit /b 1
)

REM Build the DLL
echo Building AudioAnalyzerBridge DLL...
cmake --build . --config Release

if errorlevel 1 (
    echo Error: Build failed
    pause
    exit /b 1
)

REM Check if the DLL was built successfully
if exist "..\..\DjApp\AudioAnalyzerBridge.dll" (
    echo.
    echo ^+ Build successful!
    echo ^+ DLL created: DjApp\AudioAnalyzerBridge.dll
    
    REM Show DLL info
    echo.
    echo DLL information:
    dir "..\..\DjApp\AudioAnalyzerBridge.dll"
    
    echo.
    echo === Build Complete ===
    echo You can now run the DJ application with: cd DjApp ^&^& python djapp.py
    echo.
    
) else (
    echo.
    echo ^X Build failed - DLL not found
    echo Expected: DjApp\AudioAnalyzerBridge.dll
    echo Current directory: %CD%
    echo Checking path: ..\..\DjApp\AudioAnalyzerBridge.dll
    pause
    exit /b 1
)

REM Check for Python and dependencies
echo Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo Warning: Python is not installed or not in PATH
    echo Please install Python 3.8 or later from: https://python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation
) else (
    echo ^+ Python found
    
    REM Check if requirements.txt exists and suggest installing dependencies
    if exist "..\..\DjApp\requirements.txt" (
        echo.
        echo To install Python dependencies, run:
        echo cd DjApp
        echo pip install -r requirements.txt
    )
)

echo.
echo Build completed successfully!
pause 