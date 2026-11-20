import os
import sys
import argparse
import subprocess
import json
from PIL import Image
from PIL import ExifTags
from datetime import datetime

# ---------------------------------------------------------------------
# SETUP & HELPERS
# ---------------------------------------------------------------------

def parse_arguments():
    parser = argparse.ArgumentParser(description="Convert Fujifilm W3 files to XREAL format (Recursive).")

    # Path Arguments
    parser.add_argument('-i', '--input', default='./input', help="Input folder containing files (searches recursively).")
    parser.add_argument('-o', '--output', default='./output', help="Base output folder.")
    parser.add_argument('--ffmpeg', default='ffmpeg', help="Path to ffmpeg executable.")
    parser.add_argument('--ffprobe', default='ffprobe', help="Path to ffprobe executable.")

    # Filter Arguments
    parser.add_argument('--skip-photos', action='store_true', help="Do not process .MPO photos.")
    parser.add_argument('--skip-videos', action='store_true', help="Do not process .AVI videos.")

    # Metadata Arguments
    parser.add_argument('--xreal', action='store_true', help="Generate hidden .xrealmeta sidecar files during conversion.")
    parser.add_argument('--xreal-metadata-only', action='store_true', help="Scan OUTPUT folder and generate missing .xrealmeta files only (skips conversion).")

    return parser.parse_args()

def create_xreal_metadata(file_path):
    """
    Creates a hidden .[filename_no_ext].xrealmeta file in the same folder.
    Content: {"Is3D":true}
    """
    folder = os.path.dirname(file_path)
    filename = os.path.basename(file_path)

    # Strip extension (e.g. remove .jpg or .mp4)
    filename_no_ext = os.path.splitext(filename)[0]

    # Sidecar filename convention: .filename_no_ext.xrealmeta
    # Note the leading dot!
    meta_name = f".{filename_no_ext}.xrealmeta"
    meta_path = os.path.join(folder, meta_name)

    data = {"Is3D": True}

    try:
        with open(meta_path, 'w') as f:
            json.dump(data, f)
        return True
    except Exception as e:
        print(f"    [ERR] Could not write metadata: {e}")
        return False

def get_timestamp_from_file(filepath):
    try:
        mtime = os.path.getmtime(filepath)
        return datetime.fromtimestamp(mtime)
    except OSError:
        return datetime.now()

