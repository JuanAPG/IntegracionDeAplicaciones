/* =====================================================================
   preload.js — Puente seguro entre el proceso principal y el renderer.

   Se expone la superficie minima indispensable: descargar XML y abrir
   un enlace en el navegador del sistema. El renderer no recibe acceso
   a Node, al sistema de archivos ni al modulo de red.
   ===================================================================== */

'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('libraryBridge', {
  /** Descarga un documento XML y lo devuelve como texto sin interpretar. */
  fetchXml: (url) => ipcRenderer.invoke('library:fetch-xml', url),

  /** Abre una URL en el navegador predeterminado del sistema. */
  openExternal: (url) => ipcRenderer.invoke('library:open-external', url),

  /** Acciones disparadas desde el menu de la aplicacion. */
  onOpenSettings: (handler) => ipcRenderer.on('library:open-settings', () => handler()),
  onReloadCatalog: (handler) => ipcRenderer.on('library:reload-catalog', () => handler()),

  platform: process.platform,
  versions: {
    electron: process.versions.electron,
    chrome: process.versions.chrome,
    node: process.versions.node,
  },
});
