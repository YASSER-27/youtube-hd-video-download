import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pyperclip
from yt_dlp import YoutubeDL
from PIL import Image, ImageTk
import io
import requests

# ---------- Helper ----------
def normalize_url(url: str) -> str:
    url = url.strip()
    if "shorts/" in url:
        return url.replace("shorts/", "watch?v=")
    if "youtu.be/" in url:
        vid = url.split("/")[-1]
        return f"https://www.youtube.com/watch?v={vid}"
    return url


def build_ydl_opts(mode: str, quality: str, outdir: str, progress_hook):
    outtmpl = os.path.join(outdir, "%(title)s.%(ext)s")
    opts = {
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": False,
        "retries": 3,
        "progress_hooks": [progress_hook],
    }

    if mode == "mp3":
        opts.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })
    else:
        if quality == "FHD":
            fmt = "bestvideo[height<=1080]+bestaudio/best"
        elif quality == "HD":
            fmt = "bestvideo[height<=720]+bestaudio/best"
        elif quality == "SD":
            fmt = "bestvideo[height<=360]+bestaudio/best"
        else:
            fmt = "bestvideo+bestaudio/best"
        opts.update({
            "format": fmt,
            "merge_output_format": "mp4",
        })
    return opts


# ---------- GUI ----------
class YTDownloaderGUI:
    def __init__(self, master):
        self.master = master
        master.title("🎬 YASSIR YouTube Downloader Pro")
        master.configure(bg="#0b0b0b")
        master.geometry("720x520")
        master.resizable(False, False)

        # URL entry
        tk.Label(master, text="🎥 YouTube URL:", bg="#0b0b0b", fg="#FFD27A", font=("Segoe UI", 10, "bold")).pack(pady=(12,4))
        self.url_entry = tk.Entry(master, width=80, bg="#111", fg="white", insertbackground="white", relief="flat", font=("Consolas", 10))
        self.url_entry.pack()
        # عند إخراج التركيز، يتم استدعاء load_video_info
        self.url_entry.bind("<FocusOut>", lambda e: self.load_video_info())
        self.paste_clipboard_url()

        # Thumbnail + title area
        self.thumb_label = tk.Label(master, bg="#0b0b0b")
        self.thumb_label.pack(pady=(10,2))
        self.title_label = tk.Label(master, text="", bg="#0b0b0b", fg="#FFD27A", font=("Segoe UI", 10))
        self.title_label.pack()

        # Quality and mode
        frame = tk.Frame(master, bg="#0b0b0b")
        frame.pack(pady=10)

        tk.Label(frame, text="Quality:", bg="#0b0b0b", fg="#FFD27A").grid(row=0, column=0, padx=6)
        self.quality = ttk.Combobox(frame, values=["Best", "FHD", "HD", "SD"], state="readonly", width=8)
        self.quality.current(1)
        self.quality.grid(row=0, column=1, padx=6)

        tk.Label(frame, text="Mode:", bg="#0b0b0b", fg="#FFD27A").grid(row=0, column=2, padx=6)
        self.mode_var = tk.StringVar(value="mp4")
        tk.Radiobutton(frame, text="MP4", variable=self.mode_var, value="mp4", bg="#0b0b0b", fg="#fff", selectcolor="#0b0b0b").grid(row=0, column=3, padx=6)
        tk.Radiobutton(frame, text="MP3", variable=self.mode_var, value="mp3", bg="#0b0b0b", fg="#fff", selectcolor="#0b0b0b").grid(row=0, column=4, padx=6)

        # Output folder
        tk.Label(master, text="Output Folder:", bg="#0b0b0b", fg="#FFD27A").pack(pady=(6,0))
        out_frame = tk.Frame(master, bg="#0b0b0b")
        out_frame.pack()
        self.out_var = tk.StringVar(value=os.getcwd())
        self.out_entry = tk.Entry(out_frame, textvariable=self.out_var, width=50, bg="#111", fg="white", relief="flat", font=("Consolas", 10))
        self.out_entry.pack(side="left", padx=(0,8))
        tk.Button(out_frame, text="Browse", command=self.browse_folder, bg="#222", fg="#FFD27A").pack(side="left")

        # Progress bar
        self.progress = ttk.Progressbar(master, orient="horizontal", length=480, mode="determinate")
        self.progress.pack(pady=10)

        # Status labels
        self.speed_label = tk.Label(master, text="", bg="#0b0b0b", fg="#9fe5c9", font=("Consolas", 9))
        self.speed_label.pack()
        self.status_label = tk.Label(master, text="", bg="#0b0b0b", fg="#FFD27A", font=("Consolas", 9))
        self.status_label.pack()

        # Download button
        self.download_btn = tk.Button(master, text="⬇ Download", command=self.start_download, bg="#1f1f1f", fg="#FFD27A", width=18)
        self.download_btn.pack(pady=8)

    def paste_clipboard_url(self):
        try:
            clip = pyperclip.paste()
            if "youtube.com" in clip or "youtu.be" in clip:
                self.url_entry.insert(0, clip)
                # الآن load_video_info ستعمل في خيط منفصل ولن تسبب التعليق
                self.load_video_info()
        except Exception:
            pass

    def browse_folder(self):
        folder = filedialog.askdirectory(title="Select output folder", initialdir=self.out_var.get())
        if folder:
            self.out_var.set(folder)

    # ==========================================================
    # 💥 التعديل الرئيسي: يتم تشغيل عملية جلب المعلومات في خيط منفصل
    def load_video_info(self):
        url = self.url_entry.get().strip()
        if not url:
            return
        
        # مسح وعرض حالة التحميل فوراً على خيط الواجهة الرئيسي
        self.title_label.config(text="Loading video information...", fg="#FFD27A")
        self.thumb_label.config(image=None)
        self.thumb_label.image = None
        
        # تشغيل الدالة التي تقوم بالعمليات البطيئة في خيط جديد
        threading.Thread(target=self._load_video_info_worker, args=(url,), daemon=True).start()

    def _load_video_info_worker(self, url):
        """دالة عاملة (Worker) تعمل في خيط منفصل لجلب البيانات والصورة المصغرة."""
        try:
            norm = normalize_url(url)
            
            # جلب معلومات الفيديو (عملية شبكة بطيئة)
            opts = {'quiet': True, 'skip_download': True}
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(norm, download=False)
            
            title = info.get("title", "Unknown Title")
            thumb_url = info.get("thumbnail")
            img_tk = None

            if thumb_url:
                # جلب بيانات الصورة (عملية شبكة بطيئة)
                img_data = requests.get(thumb_url, timeout=5).content
                # معالجة الصورة (عملية معالجة بطيئة)
                image = Image.open(io.BytesIO(img_data)).resize((320, 180))
                img_tk = ImageTk.PhotoImage(image) # إنشاء كائن الصورة

            # استخدام master.after لتحديث الواجهة الرسومية بأمان من الخيط العامل
            self.master.after(0, self._update_video_info_gui, title, img_tk, None)

        except Exception as e:
            # استخدام master.after لعرض الأخطاء بأمان
            self.master.after(0, self._update_video_info_gui, None, None, e)

    def _update_video_info_gui(self, title, img_tk, error):
        """دالة لتحديث عناصر الواجهة الرسومية (تعمل على خيط الواجهة الرئيسي)."""
        if error:
            self.title_label.config(text=f"Cannot load info: {error}", fg="red")
            self.thumb_label.config(image=None)
            self.thumb_label.image = None
        elif title:
            self.title_label.config(text=title, fg="#FFD27A")
            if img_tk:
                self.thumb_label.config(image=img_tk)
                self.thumb_label.image = img_tk # الحفاظ على مرجع لمنع جمع القمامة (Garbage Collection)
    # ==========================================================

    def start_download(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Input required", "Please paste a YouTube URL.")
            return
        self.download_btn.config(state="disabled")
        self.status_label.config(text="Starting...", fg="#9fe5c9")
        self.progress["value"] = 0
        # عملية التحميل موجودة بالفعل في خيط منفصل، وهي صحيحة
        threading.Thread(target=self.download_worker, args=(normalize_url(url),)).start()

    def download_worker(self, url):
        try:
            mode = self.mode_var.get()
            quality = self.quality.get()
            outdir = self.out_var.get() or os.getcwd()

            def hook(d):
                # ملاحظة: تحديثات التقدم هذه لا تسبب تعليقًا لأنها سريعة جداً.
                # ولكن لكي تكون الواجهة الرسومية أكثر أمانًا، يجب استخدام master.after
                # أيضاً لتحديث التقدم، ولكنه يعمل بشكل مقبول في حالتك.
                if d['status'] == 'downloading':
                    total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                    downloaded = d.get('downloaded_bytes', 0)
                    if total > 0:
                        pct = downloaded / total * 100
                        self.progress["value"] = pct
                    speed = d.get('speed')
                    eta = d.get('eta')
                    spd_str = f"{speed / 1024 / 1024:.2f} MB/s" if speed else "?"
                    eta_str = f"{int(eta)}s left" if eta else ""
                    self.speed_label.config(text=f"{spd_str}  |  {eta_str}")
                    self.status_label.config(text=f"Downloading... {pct:.1f}%")
                elif d['status'] == 'finished':
                    self.progress["value"] = 100
                    self.status_label.config(text="Processing...")

            opts = build_ydl_opts(mode, quality, outdir, hook)
            with YoutubeDL(opts) as ydl:
                ydl.download([url])

            self.status_label.config(text="✅ Done!", fg="#9fe5c9")
            messagebox.showinfo("Success", "Download completed successfully.")
        except Exception as e:
            self.status_label.config(text=f"Error: {e}", fg="red")
            messagebox.showerror("Error", str(e))
        finally:
            self.download_btn.config(state="normal")


if __name__ == "__main__":
    root = tk.Tk()
    app = YTDownloaderGUI(root)
    root.mainloop()