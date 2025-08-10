cmake_minimum_required(VERSION 3.10)
project(AudioAnalyzerBridge)

# Set C++ standard (required for std::filesystem)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Define source files
set(SOURCES
    src/AudioAnalyzerBridge.cpp
    src/BPM_Detector.cpp
    src/FFT_Processor.cpp
    src/LoadAudioFunction.cpp
)

# Define header files
set(HEADERS
    include/AudioAnalyzerBridge.h
    include/BPM_Detector.h
    include/FFT_Processor.h
    include/LoadAudioFunction.h
)

# Create shared library (DLL)
add_library(AudioAnalyzerBridge SHARED
    src/AudioAnalyzerBridge.cpp
    src/BPM_Detector.cpp
    src/FFT_Processor.cpp
    src/LoadAudioFunction.cpp
)

# Set output name for different platforms
if(APPLE)
    set_target_properties(AudioAnalyzerBridge PROPERTIES
        OUTPUT_NAME "AudioAnalyzerBridge"
        SUFFIX ".dylib"
    )
elseif(UNIX)
    set_target_properties(AudioAnalyzerBridge PROPERTIES
        OUTPUT_NAME "AudioAnalyzerBridge"
        SUFFIX ".so"
    )
elseif(WIN32)
    set_target_properties(AudioAnalyzerBridge PROPERTIES
        OUTPUT_NAME "AudioAnalyzerBridge"
        SUFFIX ".dll"
    )
endif()

# Define AUDIO_ANALYZER_BRIDGE_EXPORTS for DLL exports
target_compile_definitions(AudioAnalyzerBridge PRIVATE AUDIO_ANALYZER_BRIDGE_EXPORTS)

# Set Windows-specific properties
if(WIN32)
    # Disable specific warnings
    target_compile_options(AudioAnalyzerBridge PRIVATE 
        /wd4244  # conversion from 'double' to 'float', possible loss of data
        /wd4267  # conversion from 'size_t' to 'int', possible loss of data
        /wd4996  # 'function': was declared deprecated
    )
    
    # Set output directory to be inside DjApp
    set_target_properties(AudioAnalyzerBridge PROPERTIES
        RUNTIME_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/../DjApp"
        RUNTIME_OUTPUT_DIRECTORY_RELEASE "${CMAKE_SOURCE_DIR}/../DjApp"
        RUNTIME_OUTPUT_DIRECTORY_DEBUG "${CMAKE_SOURCE_DIR}/../DjApp"
    )
    
    # Add Windows-specific libraries
    target_link_libraries(AudioAnalyzerBridge PRIVATE
        winmm  # Windows Multimedia Library
    )
elseif(UNIX AND NOT APPLE)
    # Linux-specific settings
    set_target_properties(AudioAnalyzerBridge PROPERTIES
        LIBRARY_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/../DjApp"
        LIBRARY_OUTPUT_DIRECTORY_RELEASE "${CMAKE_SOURCE_DIR}/../DjApp"
        LIBRARY_OUTPUT_DIRECTORY_DEBUG "${CMAKE_SOURCE_DIR}/../DjApp"
    )
    
    # Add Linux-specific libraries
    target_link_libraries(AudioAnalyzerBridge PRIVATE
        pthread    # POSIX threads
        m          # Math library
        stdc++fs   # Filesystem library (needed for older GCC versions)
    )
    
    # Set position independent code for shared library
    set_target_properties(AudioAnalyzerBridge PROPERTIES
        POSITION_INDEPENDENT_CODE ON
    )
    
    # Set the output library name to match what Python expects
    set_target_properties(AudioAnalyzerBridge PROPERTIES
        OUTPUT_NAME "AudioAnalyzerBridge"
        PREFIX "lib"
        SUFFIX ".so"
    )
    
    # Set GCC visibility flags for proper symbol export
    target_compile_options(AudioAnalyzerBridge PRIVATE
        -fvisibility=hidden
        -fvisibility-inlines-hidden
    )
elseif(APPLE)
    # macOS-specific settings
    set_target_properties(AudioAnalyzerBridge PROPERTIES
        LIBRARY_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/../DjApp"
        LIBRARY_OUTPUT_DIRECTORY_RELEASE "${CMAKE_SOURCE_DIR}/../DjApp"
        LIBRARY_OUTPUT_DIRECTORY_DEBUG "${CMAKE_SOURCE_DIR}/../DjApp"
    )
    
    # Add macOS-specific libraries
    target_link_libraries(AudioAnalyzerBridge PRIVATE
        m          # Math library
    )
    
    # Set position independent code for shared library
    set_target_properties(AudioAnalyzerBridge PROPERTIES
        POSITION_INDEPENDENT_CODE ON
    )
    
    # Set the output library name to match what Python expects
    set_target_properties(AudioAnalyzerBridge PROPERTIES
        OUTPUT_NAME "AudioAnalyzerBridge"
        PREFIX "lib"
        SUFFIX ".dylib"
    )
    
    # Set Clang visibility flags for proper symbol export
    target_compile_options(AudioAnalyzerBridge PRIVATE
        -fvisibility=hidden
        -fvisibility-inlines-hidden
    )
endif()

# Include directories
target_include_directories(AudioAnalyzerBridge PRIVATE
    ${CMAKE_SOURCE_DIR}/include
) 