// Prueba HTTP local con Nginx y upstreams simulados; no conecta a la VM.
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const assert = require('assert');
const root = path.resolve(__dirname, '../../apps/Electron-app/src/js');
const store = new Map();
global.window = { localStorage: { getItem: k => store.get(k) || null, setItem: (k,v) => store.set(k,v), removeItem: k => store.delete(k) },
  libraryBridge: { request: async options => {
    const r = await fetch(options.url, { method: options.method || 'GET', headers: options.body ? {'Content-Type':'application/json'} : {}, body: options.body ? JSON.stringify(options.body) : undefined });
    return { ok: r.ok, status: r.status, body: await r.text() };
  } } };
global.LibraryXml = { parseBalance: JSON.parse, parseShipment: JSON.parse, parseMethods: JSON.parse };
for (const f of ['config.js', 'auth.js', 'services.js']) vm.runInThisContext(fs.readFileSync(path.join(root, f), 'utf8'), { filename: f });
(async () => {
  const config = { baseUrl: 'http://127.0.0.1:18081/api/books', endpoint: '/books' };
  assert.equal(LibraryConfig.buildUrl(config), 'http://127.0.0.1:18081/api/books');
  assert.equal(LibraryConfig.requestUrl(LibraryConfig.serviceUrl(config, 'login'), '/login?format=json'), 'http://127.0.0.1:18081/api/login?format=json');
  console.log('Electron: catálogo y login -> rutas públicas correctas');
  for (const [label, result, port, uri] of [
    ['envíos', await LibraryServices.trackShipment(config, 'ABC'), 5004, '/envios/ABC'],
    ['métodos', await LibraryServices.paymentMethods(config), 5005, '/metodos'],
    ['saldo', await LibraryServices.orderBalance(config, 15), 5005, '/pedidos/15/saldo'],
  ]) {
    assert(result.ok, JSON.stringify(result));
    assert.equal(result.data.port, port); assert.equal(result.data.uri, uri);
    console.log(`Electron: ${label} -> :${port}${uri} OK`);
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
