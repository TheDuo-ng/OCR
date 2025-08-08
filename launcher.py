import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import subprocess
import os
import threading
import sys
import requests
import json

# --- FIX FOR HIGH-DPI SCALING ON WINDOWS ---
try:
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception as e:
    print(f"[WARNING] Could not set DPI awareness: {e}")
# --- END FIX ---

class OcrLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title("OCR & Translate Controller v4.0")
        self.root.geometry("800x700")
        self.root.configure(bg="#2E2E2E")

        self.video_path = tk.StringVar()
        self.image_folder = tk.StringVar()
        self.srt_path = tk.StringVar()
        self.api_key = tk.StringVar()
        self.process = None

        # --- Style Configuration (Dark Mode) ---
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TLabel", background="#2E2E2E", foreground="white")
        style.configure("TFrame", background="#2E2E2E")
        style.configure("TButton", background="#555555", foreground="white", borderwidth=1)
        style.map("TButton", background=[('active', '#666666')])
        style.configure("TEntry", fieldbackground="#555555", foreground="white", insertbackground="white")
        style.configure("TLabelframe", background="#2E2E2E", bordercolor="gray")
        style.configure("TLabelframe.Label", background="#2E2E2E", foreground="white")
        style.configure("TCombobox", fieldbackground="#555555", background="#444444", foreground="white")
        
        # --- GUI ---
        main_frame = ttk.Frame(root, padding="10 10 10 10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Step 1: Video Selection Section ---
        video_frame = ttk.LabelFrame(main_frame, text="Step 1: Select Video and Extract Subtitle Images", padding="10 10 10 10")
        video_frame.pack(fill=tk.X, pady=5)
        ttk.Label(video_frame, text="Video File:").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(video_frame, textvariable=self.video_path, width=70).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(video_frame, text="Browse...", command=self.select_video).grid(row=0, column=2)
        self.extract_button = ttk.Button(video_frame, text="🚀 Start Image Extraction", command=self.run_extractor)
        self.extract_button.grid(row=1, column=1, pady=10, sticky="w")

        # --- Step 2: OCR Section ---
        ocr_frame = ttk.LabelFrame(main_frame, text="Step 2: Run OCR and Create .SRT File", padding="10 10 10 10")
        ocr_frame.pack(fill=tk.X, pady=5)
        ttk.Label(ocr_frame, text="Image Folder:").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(ocr_frame, textvariable=self.image_folder, width=70, state='readonly').grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Label(ocr_frame, text="Save SRT File:").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(ocr_frame, textvariable=self.srt_path, width=70, state='readonly').grid(row=1, column=1, sticky="ew", padx=5)
        self.ocr_button = ttk.Button(ocr_frame, text="✨ Run OCR and Create SRT", command=self.run_ocr_processor)
        self.ocr_button.grid(row=2, column=1, pady=10, sticky="w")

        # --- Step 3: Translation Section ---
        translate_frame = ttk.LabelFrame(main_frame, text="Step 3: Translate SRT File with Gemini", padding="10 10 10 10")
        translate_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(translate_frame, text="Gemini API Key:").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(translate_frame, textvariable=self.api_key, width=70, show="*").grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(translate_frame, text="Load Models", command=self.load_gemini_models).grid(row=0, column=2)
        
        ttk.Label(translate_frame, text="Select Model:").grid(row=1, column=0, sticky="w", pady=2)
        self.model_selector = ttk.Combobox(translate_frame, values=["Enter API Key and Load Models"], state="readonly")
        self.model_selector.current(0)
        self.model_selector.grid(row=1, column=1, sticky="w", padx=5)

        ttk.Label(translate_frame, text="Translation Context (Optional):").grid(row=2, column=0, sticky="nw", pady=2)
        self.context_text = tk.Text(translate_frame, height=3, width=70, bg="#555555", fg="white", insertbackground="white")
        self.context_text.grid(row=2, column=1, sticky="ew", padx=5)

        self.translate_button = ttk.Button(translate_frame, text="🌐 Translate SRT to Vietnamese", command=self.run_translator)
        self.translate_button.grid(row=3, column=1, pady=10, sticky="w")
        
        # --- Stop Button ---
        self.stop_button = ttk.Button(main_frame, text="❌ Stop Current Process", command=self.stop_process, state="disabled")
        self.stop_button.pack(pady=5)

        # --- Log Console ---
        log_frame = ttk.LabelFrame(main_frame, text="Log", padding="10 10 10 10")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state='disabled', bg="#1E1E1E", fg="lightgray")
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def log(self, message):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message + '\n')
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
        self.root.update_idletasks()

    def select_video(self):
        path = filedialog.askopenfilename(title="Select Video File", filetypes=(("Video files", "*.mp4 *.avi *.mkv *.mov"), ("All files", "*.*")))
        if path:
            self.video_path.set(path)
            base_path = os.path.splitext(path)[0]
            self.image_folder.set(base_path + "_sub_images")
            self.srt_path.set(base_path + ".srt")
            self.log(f"Video selected: {path}")

    def run_script(self, command):
        try:
            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='ignore', creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            threading.Thread(target=self.read_process_output, daemon=True).start()
        except FileNotFoundError:
            self.log(f"ERROR: Script file not found. Make sure all .py files are in the same directory.")
            messagebox.showerror("Error", "Script file not found. Make sure all .py files are in the same directory.")
            self.reset_buttons()
        except Exception as e:
            self.log(f"Error running script: {e}")
            messagebox.showerror("Error", f"Error running script: {e}")
            self.reset_buttons()

    def read_process_output(self):
        while True:
            if self.process is None: break
            output = self.process.stdout.readline()
            if output:
                self.log(output.strip())
            elif self.process.poll() is not None:
                break
        self.log("--- Process Finished ---")
        self.reset_buttons()

    def run_extractor(self):
        video = self.video_path.get()
        if not video:
            messagebox.showwarning("Warning", "Please select a video file first.")
            return
        self.log("--- Starting Step 1: Extracting Subtitle Images ---")
        self.disable_buttons()
        command = [sys.executable, "extractor.py", "--video_path", video]
        self.run_script(command)

    def run_ocr_processor(self):
        image_folder = self.image_folder.get()
        srt_path = self.srt_path.get()
        if not image_folder or not srt_path:
            messagebox.showwarning("Warning", "Missing image folder or SRT file path. Please complete Step 1 first.")
            return
        if not os.path.exists(image_folder):
             messagebox.showerror("Error", f"Image folder '{image_folder}' does not exist!")
             return
        self.log("--- Starting Step 2: Running OCR and Creating SRT ---")
        self.disable_buttons()
        command = [sys.executable, "ocr_processor.py", "--image_folder", image_folder, "--srt_path", srt_path]
        self.run_script(command)
        
    def run_translator(self):
        srt_path = self.srt_path.get()
        api_key = self.api_key.get()
        model = self.model_selector.get()
        context = self.context_text.get("1.0", tk.END).strip()

        if not srt_path:
            messagebox.showwarning("Warning", "SRT file path is missing. Please complete Step 1 & 2 first.")
            return
        if not api_key:
            messagebox.showwarning("Warning", "Please enter your Gemini API Key.")
            return
        if not os.path.exists(srt_path):
            messagebox.showerror("Error", f"SRT file '{srt_path}' does not exist!")
            return
            
        self.log("--- Starting Step 3: Translating SRT file ---")
        self.disable_buttons()
        output_path = os.path.splitext(srt_path)[0] + ".vi.srt"
        
        command = [sys.executable, "translator.py", 
                   "--input_srt", srt_path, 
                   "--output_srt", output_path, 
                   "--api_key", api_key,
                   "--model", model]
        
        if context:
            command.extend(["--context", context])
            
        self.run_script(command)

    def load_gemini_models(self):
        api_key = self.api_key.get()
        if not api_key:
            messagebox.showwarning("Warning", "Please enter your Gemini API Key first.")
            return
        
        self.log("--- Fetching available Gemini models... ---")
        self.translate_button.config(state="disabled")
        
        def fetch():
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
                response = requests.get(url)
                response.raise_for_status()
                data = response.json()
                
                # Filter for models that support 'generateContent'
                models = [m['name'].replace('models/', '') for m in data.get('models', []) 
                          if 'generateContent' in m.get('supportedGenerationMethods', [])]
                
                if models:
                    self.log(f"Found models: {', '.join(models)}")
                    self.model_selector['values'] = models
                    self.model_selector.current(0)
                else:
                    self.log("No compatible models found or API key is invalid.")
                    self.model_selector['values'] = ["No compatible models found"]
                    self.model_selector.current(0)

            except requests.exceptions.RequestException as e:
                self.log(f"Error fetching models: {e}")
                messagebox.showerror("API Error", f"Could not fetch models. Check your API key and internet connection.\n\nDetails: {e}")
            finally:
                self.translate_button.config(state="normal")

        threading.Thread(target=fetch, daemon=True).start()

    def stop_process(self):
        if self.process:
            self.log("--- Stopping process... ---")
            self.process.terminate()
            self.process = None
            self.reset_buttons()

    def disable_buttons(self):
        self.extract_button.config(state="disabled")
        self.ocr_button.config(state="disabled")
        self.translate_button.config(state="disabled")
        self.stop_button.config(state="normal")
        
    def reset_buttons(self):
        self.extract_button.config(state="normal")
        self.ocr_button.config(state="normal")
        self.translate_button.config(state="normal")
        self.stop_button.config(state="disabled")
        
    def on_closing(self):
        if self.process and messagebox.askyesno("Confirm", "A process is currently running. Are you sure you want to exit and stop it?"):
            self.stop_process()
            self.root.destroy()
        else:
            self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = OcrLauncher(root)
    root.mainloop()
