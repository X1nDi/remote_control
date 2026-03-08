from __future__ import annotations

import platform
import socket
import subprocess
import time
import threading
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path

import psutil
from PIL import ImageGrab

try:
    from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
    from winsdk.windows.storage.streams import DataReader, Buffer
except ImportError:
    GlobalSystemMediaTransportControlsSessionManager = None

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


def format_uptime(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    parts = []
    if d > 0: parts.append(f'{d}d')
    if h > 0: parts.append(f'{h}h')
    if m > 0: parts.append(f'{m}m')
    if not parts or s > 0: parts.append(f'{s}s')
    return ' '.join(parts)


def capture_screenshot_bytes() -> tuple[bytes, str]:
    img = ImageGrab.grab(all_screens=True)
    output = BytesIO()
    img.save(output, format='JPEG', quality=85)
    now = datetime.now().strftime('%Y%m%d_%H%M%S')
    return output.getvalue(), f'screen_{now}.jpg'


def capture_webcam_photo() -> tuple[bytes, str]:
    import cv2
    with media_lock:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            raise RuntimeError('Не удалось открыть веб-камеру.')
        try:
            for _ in range(5):
                cap.read()
                time.sleep(0.1)
            ret, frame = cap.read()
            if not ret:
                raise RuntimeError('Не удалось сделать снимок.')
            success, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            if not success:
                raise RuntimeError('Не удалось закодировать изображение.')
            now = datetime.now().strftime('%Y%m%d_%H%M%S')
            return buffer.tobytes(), f'webcam_{now}.jpg'
        finally:
            cap.release()


def capture_webcam_video(duration_seconds: int = 5) -> tuple[bytes, str]:
    import cv2
    with media_lock:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            raise RuntimeError('Не удалось открыть веб-камеру.')
        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = 20.0
        temp_file = Path('temp_video.mp4')
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(str(temp_file), fourcc, fps, (frame_width, frame_height))
        try:
            start_time = time.time()
            while int(time.time() - start_time) < duration_seconds:
                ret, frame = cap.read()
                if ret:
                    out.write(frame)
                else:
                    break
        finally:
            cap.release()
            out.release()
        if not temp_file.exists():
            raise RuntimeError('Ошибка сохранения видео.')
        video_bytes = temp_file.read_bytes()
        temp_file.unlink()
        now = datetime.now().strftime('%Y%m%d_%H%M%S')
        return video_bytes, f'webcam_{now}.mp4'


def record_audio(duration_seconds: int = 5) -> tuple[bytes, str]:
    import pyaudio
    import wave
    with media_lock:
        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
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


def get_hardware_info() -> str:
    lines = []

    # Собираем данные о самых прожорливых процессах
    procs = []
    for p in psutil.process_iter(['name', 'memory_info']):
        try:
            p.cpu_percent(interval=None)  # Инициируем замер CPU
            procs.append(p)
        except:
            pass

    time.sleep(0.15)  # Ждем долю секунды для точности замера ЦПУ

    top_cpu_name, top_cpu_val = "Нет данных", 0.0
    top_ram_name, top_ram_val = "Нет данных", 0.0

    for p in procs:
        try:
            c = p.cpu_percent(interval=None)
            if c > top_cpu_val:
                top_cpu_val = c
                top_cpu_name = p.info['name']

            m = p.info['memory_info'].rss if p.info['memory_info'] else 0
            if m > top_ram_val:
                top_ram_val = m
                top_ram_name = p.info['name']
        except:
            pass

    # === CPU Info ===
    try:
        import wmi
        w = wmi.WMI()
        cpu = w.Win32_Processor()[0]
        lines.append(f"🧠 <b>CPU:</b> {cpu.Name}")
        lines.append(f"⏱ <b>Частота:</b> {cpu.CurrentClockSpeed} MHz / {cpu.MaxClockSpeed} MHz")
        lines.append(f"📈 <b>Загрузка CPU:</b> {cpu.LoadPercentage}%")
        lines.append(f"🧮 <b>Ядра:</b> {cpu.NumberOfCores} физ / {cpu.NumberOfLogicalProcessors} лог")
    except Exception:
        lines.append(f"🧠 <b>CPU:</b> {platform.processor()}")
        lines.append(f"📈 <b>Загрузка CPU:</b> {psutil.cpu_percent()}%")

    # Температура CPU (WMI)
    try:
        import wmi
        w_wmi = wmi.WMI(namespace="root\\wmi")
        temps = w_wmi.MSAcpi_ThermalZoneTemperature()
        if temps:
            t_c = (temps[0].CurrentTemperature / 10.0) - 273.15
            lines.append(f"🌡 <b>Температура CPU:</b> {t_c:.1f} °C")
        else:
            lines.append(f"🌡 <b>Температура CPU:</b> Данные недоступны")
    except Exception:
        lines.append(f"🌡 <b>Температура CPU:</b> (Нужны права админа или спец. драйвер)")

    lines.append(f"🔥 <b>Топ процесс CPU:</b> {top_cpu_name} ({top_cpu_val:.1f}%)")
    lines.append("")

    # === GPU Info ===
    top_gpu_name = "Нет данных"
    try:
        out_apps = subprocess.check_output(
            ['nvidia-smi', '--query-compute-apps=name,used_memory', '--format=csv,noheader'],
            encoding='utf-8', timeout=3
        ).strip().split('\n')

        max_gpu_mem = -1
        for app in out_apps:
            parts = [x.strip() for x in app.split(',')]
            if len(parts) == 2:
                name = parts[0]
                mem_str = parts[1].replace(' MiB', '').strip()
                if mem_str.isdigit():
                    mem = int(mem_str)
                    if mem > max_gpu_mem:
                        max_gpu_mem = mem
                        top_gpu_name = f"{name} ({mem} MB)"
    except:
        pass

    try:
        out = subprocess.check_output(
            ['nvidia-smi', '--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total',
             '--format=csv,noheader'],
            encoding='utf-8',
            timeout=3
        )
        for i, gpu in enumerate(out.strip().split('\n')):
            parts = [p.strip() for p in gpu.split(',')]
            if len(parts) >= 5:
                lines.append(f"🎮 <b>GPU {i}:</b> {parts[0]}")
                lines.append(f"🌡 <b>Температура:</b> {parts[1]} °C")
                lines.append(f"📊 <b>Нагрузка GPU:</b> {parts[2]}")  # Убрали лишний знак %
                lines.append(f"💾 <b>Видеопамять:</b> {parts[3]} / {parts[4]}")
                lines.append(f"🔥 <b>Топ процесс GPU:</b> {top_gpu_name}")
                lines.append("")
    except Exception:
        lines.append("🎮 <b>GPU:</b> Данные недоступны (NVIDIA драйвер не найден)")
        lines.append("")

    # === RAM Info ===
    ram = psutil.virtual_memory()
    lines.append(f"💽 <b>ОЗУ (RAM):</b> {ram.percent}%")
    lines.append(f"├ Использовано: {ram.used // (1024 ** 3)} GB")
    lines.append(f"└ Всего: {ram.total // (1024 ** 3)} GB")
    lines.append(f"🔥 <b>Топ процесс ОЗУ:</b> {top_ram_name} ({top_ram_val / (1024 * 1024):.1f} MB)")
    lines.append("")

    # === Disk Info ===
    lines.append("💾 <b>Диски системы:</b>")
    for p in psutil.disk_partitions():
        if 'cdrom' in p.opts or p.fstype == '':
            continue
        try:
            usage = psutil.disk_usage(p.mountpoint)
            lines.append(f"💿 <b>{p.mountpoint}</b> ({p.fstype}) — {usage.percent}%")
            lines.append(f"   ├ Занято: {usage.used // (1024 ** 3)} GB")
            lines.append(f"   └ Свободно: {usage.free // (1024 ** 3)} GB")
        except Exception:
            pass

    return '\n'.join(lines)


async def get_now_playing() -> tuple[str, bytes | None]:
    if GlobalSystemMediaTransportControlsSessionManager is None:
        return "❌ Библиотека winsdk не установлена или не поддерживается на вашей ОС.", None
    try:
        manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
        session = manager.get_current_session()
        if not session:
            return "🔇 Сейчас ничего не играет (или плеер не передает данные).", None
        info = await session.try_get_media_properties_async()
        title = info.title or "Неизвестный трек"
        artist = info.artist or "Неизвестный исполнитель"
        text = f"🎵 <b>Сейчас играет:</b>\n👤 <b>Исполнитель:</b> <code>{artist}</code>\n🎧 <b>Трек:</b> <code>{title}</code>"
        thumb_bytes = None
        if info.thumbnail:
            try:
                stream = await info.thumbnail.open_read_async()
                buffer = Buffer(stream.size)
                await stream.read_async(buffer, buffer.capacity, 0)
                reader = DataReader.from_buffer(buffer)
                thumb_bytes = bytearray(reader.read_bytes(buffer.length))
            except Exception:
                pass
        return text, thumb_bytes
    except Exception as e:
        return f"❌ Ошибка получения медиа: {e}", None


def _disk_root() -> Path:
    home = Path.home()
    drive = home.drive
    if drive: return Path(f'{drive}\\')
    return Path('/')


def _public_ip() -> str:
    try:
        req = urllib.request.Request('https://api.ipify.org', headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.read().decode('utf8').strip()
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return 'Unknown'