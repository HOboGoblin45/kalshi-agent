const { app, BrowserWindow, shell, Menu, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

const DASHBOARD_URL = process.env.KALSHI_DASHBOARD_URL || 'http://127.0.0.1:9000';
let mainWindow = null;
let backendProc = null;

function loadFallbackPage() {
  if (!mainWindow) return;
  const fallbackHtml = `<!doctype html>
<html>
<head>
  <meta charset="UTF-8" />
  <title>Kalshi Agent Desktop</title>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet" />
  <style>
    body { margin:0; background:#0a0a0a; color:#33ff00; font-family:"JetBrains Mono",monospace; display:flex; align-items:center; justify-content:center; height:100vh; }
    .card { width: min(560px, 92vw); border:1px solid #1f521f; padding:18px; }
    h1 { margin:0 0 10px; font-size:14px; text-transform:uppercase; letter-spacing:2px; text-shadow:0 0 5px rgba(51,255,0,0.5); }
    p { margin:0 0 8px; font-size:11px; color:#88cc44; }
    code { color:#ffb000; }
    .blink { animation: blink 1s step-end infinite; }
    @keyframes blink { 50% { opacity:0; } }
    .err { color:#ff3333; font-weight:bold; }
  </style>
</head>
<body>
  <div class="card">
    <h1>[ERR] DASHBOARD UNAVAILABLE</h1>
    <p>the desktop shell is running but the backend is not reachable.</p>
    <p>attempting to auto-start backend...</p>
    <p>target: <code>${DASHBOARD_URL}</code></p>
    <p style="margin-top:12px;color:#1f521f">$ python kalshi-agent.py --config kalshi-config.json</p>
    <p><span class="blink">_</span></p>
  </div>
</body>
</html>`;
  mainWindow.loadURL(`data:text/html;charset=UTF-8,${encodeURIComponent(fallbackHtml)}`);
}

function pingDashboard() {
  return new Promise((resolve) => {
    const req = http.get(`${DASHBOARD_URL}/api/state`, { timeout: 1200 }, (res) => {
      resolve(res.statusCode === 200);
      res.resume();
    });
    req.on('error', () => resolve(false));
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function ensureBackendRunning() {
  const healthy = await pingDashboard();
  if (healthy) return true;

  const cwd = path.resolve(__dirname, '..');
  const cfg = path.join(cwd, 'kalshi-config.json');
  const fs = require('fs');
  const logPath = path.join(cwd, 'electron-backend.log');
  const logFd = fs.openSync(logPath, 'w');

  const args = ['kalshi-agent.py', '--config', cfg, '--live'];
  backendProc = spawn('python', args, {
    cwd,
    windowsHide: true,
    stdio: ['ignore', logFd, logFd],
  });

  let agentExited = false;
  backendProc.on('exit', (code) => {
    agentExited = true;
    backendProc = null;
    try { fs.writeSync(logFd, `\n[electron] agent exited with code ${code}\n`); } catch (_) {}
  });

  // Wait up to 10s for the real agent
  for (let i = 0; i < 20; i += 1) {
    const ok = await pingDashboard();
    if (ok) { try { fs.closeSync(logFd); } catch (_) {} return true; }
    if (agentExited) break;
    await new Promise((r) => setTimeout(r, 500));
  }

  // If real agent failed, try the mock server as fallback
  if (!await pingDashboard()) {
    try { fs.writeSync(logFd, '\n[electron] real agent failed, trying mock server...\n'); } catch (_) {}
    stopBackend();
    const mockScript = path.join(cwd, 'scripts', 'mock_dashboard_server.py');
    const mockArgs = [mockScript, '--port', '9000'];
    backendProc = spawn('python', mockArgs, {
      cwd,
      windowsHide: true,
      stdio: ['ignore', logFd, logFd],
    });
    backendProc.on('exit', () => { backendProc = null; });

    for (let i = 0; i < 20; i += 1) {
      const ok = await pingDashboard();
      if (ok) { try { fs.closeSync(logFd); } catch (_) {} return true; }
      await new Promise((r) => setTimeout(r, 500));
    }
  }

  try { fs.closeSync(logFd); } catch (_) {}
  return false;
}

function stopBackend() {
  if (backendProc && !backendProc.killed) {
    try {
      backendProc.kill();
    } catch (_) {
      // ignore
    }
  }
}

function createMenu() {
  const template = [
    {
      label: 'File',
      submenu: [
        {
          label: 'Restart Local Backend',
          click: async () => {
            stopBackend();
            await ensureBackendRunning();
            if (mainWindow) mainWindow.loadURL(DASHBOARD_URL);
          },
        },
        {
          label: 'Open Dashboard in Browser',
          click: () => shell.openExternal(DASHBOARD_URL),
        },
        { type: 'separator' },
        { role: 'quit' },
      ],
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
      ],
    },
    {
      label: 'Help',
      submenu: [
        {
          label: 'Troubleshooting',
          click: () => {
            const message = [
              'If the app cannot connect:',
              '',
              '1. Start backend: python kalshi-agent.py --config kalshi-config.json',
              '2. Confirm dashboard at http://127.0.0.1:9000',
              '3. Re-open this desktop app',
            ].join('\n');
            dialog.showMessageBox({ type: 'info', title: 'Troubleshooting', message });
          },
        },
      ],
    },
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1360,
    height: 860,
    minWidth: 1024,
    minHeight: 700,
    show: false,
    autoHideMenuBar: false,
    backgroundColor: '#000000',
    title: 'Kalshi Agent Desktop',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      devTools: true,
    },
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.webContents.on('did-fail-load', () => {
    loadFallbackPage();
  });

  ensureBackendRunning().then((ok) => {
    if (ok) mainWindow.loadURL(DASHBOARD_URL);
    else loadFallbackPage();
  });
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(() => {
    createMenu();
    createWindow();

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
  });
}

app.on('window-all-closed', () => {
  stopBackend();
  if (process.platform !== 'darwin') app.quit();
});
