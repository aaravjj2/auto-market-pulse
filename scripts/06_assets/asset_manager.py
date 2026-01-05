#!/usr/bin/env python3
"""Asset Manager: Selects background video files based on script topic keywords.

Maps keywords to background video filenames with fallback to default.
"""
import os
from pathlib import Path
from typing import List, Optional


class AssetManager:
    """Manages asset selection based on keyword matching."""
    
    def __init__(self, assets_base_dir: Optional[str] = None):
        """Initialize asset manager with keyword-to-file mapping.
        
        Args:
            assets_base_dir: Base directory for assets. If None, assumes 'assets' relative to script.
        """
        if assets_base_dir is None:
            # Default to assets directory relative to project root
            script_dir = Path(__file__).parent.parent.parent
            assets_base_dir = str(script_dir / "assets")
        
        self.assets_base_dir = Path(assets_base_dir)
        bg_dir = self.assets_base_dir / "bg"
        
        # Keyword mapping to background video files
        self.asset_map = {
            # Vintage/Housing themes
            "1970": "vintage_grain.mp4",
            "housing": "vintage_grain.mp4",
            "vintage": "vintage_grain.mp4",
            "home": "vintage_grain.mp4",
            "real estate": "vintage_grain.mp4",
            
            # Money/Fed themes
            "money": "printing_press.mp4",
            "printer": "printing_press.mp4",
            "fed": "printing_press.mp4",
            "federal reserve": "printing_press.mp4",
            "m2": "printing_press.mp4",
            "money supply": "printing_press.mp4",
            "quantitative easing": "printing_press.mp4",
        }
        
        # Default fallback background
        self.default_filename = "dark_grid_loop.mp4"
        self.default_path = bg_dir / self.default_filename
    
    def get_background(self, keywords: List[str]) -> str:
        """Select background video file based on keywords.
        
        Args:
            keywords: List of keyword strings to match against asset map.
            
        Returns:
            Absolute path to the selected background video file.
        """
        # Normalize keywords to lowercase for matching
        keywords_lower = [k.lower().strip() for k in keywords if k]
        
        # Search for first matching keyword
        for keyword in keywords_lower:
            if keyword in self.asset_map:
                filename = self.asset_map[keyword]
                bg_path = self.assets_base_dir / "bg" / filename
                
                # Check if file exists
                if bg_path.exists():
                    return str(bg_path.resolve())
                else:
                    print(f"Warning: Background file not found: {bg_path}")
                    break
        
        # Fallback to default
        if self.default_path.exists():
            return str(self.default_path.resolve())
        else:
            print(f"Warning: Default background file not found: {self.default_path}")
            # Return path anyway - caller can handle missing file
            return str(self.default_path.resolve())
    
    def get_background_from_text(self, text: str) -> str:
        """Extract keywords from text and return background file.
        
        Args:
            text: Text content to search for keywords (e.g., script content).
            
        Returns:
            Absolute path to the selected background video file.
        """
        # Simple keyword extraction - split text into words
        words = text.lower().split()
        # Also check for multi-word phrases
        keywords = words + [f"{words[i]} {words[i+1]}" for i in range(len(words)-1)]
        return self.get_background(keywords)


if __name__ == "__main__":
    # Test the asset manager
    manager = AssetManager()
    
    test_cases = [
        (["1970", "housing"], "Should match vintage_grain.mp4"),
        (["money", "economy"], "Should match printing_press.mp4"),
        (["random", "keywords"], "Should fallback to default"),
    ]
    
    for keywords, description in test_cases:
        result = manager.get_background(keywords)
        print(f"{description}: {result}")

