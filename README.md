# SpeedShare MAX ⚡

A high-performance, asynchronous LAN file-sharing server built with Python and `aiohttp`. SpeedShare MAX allows you to quickly share large files (up to 10GB+) over your local network using a premium glassmorphism dark mode web interface.

## Features
- **Async Turbo Engine**: Built on `aiohttp` for non-blocking I/O and zero-copy `sendfile` downloads.
- **Streaming Uploads**: Multipart streaming ensures that uploading massive files never spikes your server's RAM.
- **Premium UI**: A slick dark-mode interface with smooth animations, built-in file search, and drag-and-drop functionality.
- **Folder Navigation**: Browse and create nested folders right from the browser.
- **Mobile Friendly**: Generates a QR code in the terminal on startup. Scan it with your phone to instantly connect.
- **Safe & Secure**: Auto-renames duplicate files and safely sanitizes filenames (including Unicode).

## Installation

1. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Start the server by running:
```bash
python fast_share.py
```

By default, the server will start on port `8888` and create a `shared_files` folder in the current directory to store uploads.

### Command Line Options

- `--port` / `-p`: Specify a custom port (default is 8888).
- `--dir` / `-d`: Specify a custom storage directory path.

Example:
```bash
python fast_share.py --port 9999 --dir "D:/my_shared_files"
```

## Technical Details
- **Backend:** Python, `aiohttp`, `aiofiles`
- **Frontend:** HTML5, Vanilla JS, CSS Glassmorphism
- **I/O Strategy:** 1MB chunked streaming for uploads, `FileResponse` zero-copy for downloads.
