import os
import sys
import threading
import time
import shutil
import subprocess
import re
from pathlib import Path

# GPU & BROWSER FLAGS
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--enable-gpu-rasterization --ignore-gpu-blocklist --num-raster-threads=4"
)

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QComboBox, QTextEdit, QFileDialog,
    QFrame, QProgressBar, QMenu, QScrollArea, QLabel, QMessageBox
)

from PyQt6.QtGui import QIcon

from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from PyQt6.QtCore import QUrl, pyqtSignal, QObject, Qt

# CONFIG
APP_DIR = r"C:\Program Files\ProWeb Media Downloader"
PROFILE_DIR = os.path.join(os.environ.get("LOCALAPPDATA", str(Path.home())), "ProWeb Media Downloader")
COOKIE_PATH = os.path.join(PROFILE_DIR, "Network", "Cookies")

YT_DLP = os.path.join(APP_DIR, "yt-dlp.exe")
FFMPEG_EXE = os.path.join(APP_DIR, "ffmpeg.exe") 
CREATE_NO_WINDOW = 0x08000000

os.makedirs(PROFILE_DIR, exist_ok=True)

AUDIO_FORMATS = {"mp3", "m4a", "ogg", "wav"}

def detect_gpu_vendor():
    try:
        cmd = 'powershell -command "Get-CimInstance -ClassName Win32_VideoController | Select-Object -ExpandProperty Name"'
        output = subprocess.check_output(cmd, shell=True, text=True, creationflags=CREATE_NO_WINDOW).lower()
        if 'nvidia' in output: return 'nvidia'
        elif 'amd' in output or 'radeon' in output: return 'amd'
        elif 'intel' in output or 'arc' in output: return 'intel'
    except: pass
    return 'cpu'

GPU_VENDOR = detect_gpu_vendor()

def clean_filename(name: str) -> str:
    name = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_", ".", "(", ")", "[", "]")).strip()
    return re.sub(r"\s+", " ", name) or "Video"

def safe_remove(path: str):
    if path and os.path.exists(path):
        try: os.remove(path)
        except: pass

def copy_cookie_db(src: str, dst: str):
    if not os.path.exists(src): return
    for _ in range(3):
        try:
            shutil.copy2(src, dst)
            return
        except: time.sleep(0.2)

class WorkerSignals(QObject):
    log = pyqtSignal(str, str)
    status = pyqtSignal(str, str)
    progress = pyqtSignal(str, int)

class LogWindow(QMainWindow):
    def __init__(self, title):
        super().__init__()
        self.setWindowTitle(f"Log: {title}")
        self.resize(700, 500)
        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setStyleSheet("background-color: black; color: #00FF00; font-family: 'Consolas'; font-size: 10pt;")
        self.setCentralWidget(self.text_area)

class DownloadItem(QFrame):
    def __init__(self, job_id, title, url, parent_app):
        super().__init__()
        self.job_id, self.url, self.parent_app = job_id, url, parent_app
        self.is_cancelled, self.current_processes = False, []
        self.log_window = LogWindow(title)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("QFrame { background: #1e1e1e; color: white; border-radius: 8px; border: 1px solid #333; margin-bottom: 5px; }")
        self.setFixedHeight(115)
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-weight: bold; color: #27ae60; border:none;")
        header.addWidget(self.title_label, stretch=1)
        self.menu_btn = QPushButton("⋮")
        self.menu_btn.setFixedWidth(30)
        self.menu_btn.setStyleSheet("background: transparent; border: none; font-size: 20px; color: white;")
        self.menu_btn.clicked.connect(self.show_context_menu)
        header.addWidget(self.menu_btn)
        layout.addLayout(header)
        self.pbar = QProgressBar()
        self.pbar.setStyleSheet("QProgressBar { border: 1px solid #444; border-radius: 5px; text-align: center; } QProgressBar::chunk { background-color: #27ae60; }")
        layout.addWidget(self.pbar)
        self.status_label = QLabel("Queued...")
        layout.addWidget(self.status_label)

    def show_context_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #2b2b2b; color: white; }")
        nav_act, log_act, can_act = menu.addAction("🌐 Navigate"), menu.addAction("📋 Log"), menu.addAction("❌ Stop")
        action = menu.exec(self.menu_btn.mapToGlobal(self.menu_btn.rect().bottomLeft()))
        if action == nav_act: self.parent_app.browser.setUrl(QUrl(self.url))
        elif action == log_act: self.log_window.show()
        elif action == can_act: self.cancel_download()

    def cancel_download(self):
        self.is_cancelled = True
        for p in self.current_processes:
            try: subprocess.run(['taskkill', '/F', '/T', '/PID', str(p.pid)], creationflags=CREATE_NO_WINDOW, check=False)
            except: pass
        self.status_label.setText("Stopped")

class ProWebMediaDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ProWeb Media Downloader")
        self.setWindowIcon(QIcon("icon.ico"))
        self.setGeometry(100, 100, 1550, 920)
        self.target_folder = os.path.join(os.environ.get("USERPROFILE", str(Path.home())), "Downloads")
        self.items, self.signals = {}, WorkerSignals()
        self.signals.log.connect(self._handle_log)
        self.signals.status.connect(self._handle_status)
        self.signals.progress.connect(self._handle_progress)
        self.init_ui()

    def init_ui(self):
        central, layout, toolbar = QWidget(), QVBoxLayout(), QHBoxLayout()
        
        # --- BROWSER NAVIGATION ---
        self.back_btn = QPushButton(" < ")
        self.back_btn.setFixedWidth(35)
        self.back_btn.setStyleSheet("font-weight: bold; font-size: 16px; color: #27ae60;")
        self.fwd_btn = QPushButton(" > ")
        self.fwd_btn.setFixedWidth(35)
        self.fwd_btn.setStyleSheet("font-weight: bold; font-size: 16px; color: #27ae60;")
        
        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("Paste URL here...")
        
        toolbar.addWidget(self.back_btn)
        toolbar.addWidget(self.fwd_btn)
        toolbar.addWidget(self.url_bar, stretch=2)
        
        self.path_display = QLineEdit(self.target_folder)
        self.path_display.setReadOnly(True)
        toolbar.addWidget(self.path_display)
        self.browse_btn = QPushButton("📁")
        self.browse_btn.clicked.connect(self.choose_folder)
        toolbar.addWidget(self.browse_btn)
        
        self.res_box = QComboBox()
        self.res_box.addItems(["144p", "240p", "360p", "480p", "720p", "1080p", "1440p", "2160p"])
        self.res_box.setCurrentText("1080p")
        toolbar.addWidget(self.res_box)
        
        self.fps_box = QComboBox()
        self.fps_box.addItems([str(x) for x in range(5, 65, 5)])
        self.fps_box.setCurrentText("60")
        toolbar.addWidget(self.fps_box)
        
        self.codec_box = QComboBox()
        self.codec_box.addItems(["libx264", "libx265", "libvpx"])
        toolbar.addWidget(self.codec_box)
        
        self.audio_q_box = QComboBox()
        self.audio_q_box.addItems(["128 kbps", "192 kbps", "256 kbps", "320 kbps"])
        self.audio_q_box.setCurrentText("192 kbps")
        toolbar.addWidget(self.audio_q_box)
        
        self.format_box = QComboBox()
        self.format_box.addItems(["mp4", "mkv", "avi", "mov", "webm", "mp3", "m4a", "ogg", "wav"])
        self.format_box.currentTextChanged.connect(self.update_ui_state)
        toolbar.addWidget(self.format_box)
        
        self.download_btn = QPushButton("🚀 START")
        self.download_btn.clicked.connect(self.handle_download)
        toolbar.addWidget(self.download_btn)
        
        # --- BROWSER ENGINE ---
        self.browser = QWebEngineView()
        self.profile = QWebEngineProfile("ProWebStorage", self.browser)
        self.profile.setPersistentStoragePath(PROFILE_DIR)
        self.profile.setCachePath(PROFILE_DIR)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        
        self.page = QWebEnginePage(self.profile, self.browser)
        self.browser.setPage(self.page)
        self.browser.setUrl(QUrl("https://www.youtube.com"))
        self.browser.urlChanged.connect(lambda q: self.url_bar.setText(q.toString()))
        
        self.back_btn.clicked.connect(self.browser.back)
        self.fwd_btn.clicked.connect(self.browser.forward)

        self.queue_container = QWidget()
        self.queue_layout = QVBoxLayout(self.queue_container)
        self.queue_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll = QScrollArea()
        scroll.setWidget(self.queue_container); scroll.setWidgetResizable(True); scroll.setFixedWidth(350)
        
        main_box = QHBoxLayout()
        main_box.addWidget(self.browser, stretch=1); main_box.addWidget(scroll)
        layout.addLayout(toolbar); layout.addLayout(main_box)
        central.setLayout(layout); self.setCentralWidget(central)
        self.update_ui_state(self.format_box.currentText())

    def update_ui_state(self, fmt):
        is_audio = fmt in AUDIO_FORMATS
        for w in [self.res_box, self.fps_box, self.codec_box]:
            w.setEnabled(not is_audio)
            w.setStyleSheet("background-color: #333; color: #777;" if is_audio else "")

    def choose_folder(self):
        f = QFileDialog.getExistingDirectory(self, "Select Folder")
        if f: self.path_display.setText(f); self.target_folder = f

    def _handle_log(self, jid, msg):
        if jid in self.items and msg.strip():
            self.items[jid].log_window.text_area.append(msg.strip())

    def _handle_status(self, jid, status):
        if jid in self.items: self.items[jid].status_label.setText(status)

    def _handle_progress(self, jid, val):
        if jid in self.items: self.items[jid].pbar.setValue(val)

    def get_auto_hw_codec(self, codec: str):
        c = codec.lower()
        if c == "libvpx": return "libvpx-vp9"
        if c == "libx264":
            if GPU_VENDOR == 'nvidia': return "h264_nvenc"
            if GPU_VENDOR == 'amd': return "h264_amf"
            if GPU_VENDOR == 'intel': return "h264_qsv"
        if c == "libx265":
            if GPU_VENDOR == 'nvidia': return "hevc_nvenc"
            if GPU_VENDOR == 'amd': return "hevc_amf"
            if GPU_VENDOR == 'intel': return "hevc_qsv"
        return c

    def handle_download(self):
        url = self.url_bar.text().strip()
        if not url: return

        fmt = self.format_box.currentText()
        cdc = self.codec_box.currentText()
        
        error_msg = None
        if cdc == "libvpx" and fmt in ["mov", "avi", "mp4"]:
            error_msg = f"Codec <b>VP9 (libvpx)</b> only works with <b>.webm</b> or <b>.mkv</b>."
        elif cdc == "libx265" and fmt == "avi":
            error_msg = f"Modern codec <b>H.265 (libx265)</b> is incompatible with the legacy <b>.avi</b> container."
        elif cdc == "libx264" and fmt == "webm":
            error_msg = f"<b>.webm</b> files do not support <b>H.264 (libx264)</b>. Choose .mp4 or .mkv."

        if error_msg:
            msg = QMessageBox(self)
            msg.setWindowTitle("Unsupported Format")
            msg.setText(f"<b>Oops!</b> Incompatible settings.")
            msg.setInformativeText(f"{error_msg}<br><br>Adjust your selection to proceed.")
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setStyleSheet("QMessageBox { background-color: #1e1e1e; border: 1px solid #27ae60; } QLabel { color: white; } QPushButton { background-color: #27ae60; color: white; font-weight: bold; padding: 5px 15px; }")
            msg.exec()
            return

        jid = f"J{int(time.time() * 1000)}"
        snap = {"res": self.res_box.currentText(), "fps": self.fps_box.currentText(), "codec": self.codec_box.currentText(),
                "audio_q": self.audio_q_box.currentText().split(" ")[0] + "k", "format": self.format_box.currentText(), "target": self.target_folder}
        item = DownloadItem(jid, "Waiting...", url, self)
        self.queue_layout.addWidget(item); self.items[jid] = item
        threading.Thread(target=self.run_engine, args=(url, jid, snap), daemon=True).start()

    def run_engine(self, url, jid, snap):
        try:
            target, ext, marker = snap["target"], snap["format"], f"_T_{jid}"
            is_audio = ext in AUDIO_FORMATS
            cookie_tmp = os.path.join(PROFILE_DIR, f"c_{jid}.sqlite")
            copy_cookie_db(COOKIE_PATH, cookie_tmp)
            self.signals.log.emit(jid, f"GPU: {GPU_VENDOR.upper()} Detected.")
            self.signals.status.emit(jid, "Downloading...")

            if is_audio:
                cmd = [YT_DLP, "--newline", "--no-playlist", "--cookies", cookie_tmp, "--ffmpeg-location", FFMPEG_EXE, "--force-overwrites", "-f", "bestaudio/best", "--extract-audio", "--audio-format", "vorbis" if ext == "ogg" else ext, "--audio-quality", snap["audio_q"], "-o", f"%(title)s{marker}.%(ext)s", "--paths", target, url]
            else:
                cmd = [YT_DLP, "--newline", "--no-playlist", "--cookies", cookie_tmp, "--ffmpeg-location", FFMPEG_EXE, "--force-overwrites", "-f", f"bestvideo[height<={snap['res'][:-1]}]+bestaudio/best", "--merge-output-format", "mkv", "-o", f"%(title)s{marker}.%(ext)s", "--paths", target, url]
            
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=CREATE_NO_WINDOW)
            self.items[jid].current_processes.append(p)
            for line in p.stdout:
                if self.items[jid].is_cancelled: return
                msg = line.strip()
                if msg:
                    self.signals.log.emit(jid, msg)
                    m = re.search(r'(\d+(?:\.\d+)?)%', msg)
                    if m: self.signals.progress.emit(jid, int(float(m.group(1))))
            p.wait()

            v_f, a_f, title = None, None, "Video"
            for f in os.listdir(target):
                if marker in f:
                    path = os.path.normpath(os.path.join(target, f))
                    title = f.split(marker)[0]
                    if any(x in f.lower() for x in [".mp3", ".m4a", ".wav", ".ogg"]): a_f = path
                    else: v_f = path

            if not is_audio and v_f:
                safe_v = os.path.normpath(os.path.join(target, f"in_{jid}.tmp"))
                os.rename(v_f, safe_v); v_f = safe_v
                hw_c = self.get_auto_hw_codec(snap["codec"])
                
                # --- AMD/GPU RENDER FIX ---
                scale_filter = f"scale='trunc(oh*a/2)*2':{snap['res'][:-1]}"
                self.signals.status.emit(jid, f"Rendering ({hw_c})...")
                
                out = os.path.normpath(os.path.join(target, f"Render_{jid}.{ext}"))
                r_cmd = [FFMPEG_EXE, "-y", "-hwaccel", "auto", "-i", v_f]
                if a_f: r_cmd.extend(["-i", a_f])
                
                r_cmd.extend([
                    "-vf", scale_filter, 
                    "-c:v", hw_c, 
                    "-r", snap["fps"], 
                    "-c:a", "aac", 
                    "-b:a", snap["audio_q"], 
                    out
                ])
                
                pr = subprocess.Popen(r_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, creationflags=CREATE_NO_WINDOW)
                self.items[jid].current_processes.append(pr)
                buf = ""
                while True:
                    if self.items[jid].is_cancelled: return
                    c = pr.stdout.read(1)
                    if not c and pr.poll() is not None: break
                    if c in ('\r', '\n'):
                        if buf.strip(): self.signals.log.emit(jid, buf.strip())
                        buf = ""
                    else: buf += c
                final = out
            else: final = a_f

            f_path = os.path.join(target, f"{clean_filename(title)}.{ext}")
            if final and os.path.exists(final):
                safe_remove(f_path); os.rename(final, f_path)
                self.signals.status.emit(jid, "✅ Completed"); self.signals.progress.emit(jid, 100)
            else: self.signals.status.emit(jid, "❌ Error")

            for f in os.listdir(target):
                if jid in f: safe_remove(os.path.join(target, f))
            safe_remove(cookie_tmp)
        except Exception as e:
            self.signals.log.emit(jid, f"ERR: {e}"); self.signals.status.emit(jid, "❌ Error")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("ProWeb Media Downloader")
    app.setOrganizationName("ProWeb")
    win = ProWebMediaDownloader()
    win.show()
    sys.exit(app.exec())
