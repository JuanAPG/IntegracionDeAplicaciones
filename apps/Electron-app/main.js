/* =====================================================================
   main.js — Proceso principal de Electron

   Responsabilidades
     * Crear la ventana de la aplicacion con aislamiento de contexto.
     * Actuar como unico cliente HTTP: el renderer nunca hace peticiones
       de red por su cuenta, de modo que la politica de seguridad de
       contenido (CSP) puede mantenerse estricta y no se depende del
       CORS del microservicio.
     * Devolver al renderer el XML *en crudo*. El parseo ocurre en el
       renderer con DOMParser. En ningun punto se solicita ni se
       interpreta JSON proveniente del microservicio.
   ===================================================================== */

'use strict';

const { app, BrowserWindow, ipcMain, shell, Menu } = require('electron');
const path = require('node:path');

const IS_DEV = process.argv.includes('--dev');
const REQUEST_TIMEOUT_MS = 20000;

/* ------------------------------------------------------------------ */
/* Ventana                                                             */
/* ------------------------------------------------------------------ */

let mainWindow = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 960,
    minHeight: 640,
    show: false,
    backgroundColor: '#070B16',
    title: 'Libreria en Linea',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, 'src', 'index.html'));

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    if (IS_DEV) mainWindow.webContents.openDevTools({ mode: 'detach' });
  });

  // Cualquier enlace externo se abre en el navegador del sistema, nunca
  // dentro de la aplicacion.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.webContents.on('will-navigate', (event) => event.preventDefault());

  mainWindow.on('closed', () => { mainWindow = null; });
}

/* ------------------------------------------------------------------ */
/* Cliente HTTP (XML)                                                  */
/* ------------------------------------------------------------------ */

/**
 * Descarga un documento XML y lo devuelve como texto.
 * Nunca lanza: siempre resuelve con un sobre {ok, ...} que el renderer
 * traduce a un mensaje de interfaz.
 */
async function fetchXml(_event, requestUrl) {
  let parsed;
  try {
    parsed = new URL(String(requestUrl));
  } catch {
    return { ok: false, kind: 'url', message: 'La URL configurada no es valida.' };
  }

  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    return { ok: false, kind: 'url', message: 'Solo se admiten los protocolos http y https.' };
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const startedAt = Date.now();

  try {
    const response = await fetch(parsed.toString(), {
      method: 'GET',
      // Se solicita XML de forma explicita: el microservicio responde
      // XML por omision y este encabezado lo deja por escrito.
      headers: { Accept: 'application/xml, text/xml' },
      redirect: 'follow',
      signal: controller.signal,
    });

    const body = await response.text();

    return {
      ok: response.ok,
      status: response.status,
      statusText: response.statusText,
      contentType: response.headers.get('content-type') || '',
      totalCount: response.headers.get('x-total-count'),
      elapsedMs: Date.now() - startedAt,
      url: parsed.toString(),
      body,
      message: response.ok
        ? null
        : `El servicio respondio ${response.status} ${response.statusText}.`,
      kind: response.ok ? null : 'http',
    };
  } catch (error) {
    const aborted = error && error.name === 'AbortError';
    return {
      ok: false,
      kind: aborted ? 'timeout' : 'network',
      url: parsed.toString(),
      elapsedMs: Date.now() - startedAt,
      message: aborted
        ? `Tiempo de espera agotado (${REQUEST_TIMEOUT_MS / 1000} s) al contactar el servicio.`
        : `No fue posible contactar el servicio: ${error.message}`,
    };
  } finally {
    clearTimeout(timer);
  }
}

/* ------------------------------------------------------------------ */
/* Ciclo de vida                                                       */
/* ------------------------------------------------------------------ */

app.whenReady().then(() => {
  ipcMain.handle('library:fetch-xml', fetchXml);
  ipcMain.handle('library:open-external', (_event, url) => {
    if (/^https?:\/\//i.test(String(url))) shell.openExternal(String(url));
  });

  Menu.setApplicationMenu(buildMenu());
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

function buildMenu() {
  const isMac = process.platform === 'darwin';
  const template = [
    ...(isMac ? [{ role: 'appMenu' }] : []),
    {
      label: 'Archivo',
      submenu: [
        {
          label: 'Configuracion del servicio',
          accelerator: 'CmdOrCtrl+,',
          click: () => mainWindow && mainWindow.webContents.send('library:open-settings'),
        },
        {
          label: 'Recargar catalogo',
          accelerator: 'CmdOrCtrl+R',
          click: () => mainWindow && mainWindow.webContents.send('library:reload-catalog'),
        },
        { type: 'separator' },
        isMac ? { role: 'close' } : { role: 'quit' },
      ],
    },
    { role: 'editMenu' },
    {
      label: 'Ver',
      submenu: [
        { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' },
        { type: 'separator' }, { role: 'togglefullscreen' },
        ...(IS_DEV ? [{ type: 'separator' }, { role: 'toggleDevTools' }] : []),
      ],
    },
    { role: 'windowMenu' },
  ];
  return Menu.buildFromTemplate(template);
}