def get_video_recording_date(video_path, ffprobe_cmd='ffprobe'):
    """Finds the original recording date anywhere ffprobe can see it:
    format-level tags, stream-level tags (where the W3 stores its EXIF),
    in EXIF ('2017:10:16 15:00:24') or ISO ('2017-10-16T15:00:24') form."""
    candidate_keys = (
        'ExifIFD/DateTimeOriginal', 'ExifIFD/DateTimeDigitized',
        'DateTimeOriginal', 'DateTime', 'DateTimeDigitized',
        'creation_time', 'IDIT', 'ICRD', 'date',
    )
    date_formats = (
        '%Y:%m:%d %H:%M:%S',            # EXIF-style, as in the W3's AVIs
        '%Y-%m-%d %H:%M:%S',            # space-separated ISO variant
        '%Y-%m-%dT%H:%M:%S',            # ISO
        '%Y-%m-%dT%H:%M:%S.%f',         # ISO with fractional seconds
        '%Y-%m-%dT%H:%M:%S%z',          # ISO with UTC offset
        '%a %b %d %H:%M:%S %Y',         # RIFF IDIT style ('Thu Jan 16 12:00:00 2020')
    )
    try:
        result = subprocess.run(
            [ffprobe_cmd, '-v', 'quiet', '-print_format', 'json',
             '-show_format', '-show_streams', video_path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        if result.returncode != 0 or not result.stdout.strip():
            return None
        info = json.loads(result.stdout)

        # Gather candidate values: format tags first, then every stream's tags
        # (later candidates never override an already-parsed earlier one —
        # we return on the first successful parse).
        tags = dict(info.get('format', {}).get('tags', {}))
        for stream in info.get('streams', []):
            for k, v in stream.get('tags', {}).items():
                tags.setdefault(k, v)

        for key in candidate_keys:
            val = tags.get(key)
            if not val or not val.strip():
                continue
            val = val.strip()
            for fmt in date_formats:
                try:
                    parsed = datetime.strptime(val, fmt)
                    if '%z' in fmt:
                        parsed = parsed.replace(tzinfo=None)
                    return parsed
                except ValueError:
                    continue
    except Exception:
        pass
    return None

def get_unique_filename(folder, filename):
    base, ext = os.path.splitext(filename)
    counter = 1
    new_filename = filename
    while os.path.exists(os.path.join(folder, new_filename)):
        new_filename = f"{base}_{counter}{ext}"
        counter += 1
    return new_filename

def set_output_dates(target_path, date_obj):
    """Sets BOTH access and modified timestamps to the metadata-derived date."""
    try:
        ts = date_obj.timestamp()
        os.utime(target_path, (ts, ts))
    except Exception as e:
        print(f"    [WARN] Could not set file dates: {e}")

# ---------------------------------------------------------------------
# METADATA ONLY MODE
# ---------------------------------------------------------------------

def generate_metadata_only(output_base):
    print(f"Scanning '{output_base}' recursively for SV_ files to tag...")
    count = 0
    for root, dirs, files in os.walk(output_base):
        for file in files:
            lower = file.lower()
            if lower.endswith('.jpg') or lower.endswith('.mp4'):
                # Check if it looks like one of our converted files (SV_)
                if "SV_" in file:
                    full_path = os.path.join(root, file)
                    if create_xreal_metadata(full_path):
                        count += 1
    print(f"Generated {count} metadata sidecar files.")

# ---------------------------------------------------------------------
# VIDEO PROCESSING
# ---------------------------------------------------------------------

def convert_video(file_path, output_folder, ffmpeg_cmd, ffprobe_cmd, generate_meta):
    filename = os.path.basename(file_path)
    if not os.path.exists(output_folder): os.makedirs(output_folder)

    # Resolve the recording date: embedded container date first, file mtime as fallback
    date_obj = get_video_recording_date(file_path, ffprobe_cmd)
    if date_obj is None:
        date_obj = get_timestamp_from_file(file_path)

    clean_name = f"SV_{date_obj.strftime('%Y%m%d_%H%M%S')}.mp4"
    clean_name = get_unique_filename(output_folder, clean_name)
    output_path = os.path.join(output_folder, clean_name)

    cmd = [
        ffmpeg_cmd, '-y', '-i', file_path,
        '-filter_complex', '[0:v:0][0:v:1]hstack=inputs=2,format=yuv420p[v]',
        '-map', '[v]', '-map', '0:a',
        '-map_metadata', '0',
        '-metadata', f'creation_time={date_obj.strftime("%Y-%m-%dT%H:%M:%S")}',
        '-c:v', 'libx264', '-crf', '18', '-preset', 'fast',
        '-profile:v', 'high', '-level', '4.0',
        '-color_range', 'tv',
        '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
        '-movflags', '+faststart',
        '-c:a', 'aac', '-b:a', '192k',
        output_path
    ]

    print(f"--> Video: {filename}")
    try:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            set_output_dates(output_path, date_obj)
            print(f"    [OK] Saved as {clean_name}")
            if generate_meta:
                create_xreal_metadata(output_path)
                print("    [+] Metadata created")
        else:
            print(f"    [ERR] FFmpeg failed: {result.stderr}")
    except FileNotFoundError:
        print(f"    [FATAL] FFmpeg not found!")
        sys.exit(1)

# ---------------------------------------------------------------------
# PHOTO PROCESSING
# ---------------------------------------------------------------------

def convert_photo(file_path, output_folder, generate_meta):
    filename = os.path.basename(file_path)
    if not os.path.exists(output_folder): os.makedirs(output_folder)

    try:
        with Image.open(file_path) as im:
            # Capture EXIF from the FIRST frame (left eye) before seeking.
            # The right frame often carries little or no EXIF on the W3.
            im.seek(0)
            left_img = im.copy()
            exif_bytes = im.info.get('exif')
            exif = left_img.getexif()

            date_obj = None
            if exif:
                # DateTimeOriginal (36867) lives in the nested Exif IFD (pointer 34665),
                # not the base IFD that getexif() returns directly.
                exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)
                if 36867 in exif_ifd:
                    try: date_obj = datetime.strptime(exif_ifd[36867], '%Y:%m:%d %H:%M:%S')
                    except: pass
                # Fallback: base-IFD modification date (tag 306), usually close enough
                if date_obj is None and 306 in exif:
                    try: date_obj = datetime.strptime(exif[306], '%Y:%m:%d %H:%M:%S')
                    except: pass

            if not date_obj:
                date_obj = get_timestamp_from_file(file_path)

            try:
                im.seek(1)
                right_img = im.copy()
            except EOFError:
                print(f"    [SKIP] {filename}: Not 3D.")
                return

            w, h = left_img.size
            sbs = Image.new('RGB', (w * 2, h))
            sbs.paste(left_img, (0, 0))
            sbs.paste(right_img, (w, 0))

            clean_name = f"SV_{date_obj.strftime('%Y%m%d_%H%M%S')}.jpg"
            clean_name = get_unique_filename(output_folder, clean_name)
            output_path = os.path.join(output_folder, clean_name)

            if exif_bytes:
                sbs.save(output_path, "JPEG", quality=95, exif=exif_bytes)
            else:
                sbs.save(output_path, "JPEG", quality=95)

            set_output_dates(output_path, date_obj)
            print(f"    [OK] Photo: {filename} -> {clean_name}")

            if generate_meta:
                create_xreal_metadata(output_path)
                print("    [+] Metadata created")

    except Exception as e:
        print(f"    [ERR] {filename}: {e}")

# ---------------------------------------------------------------------
# MAIN EXECUTION
# ---------------------------------------------------------------------

def main():
    args = parse_arguments()

    # MODE: Generate Metadata ONLY (no conversion)
    if args.xreal_metadata_only:
        if not os.path.exists(args.output):
            print(f"Error: Output folder '{args.output}' does not exist.")
            sys.exit(1)
        generate_metadata_only(args.output)
        sys.exit(0)

    # MODE: Standard Conversion
    if not os.path.exists(args.input):
        print(f"Error: Input folder '{args.input}' not found.")
        sys.exit(1)

    img_output_dir = os.path.join(args.output, 'images')
    vid_output_dir = os.path.join(args.output, 'videos')

    videos = []
    photos = []

    print(f"Scanning '{args.input}' recursively...")
    for root, dirs, files in os.walk(args.input):
        for file in files:
            full_path = os.path.join(root, file)
            if not args.skip_videos and file.lower().endswith('.avi'):
                videos.append(full_path)
            elif not args.skip_photos and file.lower().endswith('.mpo'):
                photos.append(full_path)

    if not videos and not photos:
        print(f"No compatible files found.")
        sys.exit(0)

    print(f"Found: {len(photos)} Photos | {len(videos)} Videos")
    if args.xreal:
        print(">> XREAL Metadata generation ENABLED")
    print("-" * 50)

    if photos:
        print("Starting Photo Conversion...")
        for f in photos:
            convert_photo(f, img_output_dir, args.xreal)
        print("-" * 50)

    if videos:
        print("Starting Video Conversion...")
        for f in videos:
            convert_video(f, vid_output_dir, args.ffmpeg, args.ffprobe, args.xreal)
        print("-" * 50)

    print("All tasks completed.")

if __name__ == "__main__":
    main()
