ProWeb Media Downloader
I built this because most media downloaders out there are either buried in ads or incredibly slow. This is a no-nonsense, high-performance GUI wrapper for yt-dlp and FFmpeg that runs entirely on your local machine. No tracking, no middle-man, just the raw power of Python and PyQt6.

Why I built this (Features)
Native GPU Support
I hate waiting for renders. The app automatically sniffs out your hardware (NVIDIA, AMD, or Intel) and forces FFmpeg to use your GPU (nvenc, amf, or qsv). It is significantly faster than standard CPU encoding.

Built-in Browser (With a brain)
Instead of copying and pasting links, you can browse directly in the app. It handles cookies properly (ForcePersistentCookies), so if you are logged into a site or need to bypass an age-gate, it just works without extra steps.

Total Control
You get to pick exactly what you want—up to 4K, 60 FPS, and specific bitrates (up to 320kbps for audio).

Smart Validation
I added logic to stop you from picking incompatible settings, like trying to shove H.265 into an old .avi container. This prevents those annoying "Error 1" crashes halfway through a long download.

Real-time Logs
If something goes wrong, you do not have to guess. Every download has its own live terminal window so you can see exactly what yt-dlp is doing under the hood.

Getting Started
You will need Python 3.x and two main binaries to make this fly.

1. Install the Python dependencies:

Bash
pip install PyQt6 PyQt6-WebEngine
2. The Engine:
The app looks for yt-dlp.exe and ffmpeg.exe in:

C:\Program Files\ProWeb Media Downloader

(If you want to move them, just tweak the # CONFIG section at the top of the script).

3. Fire it up:

Bash
python proweb_downloader.py
What it looks like
(Drop a screenshot of that clean dark-mode UI here)

The "Don't be a jerk" Clause (Legal)
This is a tool, not a piracy service. Use it for lawful stuff—backups of your own content, grabbing royalty-free clips, or material you have explicit permission to download. Since this runs 100% locally on your PC, you are the one in the driver's seat. I do not host the files, I do not track what you do, and I do not condone piracy. Be smart.

License
Released under the MIT License. Go nuts.
