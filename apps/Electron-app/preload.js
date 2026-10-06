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

  /**
   * Peticion generica contra los microservicios, con token opcional.
   *
   *   request({ url, method, token, body, accept })
   *
   * El renderer sigue sin tocar la red: solo describe la peticion y el
   * proceso principal la ejecuta. 'accept' admite 'xml' (por omision) o
   * 'json', que se usa unicamente en /login y /refresh porque el XML de
   * esos endpoints NO publica los tokens a proposito.
   */
  request: (options) => ipcRenderer.invoke('library:api-request', options),

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
