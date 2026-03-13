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
  <style>
    body { margin:0; background:#000; color:#fff; font-family:Segoe UI,Arial,sans-serif; display:flex; align-items:center; justify-content:center; height:100vh; }
    .card { width: min(560px, 92vw); background:#1c1c1e; border:1px solid rgba(255,255,255,.1); border-radius:12px; padding:18px; }
    h1 { margin:0 0 10px; font-size:18px; }
    p { margin:0 0 10px; font-size:13px; color:rgba(235,235,245,.8); }
    code { background:#2c2c2e; padding:2px 6px; border-radius:6px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Kalshi Dashboard Unavailable</h1>
    <p>The desktop shell is running but the backend dashboard is not reachable.</p>
    <p>The app will attempt to auto-start local backend in dry-run mode.</p>
    <p>Expected URL: <code>${DASHBOARD_URL}</code></p>
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
  const args = ['kalshi-agent.py', '--config', cfg, '--dry-run'];
  backendProc = spawn('python', args, {
    cwd,
    windowsHide: true,
    stdio: 'ignore',
  });
  backendProc.on('exit', () => {
    backendProc = null;
  });

  for (let i = 0; i < 30; i += 1) {
    const ok = await pingDashboard();
    if (ok) return true;
    await new Promise((r) => setTimeout(r, 500));
  }
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
              '1. Start backend: python kalshi-agent.py --config kalshi-config.json --dry-run',
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
