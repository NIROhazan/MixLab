import time
import os
import traceback
import numpy as np
import sounddevice as sd
import soundfile as sf
from PyQt6.QtCore import QThread, pyqtSignal, QMutex

class RealTimeRecordingWorker(QThread):
    """Worker thread for recording real-time audio output using sounddevice.
    
    This class captures the actual audio output that you hear from the speakers,
    including all mixing effects from both decks.
    
    Signals:
        finished (str): Emitted when recording is complete with output file path
        error (str): Emitted when an error occurs during recording
        progress (int): Emitted to update recording progress in seconds
    """
    
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, output_file, channels=2, samplerate=44100):
        super().__init__()
        self.output_file = output_file
        self.channels = channels
        self.samplerate = samplerate
        self._is_running = True
        self._lock = QMutex()
        self.audio_data = []

    
    # Define callback for the stream     
    def audio_callback(self, indata, frames, time, status):
            """Sounddevice input stream callback.

            Appends captured chunks into an internal buffer while the worker
            is running. Any stream status is printed for diagnostic purposes.

            Args:
                indata (np.ndarray): Recorded audio chunk.
                frames (int): Number of frames in the chunk.
                time: Stream timing info (from sounddevice).
                status: Stream status flags.
            """
            if status:
                print(f'Status: {status}')
            if self._is_running:
                self.audio_data.append(indata.copy())
        
    def run(self):
        """Execute the recording loop until stop is requested.

        Selects a suitable loopback/virtual input device, records audio from
        the system output, periodically emits progress, and writes a WAV file
        when stopped or on completion.
        """
        try:
            print(f"RealTime Recording Worker: Starting - Output: {self.output_file}")
            
            # List all available devices
            print("\nAvailable audio devices:")
            devices = sd.query_devices()
            for i, dev in enumerate(devices):
                print(f"{i}: {dev['name']} (in={dev['max_input_channels']}, out={dev['max_output_channels']})")
            
            # Find VB-Audio Virtual Cable or Stereo Mix device
            recording_device = None
            for i, dev in enumerate(devices):
                # Look for common names of virtual audio devices
                if any(name.lower() in dev['name'].lower() for name in ['vb-audio', 'virtual cable', 'stereo mix', 'voicemeeter']):
                    if dev['max_input_channels'] > 0:  # Make sure it's an input device
                        recording_device = i
                        print(f"Found recording device: {dev['name']}")
                        break
            
            if recording_device is None:
                raise RuntimeError(
                    "No suitable recording device found. Please ensure VB-Audio Virtual Cable "
                    "or another virtual audio device is installed and enabled in your sound settings."
                )
            
            # Get device info
            device_info = devices[recording_device]
            print(f"Selected device info: {device_info}")
            
            # Use device's native sample rate if possible
            if 'default_samplerate' in device_info:
                self.samplerate = int(device_info['default_samplerate'])
                print(f"Using device's native sample rate: {self.samplerate}")
            
            # Configure stream settings
            stream_settings = {
                'device': recording_device,
                'channels': min(self.channels, device_info['max_input_channels']),
                'callback': self.audio_callback,
                'samplerate': self.samplerate,
                'latency': 'low'
            }
            
            print(f"Opening stream with settings: {stream_settings}")
            
            # Start recording stream
            with sd.InputStream(**stream_settings):
                start_time = time.time()
                last_progress_update = start_time
                
                # Keep recording until stopped
                while True:
                    self._lock.lock()
                    should_continue = self._is_running
                    self._lock.unlock()
                    
                    if not should_continue:
                        break
                        
                    # Update progress
                    current_time = time.time()
                    if current_time - last_progress_update >= 1.0:
                        seconds_recorded = int(current_time - start_time)
                        self.progress.emit(seconds_recorded)
                        last_progress_update = current_time
                        
                    time.sleep(0.1)  # Small sleep to prevent CPU overuse
                    
            # Combine all audio data
            if self.audio_data:
                combined_data = np.concatenate(self.audio_data)
                
                # Save to WAV file
                sf.write(self.output_file, combined_data, self.samplerate)
                print(f"RealTime Recording Worker: Finished successfully. Output: {self.output_file}")
                self.finished.emit(self.output_file)
            else:
                raise RuntimeError("No audio data was captured")
                
        except Exception as e:
            error_msg = f"Error in RealTimeRecordingWorker: {e}\n{traceback.format_exc()}"
            print(error_msg)
            # Attempt to remove partially created file
            if os.path.exists(self.output_file):
                try:
                    os.remove(self.output_file)
                except OSError:
                    pass
            self.error.emit(str(e))

    def stop_recording(self):
        """Signal the recording loop to stop gracefully."""
        self._lock.lock()
        print("RealTime Recording Worker: Setting stop flag.")
        self._is_running = False
        self._lock.unlock() 

            

        