import os
import sys
import socket
import json
import asyncio
import argparse
import mimetypes
import hashlib
from pathlib import Path
from datetime import datetime

import aiohttp
from aiohttp import web
import aiofiles
import qrcode

# ==========================================
# ⚡ CONFIGURATION
# ==========================================
DEFAULT_STORAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shared_files')
DEFAULT_PORT = 8888
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for streaming
MAX_FILE_SIZE = 10 * 1024 * 1024 * 1024  # 10GB

# ==========================================
# 🛠️ UTILITIES
# ==========================================
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        return s.getsockname()[0]
    except Exception:
        return '127.0.0.1'
    finally:
        s.close()

def format_size(size_bytes):
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / (1024**3):.1f} GB"
    elif size_bytes >= 1024 ** 2:
        return f"{size_bytes / (1024**2):.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"

def get_file_icon(filename):
    ext = Path(filename).suffix.lower()
    icons = {
        '.pdf': '📄', '.doc': '📝', '.docx': '📝', '.txt': '📝', '.rtf': '📝',
        '.xls': '📊', '.xlsx': '📊', '.csv': '📊',
        '.ppt': '📽️', '.pptx': '📽️',
        '.jpg': '🖼️', '.jpeg': '🖼️', '.png': '🖼️', '.gif': '🖼️',
        '.svg': '🖼️', '.webp': '🖼️', '.bmp': '🖼️', '.ico': '🖼️',
        '.mp4': '🎬', '.mkv': '🎬', '.avi': '🎬', '.mov': '🎬', '.wmv': '🎬', '.webm': '🎬',
        '.mp3': '🎵', '.wav': '🎵', '.flac': '🎵', '.aac': '🎵', '.ogg': '🎵',
        '.zip': '📦', '.rar': '📦', '.7z': '📦', '.tar': '📦', '.gz': '📦',
        '.exe': '⚙️', '.msi': '⚙️', '.dmg': '⚙️',
        '.py': '🐍', '.js': '🟨', '.html': '🌐', '.css': '🎨',
        '.json': '📋', '.xml': '📋', '.yaml': '📋', '.yml': '📋',
        '.iso': '💿', '.img': '💿',
    }
    return icons.get(ext, '📎')

def safe_filename(filename):
    """Sanitize filename while preserving unicode characters."""
    if not filename:
        return 'unnamed_file'
    # Remove path separators and null bytes
    filename = filename.replace('/', '_').replace('\\', '_').replace('\x00', '')
    # Remove leading dots/spaces for security
    filename = filename.lstrip('. ')
    # Fallback if empty after sanitization
    return filename if filename else 'unnamed_file'

def unique_filepath(directory, filename):
    """Generate a unique file path, appending (1), (2), etc. for duplicates."""
    filepath = os.path.join(directory, filename)
    if not os.path.exists(filepath):
        return filepath
    name, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(filepath):
        filepath = os.path.join(directory, f"{name} ({counter}){ext}")
        counter += 1
    return filepath

def scan_files(directory, subpath=''):
    """Efficiently scan directory using os.scandir()."""
    target = os.path.join(directory, subpath) if subpath else directory
    items = []
    if not os.path.exists(target):
        return items
    try:
        with os.scandir(target) as entries:
            for entry in entries:
                try:
                    stat = entry.stat()
                    items.append({
                        'name': entry.name,
                        'is_dir': entry.is_dir(),
                        'size': format_size(stat.st_size) if entry.is_file() else '--',
                        'size_bytes': stat.st_size if entry.is_file() else 0,
                        'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%b %d, %H:%M'),
                        'icon': '📁' if entry.is_dir() else get_file_icon(entry.name),
                    })
                except (PermissionError, OSError):
                    continue
    except (PermissionError, OSError):
        pass
    # Sort: folders first, then by modified time descending
    items.sort(key=lambda x: (not x['is_dir'], -x.get('size_bytes', 0)))
    return items

# ==========================================
# 🌐 ROUTE HANDLERS
# ==========================================
async def index_handler(request):
    return web.Response(text=HTML_TEMPLATE, content_type='text/html')

async def api_files_handler(request):
    """JSON API for file listing — supports subfolder browsing."""
    storage = request.app['storage_dir']
    subpath = request.query.get('path', '')
    # Prevent directory traversal
    resolved = os.path.realpath(os.path.join(storage, subpath))
    if not resolved.startswith(os.path.realpath(storage)):
        return web.json_response({'error': 'Access denied'}, status=403)
    files = scan_files(storage, subpath)
    return web.json_response({'files': files, 'path': subpath})

