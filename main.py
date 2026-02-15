import os
import sys
import argparse
import subprocess
import shutil
import time
from PIL import Image, UnidentifiedImageError
from datetime import datetime

# ---------------------------------------------------------------------
# SETUP & HELPERS
# ---------------------------------------------------------------------

def parse_arguments():
    parser = argparse.ArgumentParser(description="Convert Fujifilm W3 Photos (MPO) and Videos (AVI) to XREAL format (Recursive).")
    
    # Path Arguments
    parser.add_argument('-i', '--input', default='./input', help="Input folder containing files (searches recursively).")
    parser.add_argument('-o', '--output', default='./output', help="Base output folder.")
    parser.add_argument('--ffmpeg', default='ffmpeg', help="Path to ffmpeg executable.")
    
    # Filter Arguments
    parser.add_argument('--skip-photos', action='store_true', help="Do not process .MPO photos.")
    parser.add_argument('--skip-videos', action='store_true', help="Do not process .AVI videos.")
    
    return parser.parse_args()

def get_timestamp_from_file(filepath):
    try:
        mtime = os.path.getmtime(filepath)
        return datetime.fromtimestamp(mtime)
    except OSError:
        return datetime.now()

def get_unique_filename(folder, filename):
    base, ext = os.path.splitext(filename)
    counter = 1
    new_filename = filename
    while os.path.exists(os.path.join(folder, new_filename)):
        new_filename = f"{base}_{counter}{ext}"
        counter += 1
    return new_filename

def match_file_dates(source_path, target_path):
    try:
        mtime = os.path.getmtime(source_path)
        os.utime(target_path, (mtime, mtime))
    except Exception:
        pass

# ---------------------------------------------------------------------
# VIDEO PROCESSING (FFMPEG)
# ---------------------------------------------------------------------

def convert_video(file_path, output_folder, ffmpeg_cmd):
    filename = os.path.basename(file_path)
    
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    # Generate Filename
    date_obj = get_timestamp_from_file(file_path)
    timestamp_str = date_obj.strftime('%Y%m%d_%H%M%S')
    clean_name = f"SV_{timestamp_str}.mp4" 
    clean_name = get_unique_filename(output_folder, clean_name)
    output_path = os.path.join(output_folder, clean_name)
    
    # FFmpeg Command
    cmd = [
        ffmpeg_cmd, '-y', '-i', file_path,       
        '-filter_complex', '[0:v:0][0:v:1]hstack=inputs=2[v]', 
        '-map', '[v]', '-map', '0:a',         
        '-c:v', 'libx264', '-crf', '18', '-preset', 'fast',     
        '-c:a', 'aac', '-b:a', '192k',        
        output_path
    ]

    print(f"--> Video: {filename}")
    
    try:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            match_file_dates(file_path, output_path)
            print(f"    [OK] Saved as {clean_name}")
        else:
            print(f"    [ERR] FFmpeg failed: {result.stderr}")
    except FileNotFoundError:
        print("    [FATAL] FFmpeg not found!")
        sys.exit(1)

# ---------------------------------------------------------------------
# PHOTO PROCESSING (PILLOW)
# ---------------------------------------------------------------------

def convert_photo(file_path, output_folder):
    filename = os.path.basename(file_path)

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    try:
        with Image.open(file_path) as im:
            try:
                im.seek(0); left_img = im.copy()
                im.seek(1); right_img = im.copy()
            except EOFError:
                print(f"    [SKIP] {filename}: Not 3D.")
                return

            w, h = left_img.size
            sbs = Image.new('RGB', (w * 2, h))
            sbs.paste(left_img, (0, 0))
            sbs.paste(right_img, (w, 0))

            # Metadata & Naming
            exif = im._getexif()
            date_obj = None
            if exif and 36867 in exif:
                try:
                    date_obj = datetime.strptime(exif[36867], '%Y:%m:%d %H:%M:%S')
                except: pass
            
            if not date_obj:
                date_obj = get_timestamp_from_file(file_path)

            clean_name = f"SV_{date_obj.strftime('%Y%m%d_%H%M%S')}.jpg"
            clean_name = get_unique_filename(output_folder, clean_name)
            output_path = os.path.join(output_folder, clean_name)

            if im.info.get('exif'):
                sbs.save(output_path, "JPEG", quality=95, exif=im.info['exif'])
            else:
                sbs.save(output_path, "JPEG", quality=95)
            
            match_file_dates(file_path, output_path)
            print(f"    [OK] Photo: {filename} -> {clean_name}")

    except Exception as e:
        print(f"    [ERR] {filename}: {e}")

# ---------------------------------------------------------------------
# MAIN EXECUTION
# ---------------------------------------------------------------------

def main():
    args = parse_arguments()

    if not os.path.exists(args.input):
        print(f"Error: Input folder '{args.input}' not found.")
        sys.exit(1)

    # Define Output Subfolders
    img_output_dir = os.path.join(args.output, 'images')
    vid_output_dir = os.path.join(args.output, 'videos')

    # RECURSIVE SEARCH
    videos = []
    photos = []
    
    print(f"Scanning '{args.input}' recursively...")

    for root, dirs, files in os.walk(args.input):
        for file in files:
            # We store the FULL path to the file
            full_path = os.path.join(root, file)
            
            if not args.skip_videos and file.lower().endswith('.avi'):
                videos.append(full_path)
            elif not args.skip_photos and file.lower().endswith('.mpo'):
                photos.append(full_path)

    if not videos and not photos:
        print(f"No compatible files found in '{args.input}' or its subfolders.")
        sys.exit(0)

    print(f"Found: {len(photos)} Photos | {len(videos)} Videos")
    print("-" * 50)

    # Process Photos
    if photos:
        print("Starting Photo Conversion...")
        for f in photos:
            convert_photo(f, img_output_dir)
        print("-" * 50)

    # Process Videos
    if videos:
        print("Starting Video Conversion...")
        for f in videos:
            convert_video(f, vid_output_dir, args.ffmpeg)
        print("-" * 50)

    print("All tasks completed.")

if __name__ == "__main__":
    main()