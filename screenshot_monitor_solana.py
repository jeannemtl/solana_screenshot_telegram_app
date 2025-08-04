#!/usr/bin/env python3

import os
import time
import unicodedata
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from src.simple_solana_client import SimpleScreenshotProcessor
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SolanaScreenshotHandler(FileSystemEventHandler):
    def __init__(self):
        self.processor = SimpleScreenshotProcessor()
        self.processed_files = set()
    
    def normalize_path(self, filepath):
        """Normalize unicode characters in file path"""
        try:
            # Normalize unicode characters
            normalized = unicodedata.normalize('NFC', filepath)
            return normalized
        except:
            return filepath
    
    def find_actual_file(self, reported_path):
        """Find the actual file when the reported path has unicode issues"""
        directory = os.path.dirname(reported_path)
        reported_filename = os.path.basename(reported_path)
        
        try:
            # List all files in the directory
            actual_files = os.listdir(directory)
            
            # Look for screenshot files created in the last 10 seconds
            recent_screenshots = []
            current_time = time.time()
            
            for filename in actual_files:
                if self.is_screenshot_file(filename):
                    full_path = os.path.join(directory, filename)
                    try:
                        file_time = os.path.getmtime(full_path)
                        if current_time - file_time < 10:  # Created in last 10 seconds
                            recent_screenshots.append((full_path, file_time))
                    except:
                        continue
            
            if recent_screenshots:
                # Return the most recent screenshot
                recent_screenshots.sort(key=lambda x: x[1], reverse=True)
                return recent_screenshots[0][0]
            
        except Exception as e:
            logger.error(f"Error finding actual file: {e}")
        
        return reported_path
    
    def is_screenshot_file(self, filename):
        """Check if filename is a screenshot"""
        filename_lower = filename.lower()
        return (
            filename_lower.endswith(('.png', '.jpg', '.jpeg')) and 
            (
                'screenshot' in filename_lower or 
                'screen shot' in filename_lower or
                filename.startswith('Screenshot') or 
                filename.startswith('.Screenshot') or  # Hidden screenshots
                'cleanshot' in filename_lower
            )
        )
    
    def on_created(self, event):
        if event.is_directory:
            return
        
        filepath = event.src_path
        filename = os.path.basename(filepath)
        
        # Check if it's a screenshot
        if self.is_screenshot_file(filename) and filepath not in self.processed_files:
            self.processed_files.add(filepath)
            logger.info(f"📸 New screenshot detected: {filename}")
            time.sleep(3)  # Wait a bit longer for file to be written
            self.process_screenshot(filepath)
    
    def process_screenshot(self, filepath):
        try:
            # Try to find the actual file path
            actual_filepath = self.find_actual_file(filepath)
            
            # Verify the file exists
            if not os.path.exists(actual_filepath):
                logger.warning(f"File not found at {actual_filepath}, trying alternatives...")
                
                # Try different normalizations
                normalized_path = self.normalize_path(filepath)
                if os.path.exists(normalized_path):
                    actual_filepath = normalized_path
                else:
                    logger.error(f"Could not find screenshot file: {filepath}")
                    return False
            
            logger.info(f"Processing file: {os.path.basename(actual_filepath)}")
            
            success = self.processor.process_screenshot(actual_filepath)
            if success:
                logger.info("✅ Screenshot added to daily Solana NFT!")
            else:
                logger.error("❌ Failed to process screenshot")
                
        except Exception as e:
            logger.error(f"Error processing screenshot: {e}")

def main():
    screenshots_dir = os.path.expanduser('~/Desktop')
    observer = Observer()
    observer.schedule(SolanaScreenshotHandler(), screenshots_dir, recursive=False)
    
    print("🚀 Solana Screenshot NFT Monitor (Enhanced)")
    print("=" * 40)
    print(f"📁 Monitoring: {screenshots_dir}")
    print("📸 Take a screenshot to see it added to your daily NFT!")
    print("💰 Cost per screenshot: ~$0.0001")
    print("🔧 Enhanced Unicode and hidden file handling")
    print("Press Ctrl+C to stop.\n")
    
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n👋 Stopping monitor...")
    
    observer.join()

if __name__ == "__main__":
    main()
