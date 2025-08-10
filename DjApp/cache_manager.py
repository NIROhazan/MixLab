import os
import json
import hashlib
import pickle
import numpy as np
import time
import logging
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path


logger = logging.getLogger(__name__)

class AudioCacheManager:
    """
    Comprehensive cache manager for audio analysis data.
    
    Handles persistent storage and retrieval of:
    - BPM data
    - Waveform data
    - Beat positions
    - FFT data
    - File metadata and integrity checking
    """
    
    def __init__(self, cache_directory: str = None):
        """
        Initialize the cache manager.
        
        Args:
            cache_directory (str, optional): Directory to store cache files. 
                                           Defaults to 'cache' in the script directory.
        """
        if cache_directory is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            cache_directory = os.path.join(script_dir, "cache")
        
        self.cache_dir = Path(cache_directory)
        self.metadata_file = self.cache_dir / "cache_metadata.json"
        
        # Create cache directory structure
        self._setup_cache_directories()
        
        # Load existing metadata
        self.metadata = self._load_metadata()
        
        logger.info(f"Audio cache manager initialized: {self.cache_dir}")
    
    def _setup_cache_directories(self):
        """Create the cache directory structure."""
        try:
            # Main cache directory
            self.cache_dir.mkdir(exist_ok=True)
            
            # Subdirectories for different data types
            (self.cache_dir / "bpm").mkdir(exist_ok=True)
            (self.cache_dir / "waveforms").mkdir(exist_ok=True)
            (self.cache_dir / "fft").mkdir(exist_ok=True)
            
            logger.debug("Cache directories created successfully")
        except Exception as e:
            logger.error(f"Failed to create cache directories: {e}")
        
    
    def _load_metadata(self) -> Dict[str, Any]:
        """Load cache metadata from disk."""
        try:
            if self.metadata_file.exists():
                with open(self.metadata_file, 'r') as f:
                    metadata = json.load(f)
                logger.debug(f"Loaded cache metadata for {len(metadata)} files")
                return metadata
        except Exception as e:
            logger.warning(f"Failed to load cache metadata: {e}")
        
        return {}
    
    def _save_metadata(self):
        """Save cache metadata to disk."""
        try:
            with open(self.metadata_file, 'w') as f:
                json.dump(self.metadata, f, indent=2)
            logger.debug("Cache metadata saved successfully")
        except Exception as e:
            logger.error(f"Failed to save cache metadata: {e}")
    
    def _get_file_hash(self, file_path: str) -> str:
        """
        Calculate MD5 hash of a file for integrity checking.
        
        Args:
            file_path (str): Path to the file.
            
        Returns:
            str: MD5 hash of the file.
        """
        try:
            hasher = hashlib.md5()
            with open(file_path, 'rb') as f:
                # Read file in chunks to handle large files efficiently
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            logger.error(f"Failed to calculate hash for {file_path}: {e}")
            return ""
    
    def _get_file_info(self, file_path: str) -> Dict[str, Any]:
        """
        Get file information for cache validation.
        
        Args:
            file_path (str): Path to the file.
            
        Returns:
            dict: File information including size, modification time, and hash.
        """
        try:
            stat = os.stat(file_path)
            return {
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "hash": self._get_file_hash(file_path)
            }
        except Exception as e:
            logger.error(f"Failed to get file info for {file_path}: {e}")
            return {}
    
    def _is_cache_valid(self, file_path: str) -> bool:
        """
        Check if cached data is still valid for the given file.
        
        Args:
            file_path (str): Path to the audio file.
            
        Returns:
            bool: True if cache is valid, False otherwise.
        """
        if file_path not in self.metadata:
            return False
        
        try:
            # Get current file info
            current_info = self._get_file_info(file_path)
            cached_info = self.metadata[file_path].get("file_info", {})
            
            # Check if file has changed
            if (current_info.get("size") != cached_info.get("size") or 
                current_info.get("mtime") != cached_info.get("mtime") or
                current_info.get("hash") != cached_info.get("hash")):
                logger.debug(f"Cache invalid for {file_path}: file has changed")
                return False
            
            return True
        except Exception as e:
            logger.error(f"Error checking cache validity for {file_path}: {e}")
            return False
    
    def _get_cache_key(self, file_path: str) -> str:
        """
        Generate a safe cache key from file path.
        
        Args:
            file_path (str): Path to the file.
            
        Returns:
            str: Safe cache key.
        """
        # Use MD5 hash of the full path to create a safe filename
        return hashlib.md5(file_path.encode('utf-8')).hexdigest()
    
    def cache_bpm_data(self, file_path: str, bpm: int, beat_positions: List[int], full_track: bool = False):
        """
        Cache BPM and beat position data for a file.
        
        Args:
            file_path (str): Path to the audio file.
            bpm (int): BPM value.
            beat_positions (List[int]): List of beat positions in milliseconds.
        """
        try:
            cache_key = self._get_cache_key(file_path)
            bpm_file = self.cache_dir / "bpm" / f"{cache_key}.json"
            
            # Prepare data to cache
            bpm_data = {
                "bpm": bpm,
                "beat_positions": beat_positions,
                "cached_at": time.time(),
                "full_track": bool(full_track)
            }
            
            # Save BPM data
            with open(bpm_file, 'w') as f:
                json.dump(bpm_data, f)
            
            # Update metadata
            if file_path not in self.metadata:
                self.metadata[file_path] = {}
            
            self.metadata[file_path].update({
                "file_info": self._get_file_info(file_path),
                "bpm_cached": True,
                "bpm_file": str(bpm_file),
                "last_updated": time.time()
            })
            
            self._save_metadata()
            logger.debug(f"Cached BPM data for {file_path}: BPM={bpm}, Beats={len(beat_positions)}")
            
        except Exception as e:
            logger.error(f"Failed to cache BPM data for {file_path}: {e}")

    def get_bpm_cache_entry(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve raw BPM cache entry (including metadata fields like 'full_track').

        Args:
            file_path (str): Path to the audio file.

        Returns:
            Optional[Dict[str, Any]]: Parsed JSON cache entry or None.
        """
        if not self._is_cache_valid(file_path):
            return None

        try:
            cache_key = self._get_cache_key(file_path)
            bpm_file = self.cache_dir / "bpm" / f"{cache_key}.json"
            if not bpm_file.exists():
                return None
            with open(bpm_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to retrieve raw BPM cache entry for {file_path}: {e}")
            return None
    
    def get_bpm_data(self, file_path: str) -> Tuple[Optional[int], Optional[List[int]]]:
        """
        Retrieve cached BPM and beat position data.
        
        Args:
            file_path (str): Path to the audio file.
            
        Returns:
            Tuple[Optional[int], Optional[List[int]]]: (BPM, beat_positions) or (None, None) if not cached.
        """
        if not self._is_cache_valid(file_path):
            return None, None
        
        try:
            cache_key = self._get_cache_key(file_path)
            bpm_file = self.cache_dir / "bpm" / f"{cache_key}.json"
            
            if not bpm_file.exists():
                return None, None
            
            with open(bpm_file, 'r') as f:
                bpm_data = json.load(f)
            
            bpm = bpm_data.get("bpm")
            beat_positions = bpm_data.get("beat_positions", [])
            
            logger.debug(f"Retrieved cached BPM data for {file_path}: BPM={bpm}, Beats={len(beat_positions)}")
            return bpm, beat_positions
            
        except Exception as e:
            logger.error(f"Failed to retrieve BPM data for {file_path}: {e}")
            return None, None
    
    def cache_waveform_data(self, file_path: str, waveform_data: np.ndarray, sample_rate: int):
        """
        Cache waveform data for a file.
        
        Args:
            file_path (str): Path to the audio file.
            waveform_data (np.ndarray): Waveform data array.
            sample_rate (int): Sample rate.
        """
        try:
            cache_key = self._get_cache_key(file_path)
            waveform_file = self.cache_dir / "waveforms" / f"{cache_key}.npz"
            
            # Save waveform data using numpy's compressed format
            np.savez_compressed(
                waveform_file,
                waveform=waveform_data,
                sample_rate=sample_rate,
                cached_at=time.time()
            )
            
            # Update metadata
            if file_path not in self.metadata:
                self.metadata[file_path] = {}
            
            self.metadata[file_path].update({
                "file_info": self._get_file_info(file_path),
                "waveform_cached": True,
                "waveform_file": str(waveform_file),
                "last_updated": time.time()
            })
            
            self._save_metadata()
            logger.debug(f"Cached waveform data for {file_path}: {len(waveform_data)} samples at {sample_rate}Hz")
            
        except Exception as e:
            logger.error(f"Failed to cache waveform data for {file_path}: {e}")
    
    def get_waveform_data(self, file_path: str) -> Tuple[Optional[np.ndarray], Optional[int]]:
        """
        Retrieve cached waveform data.
        
        Args:
            file_path (str): Path to the audio file.
            
        Returns:
            Tuple[Optional[np.ndarray], Optional[int]]: (waveform_data, sample_rate) or (None, None) if not cached.
        """
        if not self._is_cache_valid(file_path):
            return None, None
        
        try:
            cache_key = self._get_cache_key(file_path)
            waveform_file = self.cache_dir / "waveforms" / f"{cache_key}.npz"
            
            if not waveform_file.exists():
                return None, None
            
            data = np.load(waveform_file)
            waveform = data['waveform']
            sample_rate = int(data['sample_rate'])
            
            logger.debug(f"Retrieved cached waveform data for {file_path}: {len(waveform)} samples at {sample_rate}Hz")
            return waveform, sample_rate
            
        except Exception as e:
            logger.error(f"Failed to retrieve waveform data for {file_path}: {e}")
            return None, None
    
    def cache_fft_data(self, file_path: str, fft_data: List[Dict[str, Any]]):
        """
        Cache FFT analysis data for a file.
        
        Args:
            file_path (str): Path to the audio file.
            fft_data (List[Dict]): List of FFT data entries with time_ms and magnitudes.
        """
        try:
            cache_key = self._get_cache_key(file_path)
            fft_file = self.cache_dir / "fft" / f"{cache_key}.pkl"
            
            # Prepare data with timestamp
            cache_data = {
                "fft_data": fft_data,
                "cached_at": time.time()
            }
            
            # Save using pickle for complex data structures
            with open(fft_file, 'wb') as f:
                pickle.dump(cache_data, f)
            
            # Update metadata
            if file_path not in self.metadata:
                self.metadata[file_path] = {}
            
            self.metadata[file_path].update({
                "file_info": self._get_file_info(file_path),
                "fft_cached": True,
                "fft_file": str(fft_file),
                "last_updated": time.time()
            })
            
            self._save_metadata()
            logger.debug(f"Cached FFT data for {file_path}: {len(fft_data)} entries")
            
        except Exception as e:
            logger.error(f"Failed to cache FFT data for {file_path}: {e}")
    
    def get_fft_data(self, file_path: str) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieve cached FFT data.
        
        Args:
            file_path (str): Path to the audio file.
            
        Returns:
            Optional[List[Dict]]: FFT data or None if not cached.
        """
        if not self._is_cache_valid(file_path):
            return None
        
        try:
            cache_key = self._get_cache_key(file_path)
            fft_file = self.cache_dir / "fft" / f"{cache_key}.pkl"
            
            if not fft_file.exists():
                return None
            
            with open(fft_file, 'rb') as f:
                cache_data = pickle.load(f)
            
            fft_data = cache_data.get("fft_data", [])
            logger.debug(f"Retrieved cached FFT data for {file_path}: {len(fft_data)} entries")
            return fft_data
            
        except Exception as e:
            logger.error(f"Failed to retrieve FFT data for {file_path}: {e}")
            return None
    
    def invalidate_cache(self, file_path: str):
        """
        Invalidate cached data for a specific file.When file is deleted/changed, this function is called to remove the cache.
        
        Args:
            file_path (str): Path to the audio file.
        """
        try:
            if file_path in self.metadata:
                cache_key = self._get_cache_key(file_path)
                
                # Remove cache files
                for data_type in ["bpm", "waveforms", "fft"]:
                    cache_files = list((self.cache_dir / data_type).glob(f"{cache_key}.*"))
                    for cache_file in cache_files:
                        try:
                            cache_file.unlink()
                            logger.debug(f"Removed cache file: {cache_file}")
                        except Exception as e:
                            logger.warning(f"Failed to remove cache file {cache_file}: {e}")
                
                # Remove from metadata
                del self.metadata[file_path]
                self._save_metadata()
                
                logger.info(f"Invalidated cache for {file_path}")
        
        except Exception as e:
            logger.error(f"Failed to invalidate cache for {file_path}: {e}")
    
    def cleanup_old_cache(self, max_age_days: int = 30):
        """
        Remove old cache entries that haven't been accessed recently.
        
        Args:
            max_age_days (int): Maximum age in days for cache entries.
        """
        try:
            current_time = time.time()
            max_age_seconds = max_age_days * 24 * 60 * 60
            
            files_to_remove = []
            
            for file_path, metadata in self.metadata.items():
                last_updated = metadata.get("last_updated", 0)
                if current_time - last_updated > max_age_seconds:
                    files_to_remove.append(file_path)
            
            for file_path in files_to_remove:
                self.invalidate_cache(file_path)
            
            logger.info(f"Cleaned up {len(files_to_remove)} old cache entries")
            
        except Exception as e:
            logger.error(f"Failed to cleanup old cache: {e}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the cache.
        
        Returns:
            Dict[str, Any]: Cache statistics.
        """
        try:
            total_files = len(self.metadata)
            bpm_cached = sum(1 for meta in self.metadata.values() if meta.get("bpm_cached", False))
            waveform_cached = sum(1 for meta in self.metadata.values() if meta.get("waveform_cached", False))
            fft_cached = sum(1 for meta in self.metadata.values() if meta.get("fft_cached", False))
            
            # Calculate cache size
            cache_size = 0
            for root, _, files in os.walk(self.cache_dir):
                for file in files:
                    try:
                        cache_size += os.path.getsize(os.path.join(root, file))
                    except:
                        pass
            
            cache_size_mb = cache_size / (1024 * 1024)
            
            return {
                "total_files": total_files,
                "bpm_cached": bpm_cached,
                "waveform_cached": waveform_cached,
                "fft_cached": fft_cached,
                "cache_size_mb": round(cache_size_mb, 2),
                "cache_directory": str(self.cache_dir)
            }
            
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {"error": str(e)}
    
    def clear_all_cache(self):
        """Clear all cached data."""
        try:
            # Remove all cache files
            for data_dir in ["bpm", "waveforms", "fft"]:
                cache_dir = self.cache_dir / data_dir
                if cache_dir.exists():
                    for cache_file in cache_dir.iterdir():
                        try:
                            cache_file.unlink()
                        except Exception as e:
                            logger.warning(f"Failed to remove {cache_file}: {e}")
            
            # Clear metadata
            self.metadata = {}
            self._save_metadata()
            
            logger.info("Cleared all cache data")
            
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}") 