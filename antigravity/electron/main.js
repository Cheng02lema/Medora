// Clarinora — Electron 主进程
// 开发: Vite dev server + 本机 python3 后端
// 生产: 加载 frontend/dist + resources 内 Python 源码/二进制

const { app, BrowserWindow, dialog, ipcMain, Menu, shell } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const http = require("http");
const fs = require("fs");

const BACKEND_PORT = 8765;
const DEV_FRONTEND_URL = "http://localhost:5173";
const IS_DEV = !app.isPackaged;

let backendProcess = null;
let mainWindow = null;
let logStream = null;

function resourcesRoot() {
  if (IS_DEV) return path.resolve(__dirname, "..", ".."); // 数据提取/
  return process.resourcesPath;
}

function findPython() {
  return process.env.CLARINORA_PYTHON || "python3";
}

function findBackendBinary() {
  const name = process.platform === "win32" ? "clarinora-backend.exe" : "clarinora-backend";
  const candidates = [
    path.join(process.resourcesPath || "", "backend", name),
    path.join(process.resourcesPath || "", name),
    path.join(__dirname, "..", "backend-dist", name),
  ];
  for (const c of candidates) {
    if (c && fs.existsSync(c)) return c;
  }
  return null;
}

function findRunBackendScript() {
  const candidates = [
    path.join(process.resourcesPath || "", "run-backend.py"),
    path.join(__dirname, "..", "scripts", "run-backend.py"),
  ];
  for (const c of candidates) {
    if (c && fs.existsSync(c)) return c;
  }
  return null;
}

function startBackend() {
  const cwd = resourcesRoot();
  const env = {
    ...process.env,
    CLARINORA_PORT: String(BACKEND_PORT),
    PYTHONUNBUFFERED: "1",
    PYTHONPATH: cwd + path.delimiter + (process.env.PYTHONPATH || ""),
  };

  let cmd;
  let args;

  const binary = !IS_DEV ? findBackendBinary() : null;
  if (binary) {
    cmd = binary;
    args = ["--port", String(BACKEND_PORT)];
  } else {
    cmd = findPython();
    const script = findRunBackendScript();
    if (script) {
      args = [script, "--port", String(BACKEND_PORT)];
    } else {
      // 开发回退：直接 uvicorn 模块
      args = [
        "-m",
        "uvicorn",
        "antigravity.backend.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        String(BACKEND_PORT),
      ];
    }
  }

  backendProcess = spawn(cmd, args, {
    cwd,
    env,
    stdio: IS_DEV ? "inherit" : ["ignore", "pipe", "pipe"],
  });

  if (!IS_DEV) {
    try {
      const logFile = path.join(app.getPath("userData"), "backend.log");
      logStream = fs.createWriteStream(logFile, { flags: "a" });
      backendProcess.stdout?.pipe(logStream);
      backendProcess.stderr?.pipe(logStream);
    } catch (_) {}
  }

  backendProcess.on("error", (err) => {
    console.error("[backend] 启动失败:", err.message);
  });

  backendProcess.on("exit", (code) => {
    console.log(`[backend] 退出 code=${code}`);
  });
}

function waitForBackend(retriesLeft = 80) {
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const req = http.get(`http://127.0.0.1:${BACKEND_PORT}/health`, (res) => {
        if (res.statusCode === 200) resolve();
        else if (retriesLeft > 0) setTimeout(() => waitForBackend(retriesLeft - 1).then(resolve, reject), 250);
        else reject(new Error("后端启动超时"));
      });
      req.on("error", () => {
        if (retriesLeft > 0) setTimeout(() => waitForBackend(retriesLeft - 1).then(resolve, reject), 250);
        else reject(new Error("后端启动超时"));
      });
    };
    attempt();
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1380,
    height: 880,
    minWidth: 1024,
    minHeight: 640,
    backgroundColor: "#0d0d0f",
    titleBarStyle: "hiddenInset",
    trafficLightPosition: { x: 16, y: 14 },
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (IS_DEV) {
    mainWindow.loadURL(DEV_FRONTEND_URL);
  } else {
    mainWindow.loadFile(path.join(__dirname, "..", "frontend", "dist", "index.html"));
  }

  mainWindow.once("ready-to-show", () => mainWindow.show());

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
}

function killBackend() {
  if (!backendProcess) return;
  try {
    backendProcess.kill();
  } catch (_) {}
  backendProcess = null;
  try {
    logStream?.end();
  } catch (_) {}
  logStream = null;
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    if (process.platform === "darwin") {
      Menu.setApplicationMenu(
        Menu.buildFromTemplate([
          {
            role: "appMenu",
            submenu: [
              { role: "about", label: "关于 Clarinora" },
              { type: "separator" },
              { role: "quit", label: "退出 Clarinora" },
            ],
          },
          { role: "editMenu" },
          { role: "windowMenu" },
        ])
      );
    } else {
      Menu.setApplicationMenu(null);
    }

    startBackend();
    try {
      await waitForBackend();
    } catch (err) {
      dialog.showErrorBox(
        "后端启动失败",
        `${err.message}\n\n请确认已安装 Python3 及依赖：\npip install -r requirements.txt`
      );
    }
    createWindow();

    app.on("activate", () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
  });
}

app.on("window-all-closed", () => {
  killBackend();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  killBackend();
});

// ─── 文件对话框 IPC ───
ipcMain.handle("dialog:selectFolder", async () => {
  if (!mainWindow) return "";
  const result = await dialog.showOpenDialog(mainWindow, { properties: ["openDirectory"] });
  return result.filePaths[0] || "";
});

ipcMain.handle("dialog:selectFile", async (_event, filters) => {
  if (!mainWindow) return "";
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ["openFile"],
    filters: filters || [{ name: "所有文件", extensions: ["*"] }],
  });
  return result.filePaths[0] || "";
});

ipcMain.handle("dialog:selectSaveFile", async (_event, filters) => {
  if (!mainWindow) return "";
  const result = await dialog.showSaveDialog(mainWindow, {
    filters: filters || [{ name: "Excel", extensions: ["xlsx"] }],
  });
  return result.filePath || "";
});