async def upload_handler(request):
    """Stream multipart upload — never loads entire file into RAM."""
    storage = request.app['storage_dir']
    subpath = ''
    uploaded = []
    try:
        reader = await request.multipart()
        async for part in reader:
            if part.name == 'path':
                subpath = (await part.text()).strip('/')
            elif part.name == 'files':
                filename = safe_filename(part.filename)
                if not filename:
                    continue
                target_dir = os.path.join(storage, subpath) if subpath else storage
                # Prevent directory traversal
                resolved = os.path.realpath(target_dir)
                if not resolved.startswith(os.path.realpath(storage)):
                    return web.json_response({'error': 'Access denied'}, status=403)
                os.makedirs(target_dir, exist_ok=True)
                filepath = unique_filepath(target_dir, filename)
                size = 0
                async with aiofiles.open(filepath, 'wb') as f:
                    while True:
                        chunk = await part.read_chunk(CHUNK_SIZE)
                        if not chunk:
                            break
                        await f.write(chunk)
                        size += len(chunk)
                uploaded.append({'name': os.path.basename(filepath), 'size': format_size(size)})
        if not uploaded:
            return web.json_response({'error': 'No files received'}, status=400)
        return web.json_response({'status': 'ok', 'files': uploaded})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

async def download_handler(request):
    """Optimized download using FileResponse (sendfile)."""
    storage = request.app['storage_dir']
    filename = request.match_info['filename']
    filepath = os.path.join(storage, filename)
    # Prevent directory traversal
    resolved = os.path.realpath(filepath)
    if not resolved.startswith(os.path.realpath(storage)):
        return web.json_response({'error': 'Access denied'}, status=403)
    if not os.path.isfile(filepath):
        return web.json_response({'error': 'File not found'}, status=404)
    return web.FileResponse(
        filepath,
        headers={'Content-Disposition': f'attachment; filename="{os.path.basename(filepath)}"'}
    )

async def delete_handler(request):
    """Delete a file with safety checks."""
    storage = request.app['storage_dir']
    data = await request.json()
    filename = data.get('filename', '')
    subpath = data.get('path', '')
    filepath = os.path.join(storage, subpath, filename) if subpath else os.path.join(storage, filename)
    resolved = os.path.realpath(filepath)
    if not resolved.startswith(os.path.realpath(storage)):
        return web.json_response({'error': 'Access denied'}, status=403)
    if not os.path.exists(filepath):
        return web.json_response({'error': 'File not found'}, status=404)
    try:
        if os.path.isdir(filepath):
            import shutil
            shutil.rmtree(filepath)
        else:
            os.remove(filepath)
        return web.json_response({'status': 'ok'})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

async def mkdir_handler(request):
    """Create a new subdirectory."""
    storage = request.app['storage_dir']
    data = await request.json()
    dirname = safe_filename(data.get('name', ''))
    subpath = data.get('path', '')
    target = os.path.join(storage, subpath, dirname) if subpath else os.path.join(storage, dirname)
    resolved = os.path.realpath(target)
    if not resolved.startswith(os.path.realpath(storage)):
        return web.json_response({'error': 'Access denied'}, status=403)
    try:
        os.makedirs(target, exist_ok=True)
        return web.json_response({'status': 'ok'})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

# ==========================================
# 📄 HTML TEMPLATE (loaded from file)
# ==========================================
_template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'template.html')
with open(_template_path, 'r', encoding='utf-8') as _f:
    HTML_TEMPLATE = _f.read()

# ==========================================
# 🚀 SERVER STARTUP
# ==========================================
def print_banner(ip, port, storage):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    print("\n" + "=" * 48)
    print("  SPEEDSHARE MAX")
    print("  Async Turbo Engine v2.0")
    print("=" * 48)
    print(f"  URL:     http://{ip}:{port}")
    print(f"  Storage: {storage}")
    print("-" * 48)
    print("  [+] aiohttp async engine")
    print("  [+] Zero-copy sendfile downloads")
    print("  [+] Streaming multipart uploads")
    print("  [+] 1MB chunked I/O")
    print("=" * 48)
    # QR Code
    try:
        import io
        qr = qrcode.QRCode(version=1, box_size=1, border=1)
        qr.add_data(f"http://{ip}:{port}")
        qr.make(fit=True)
        buf = io.StringIO()
        qr.print_ascii(out=buf, invert=True)
        print("\n  Scan to connect:\n")
        print(buf.getvalue())
    except Exception:
        pass
    print()

def main():
    parser = argparse.ArgumentParser(description='SpeedShare MAX — Turbo LAN File Sharing')
    parser.add_argument('--dir', '-d', default=DEFAULT_STORAGE, help='Storage directory path')
    parser.add_argument('--port', '-p', type=int, default=DEFAULT_PORT, help='Server port')
    args = parser.parse_args()

    storage = os.path.abspath(args.dir)
    os.makedirs(storage, exist_ok=True)

    app = web.Application(client_max_size=MAX_FILE_SIZE)
    app['storage_dir'] = storage

    app.router.add_get('/', index_handler)
    app.router.add_get('/api/files', api_files_handler)
    app.router.add_post('/api/upload', upload_handler)
    app.router.add_post('/api/delete', delete_handler)
    app.router.add_post('/api/mkdir', mkdir_handler)
    app.router.add_get('/download/{filename:.+}', download_handler)

    ip = get_local_ip()
    print_banner(ip, args.port, storage)
    web.run_app(app, host='0.0.0.0', port=args.port, print=None)

if __name__ == '__main__':
    main()
