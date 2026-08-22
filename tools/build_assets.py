#!/usr/bin/env python3
"""
Asset Fingerprinting Build Script

This script:
1. Minifies CSS and JS files
2. Adds content-based hash fingerprints to filenames
3. Generates a manifest.json for template lookup
4. Enables long-term caching with cache-busting on changes

Usage:
    python build_assets.py
    python build_assets.py --watch  # Watch mode for development
"""
import os
import sys
import json
import hashlib
import shutil
import re
from pathlib import Path
from datetime import datetime

# Configuration
STATIC_DIR = Path(__file__).parent / "static"
BUILD_DIR = Path(__file__).parent / "static" / "dist"
MANIFEST_FILE = BUILD_DIR / "manifest.json"

# File types to process
CSS_EXTENSIONS = ['.css']
JS_EXTENSIONS = ['.js']
SKIP_DIRS = ['dist', 'vendor', 'node_modules']
SKIP_FILES = ['manifest.json']


def get_file_hash(filepath: Path, length: int = 8) -> str:
    """Generate content-based hash for a file."""
    with open(filepath, 'rb') as f:
        content = f.read()
    return hashlib.md5(content).hexdigest()[:length]


def minify_css(content: str) -> str:
    """Simple CSS minification."""
    # Remove comments
    content = re.sub(r'/\*[\s\S]*?\*/', '', content)
    # Remove extra whitespace
    content = re.sub(r'\s+', ' ', content)
    # Remove whitespace around special chars
    content = re.sub(r'\s*([{};:,>+~])\s*', r'\1', content)
    # Remove trailing semicolons before closing braces
    content = re.sub(r';}', '}', content)
    return content.strip()


def minify_js(content: str) -> str:
    """Simple JS minification (basic - for production use terser/esbuild)."""
    # Remove single-line comments (but preserve URLs)
    lines = content.split('\n')
    result = []
    for line in lines:
        # Skip lines that are only comments
        stripped = line.strip()
        if stripped.startswith('//') and 'http' not in stripped:
            continue
        # Remove inline comments (naive approach)
        if '//' in line and 'http' not in line:
            line = re.sub(r'\s*//[^"\']*$', '', line)
        result.append(line)
    content = '\n'.join(result)
    
    # Remove multi-line comments
    content = re.sub(r'/\*[\s\S]*?\*/', '', content)
    # Reduce multiple whitespace
    content = re.sub(r'\n\s*\n', '\n', content)
    content = re.sub(r'  +', ' ', content)
    return content.strip()


def process_file(src_path: Path, dest_dir: Path) -> dict:
    """Process a single file: minify and fingerprint."""
    relative_path = src_path.relative_to(STATIC_DIR)
    
    # Read content
    with open(src_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Minify based on type
    suffix = src_path.suffix.lower()
    if suffix in CSS_EXTENSIONS:
        minified = minify_css(content)
    elif suffix in JS_EXTENSIONS:
        minified = minify_js(content)
    else:
        minified = content
    
    # Generate hash
    file_hash = hashlib.md5(minified.encode()).hexdigest()[:8]
    
    # Create fingerprinted filename
    stem = src_path.stem
    new_filename = f"{stem}.{file_hash}{suffix}"
    
    # Create destination path maintaining directory structure
    dest_subdir = dest_dir / relative_path.parent
    dest_subdir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_subdir / new_filename
    
    # Write minified content
    with open(dest_path, 'w', encoding='utf-8') as f:
        f.write(minified)
    
    # Return mapping for manifest
    original_url = f"/static/{relative_path.as_posix()}"
    fingerprinted_url = f"/static/dist/{relative_path.parent.as_posix()}/{new_filename}"
    
    # Calculate size reduction
    original_size = len(content.encode('utf-8'))
    minified_size = len(minified.encode('utf-8'))
    reduction = ((original_size - minified_size) / original_size * 100) if original_size > 0 else 0
    
    return {
        'original': original_url,
        'fingerprinted': fingerprinted_url,
        'hash': file_hash,
        'original_size': original_size,
        'minified_size': minified_size,
        'reduction_percent': round(reduction, 1)
    }


def build_assets():
    """Main build function."""
    print(f"\n{'='*60}")
    print(f"  Asset Fingerprinting Build")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    # Clean build directory
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True)
    
    manifest = {
        'version': datetime.now().isoformat(),
        'files': {}
    }
    
    total_original = 0
    total_minified = 0
    processed_count = 0
    
    # Find all CSS and JS files
    for ext_list in [CSS_EXTENSIONS, JS_EXTENSIONS]:
        for ext in ext_list:
            for filepath in STATIC_DIR.rglob(f"*{ext}"):
                # Skip files in excluded directories
                if any(skip in filepath.parts for skip in SKIP_DIRS):
                    continue
                if filepath.name in SKIP_FILES:
                    continue
                
                try:
                    result = process_file(filepath, BUILD_DIR)
                    manifest['files'][result['original']] = result['fingerprinted']
                    
                    total_original += result['original_size']
                    total_minified += result['minified_size']
                    processed_count += 1
                    
                    print(f"✓ {result['original']}")
                    print(f"  → {result['fingerprinted']}")
                    print(f"  Size: {result['original_size']:,}B → {result['minified_size']:,}B ({result['reduction_percent']}% reduction)\n")
                    
                except Exception as e:
                    print(f"✗ Error processing {filepath}: {e}")
    
    # Write manifest
    with open(MANIFEST_FILE, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    # Summary
    total_reduction = ((total_original - total_minified) / total_original * 100) if total_original > 0 else 0
    
    print(f"\n{'='*60}")
    print(f"  Build Complete!")
    print(f"{'='*60}")
    print(f"  Files processed: {processed_count}")
    print(f"  Original size:   {total_original:,} bytes")
    print(f"  Minified size:   {total_minified:,} bytes")
    print(f"  Total reduction: {total_reduction:.1f}%")
    print(f"  Manifest:        {MANIFEST_FILE}")
    print(f"{'='*60}\n")
    
    return manifest


def get_asset_url(original_url: str) -> str:
    """
    Helper function to get fingerprinted URL from original.
    Use this in templates or API responses.
    """
    try:
        if MANIFEST_FILE.exists():
            with open(MANIFEST_FILE) as f:
                manifest = json.load(f)
            return manifest['files'].get(original_url, original_url)
    except:
        pass
    return original_url


if __name__ == '__main__':
    if '--watch' in sys.argv:
        print("Watch mode not implemented. Use a tool like watchdog.")
        print("For now, run this script manually after changes.")
    else:
        build_assets()
