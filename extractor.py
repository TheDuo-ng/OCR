import cv2
import os
import sys
import numpy as np
import datetime
import tkinter as tk
from tkinter import messagebox
import argparse
from tqdm import tqdm

# Import PySceneDetect components
from scenedetect import open_video, SceneManager
from scenedetect.detectors import ContentDetector

# --- CONFIGURATION ---
SCENE_DETECT_THRESHOLD = 12.0
CHANGE_THRESHOLD = 25000
MAX_WINDOW_WIDTH = 1280
MAX_WINDOW_HEIGHT = 720

def select_subtitle_area(video_path):
    """Opens a resized, DPI-aware video player for region selection."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("[ERROR] Could not open video.")
        return None
        
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames == 0:
        print("[ERROR] Video has no frames.")
        return None

    # --- SCALING FIX ---
    original_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    original_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    scale_ratio = min(MAX_WINDOW_WIDTH / original_width, MAX_WINDOW_HEIGHT / original_height)
    
    if scale_ratio >= 1.0: # Don't scale up
        display_width, display_height = original_width, original_height
        scale_ratio = 1.0
    else:
        display_width = int(original_width * scale_ratio)
        display_height = int(original_height * scale_ratio)
    # --- END SCALING FIX ---

    try:
        window_name = "Select Frame (Drag slider, press ENTER to select)"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL) # Use WINDOW_NORMAL for resizability
        cv2.resizeWindow(window_name, display_width, display_height)

        def on_trackbar(val): pass
        cv2.createTrackbar('Timeline', window_name, 0, total_frames - 1, on_trackbar)
    except cv2.error as e:
        print(f"[FATAL_ERROR] Critical OpenCV error while creating GUI: {e}")
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("OpenCV Error", f"Could not create selection GUI. Please check your OpenCV installation.\n\nDetails: {e}")
        return None

    print("[INFO] Guide: Drag the slider to find a frame with subtitles, then press ENTER.")
    
    frame_for_selection = None
    while True:
        current_pos = cv2.getTrackbarPos('Timeline', window_name)
        cap.set(cv2.CAP_PROP_POS_FRAMES, current_pos)
        ret, frame = cap.read()
        if not ret: break
        
        display_frame = cv2.resize(frame, (display_width, display_height))
        cv2.imshow(window_name, display_frame)
        
        key = cv2.waitKey(30) & 0xFF
        if key == 13: # Enter
            frame_for_selection = frame # Use the original full-res frame
            break
        if key == 27: # Esc
            break
    cv2.destroyWindow(window_name)
    cap.release()

    if frame_for_selection is None: return None
    
    messagebox.showinfo("Instruction", "Now, draw a rectangle around the TEXT ONLY.\n\nIMPORTANT: Avoid including any background elements, progress bars, or underlines to improve OCR accuracy.")
    
    display_frame_for_roi = cv2.resize(frame_for_selection, (display_width, display_height))
    roi_window_title = "Draw Subtitle Region (TEXT ONLY) | Press ENTER to confirm"
    roi = cv2.selectROI(roi_window_title, display_frame_for_roi, fromCenter=False, showCrosshair=True)
    cv2.destroyAllWindows()

    if roi == (0, 0, 0, 0): return None
    
    # --- CONVERT ROI COORDINATES BACK TO ORIGINAL SCALE ---
    rx, ry, rw, rh = roi
    original_x = int(rx / scale_ratio)
    original_y = int(ry / scale_ratio)
    original_w = int(rw / scale_ratio)
    original_h = int(rh / scale_ratio)
    # --- END CONVERSION ---

    return (original_y, original_y + original_h, original_x, original_x + original_w)

def frames_to_time_str(frame_count, fps):
    """Converts frame count to a HH_MM_SS_ms time string."""
    if fps == 0: fps = 25 # Avoid division by zero
    seconds = frame_count / float(fps)
    frac, whole = np.modf(seconds)
    td = datetime.timedelta(seconds=whole)
    ms = int(frac * 1000)
    hours, remainder = divmod(int(td.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    time_str = f"{hours:02d}_{minutes:02d}_{seconds:02d}"
    return f"{time_str}_{ms:03d}"

def main(video_path, roi=None, scene_threshold=SCENE_DETECT_THRESHOLD, change_threshold=CHANGE_THRESHOLD):
    print("================ STARTING IMAGE EXTRACTION (Hybrid Mode) ================")

    base_path = os.path.splitext(video_path)[0]
    temp_folder = base_path + "_sub_images"

    if not os.path.exists(temp_folder):
        os.makedirs(temp_folder)
        print(f"[INFO] Created temp folder: {temp_folder}")
    else:
        print("[INFO] Clearing old images from temp folder...")
        for f in os.listdir(temp_folder):
            if f.endswith('.png'):
                os.remove(os.path.join(temp_folder, f))

    crop_rect = roi if roi else select_subtitle_area(video_path)
    if not crop_rect:
        print("[ERROR] No subtitle region selected. Exiting.")
        return

    print("\n--- Step 1.1: Detecting scenes with PySceneDetect ---")
    video = open_video(video_path)
    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector(threshold=scene_threshold))
    scene_manager.detect_scenes(video=video, show_progress=True)
    scene_list = scene_manager.get_scene_list()
    print(f"[INFO] Scene detection complete. Found {len(scene_list)} scenes.")
    
    if not scene_list:
        print("[WARNING] No scenes were detected. Nothing to extract.")
        return

    print("\n--- Step 1.2: Analyzing each scene for subtitles ---")
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    y1, y2, x1, x2 = crop_rect
    total_images_saved = 0

    for i, (start_time, end_time) in enumerate(tqdm(scene_list, desc="Scenes", unit="scene", ascii=True)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_time.get_frames())

        last_img = None
        subtitle_present = False
        subtitle_start_frame = 0

        frame_range = range(start_time.get_frames(), end_time.get_frames())
        for frame_number in tqdm(frame_range, desc=f"Scene {i+1}/{len(scene_list)}", unit="frame", ascii=True, leave=False):
            ret, frame = cap.read()
            if not ret:
                break

            sub_region = frame[y1:y2, x1:x2]

            if last_img is not None:
                diff = cv2.absdiff(sub_region, last_img)
                diff_score = np.sum(diff)

                if diff_score > change_threshold:
                    if not subtitle_present:
                        subtitle_present = True
                        subtitle_start_frame = frame_number
                else:
                    if subtitle_present:
                        sub_end_frame = frame_number - 1
                        if sub_end_frame > subtitle_start_frame + int(fps * 0.2):
                            start_time_str = frames_to_time_str(subtitle_start_frame, fps)
                            end_time_str = frames_to_time_str(sub_end_frame, fps)
                            img_name = f"{start_time_str}__{end_time_str}.png"
                            img_path = os.path.join(temp_folder, img_name)
                            cv2.imwrite(img_path, last_img)
                            total_images_saved += 1
                        subtitle_present = False

            last_img = sub_region.copy()

        if subtitle_present and last_img is not None:
            sub_end_frame = end_time.get_frames() - 1
            if sub_end_frame > subtitle_start_frame + int(fps * 0.2):
                start_time_str = frames_to_time_str(subtitle_start_frame, fps)
                end_time_str = frames_to_time_str(sub_end_frame, fps)
                img_name = f"{start_time_str}__{end_time_str}.png"
                img_path = os.path.join(temp_folder, img_name)
                cv2.imwrite(img_path, last_img)
                total_images_saved += 1

    print(f"\n[SUCCESS] Finished extraction. Total images saved: {total_images_saved}.")
    cap.release()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract subtitle images from a video using a hybrid scene/difference detection method.")
    parser.add_argument('--video_path', required=True, help='Path to the video file.')
    parser.add_argument('--roi', type=str, help='Bypass interactive selection with coordinates y1,y2,x1,x2.')
    parser.add_argument('--scene_threshold', type=float, default=SCENE_DETECT_THRESHOLD,
                        help=f'Scene detection threshold (default: {SCENE_DETECT_THRESHOLD}).')
    parser.add_argument('--change_threshold', type=float, default=CHANGE_THRESHOLD,
                        help=f'Pixel change threshold (default: {CHANGE_THRESHOLD}).')

    args = parser.parse_args()

    roi = None
    if args.roi:
        try:
            y1, y2, x1, x2 = map(int, args.roi.split(','))
            roi = (y1, y2, x1, x2)
        except ValueError:
            print("[ERROR] Invalid --roi format. Expected y1,y2,x1,x2.")
            sys.exit(1)

    main(args.video_path, roi=roi, scene_threshold=args.scene_threshold, change_threshold=args.change_threshold)
