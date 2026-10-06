/* =====================================================================
   test/parsers.test.js
   Comprueba que los parsers del renderer leen el XML QUE DE VERDAD
   EMITEN los microservicios.

   Las muestras de test/fixtures/xml_reales.json no estan escritas a
   mano: se generaron llamando a los servicios de pedidos y pagos con su
   cliente de pruebas. Un parser que acierta con XML inventado no
   demuestra nada; este acierta con el XML real.

   Uso (desde apps/Electron-app):
       npm i -D @xmldom/xmldom
       node test/parsers.test.js
   ===================================================================== */

'use strict';

const fs = require('fs');
const path = require('path');

/* --- DOM minimo para poder correr fuera de Electron ----------------- */
let DOMParser;
try {
  ({ DOMParser } = require('@xmldom/xmldom'));
} catch {
  console.error('Falta @xmldom/xmldom. Instalalo con:  npm i -D @xmldom/xmldom');
  process.exit(2);
}
global.DOMParser = DOMParser;
global.window = { localStorage: { getItem: () => null, setItem() {}, removeItem() {} } };

/* xmldom no implementa querySelectorAll ni .children como el navegador:
   se completa lo justo que usa xml.js, sin fingir un DOM entero. */
function completarNodo(nodo) {
  if (!nodo || nodo.__completado) return nodo;
  Object.defineProperty(nodo, 'children', {
    get() {
      const salida = [];
      for (let i = 0; i < this.childNodes.length; i += 1) {
        const hijo = this.childNodes[i];
        if (hijo.nodeType === 1) salida.push(completarNodo(hijo));
      }
      return salida;
    },
    configurable: true,
  });
  nodo.querySelectorAll = function querySelectorAll() {
    const salida = [];
    const recorrer = (n) => {
      for (let i = 0; i < n.childNodes.length; i += 1) {
        const hijo = n.childNodes[i];
        if (hijo.nodeType === 1) { salida.push(completarNodo(hijo)); recorrer(hijo); }
      }
    };
    recorrer(this);
    return salida;
  };
  nodo.__completado = true;
  return nodo;
}

const parserOriginal = DOMParser.prototype.parseFromString;
DOMParser.prototype.parseFromString = function parse(...args) {
  const doc = parserOriginal.apply(this, args);
  if (doc && doc.documentElement) completarNodo(doc.documentElement);
  // xml.js comprueba doc.querySelector('parsererror'), que es como el
  // navegador reporta un XML mal formado. xmldom no lo tiene: lanza. Se
  // devuelve null, que es lo que ve el navegador cuando el XML esta bien.
  if (doc && typeof doc.querySelector !== 'function') {
    doc.querySelector = () => null;
  }
  return doc;
};

/* --- Carga de los modulos del renderer ------------------------------ */
const raiz = path.join(__dirname, '..', 'src', 'js');
// xml.js declara `const LibraryXml = (() => {...})()`. Un `const` dentro
// de eval queda en el ambito del propio eval, de modo que se anade una
// expresion final para que eval DEVUELVA el modulo.
// eslint-disable-next-line no-eval
const X = eval(`${fs.readFileSync(path.join(raiz, 'xml.js'), 'utf8')}\n;LibraryXml`);

const muestras = JSON.parse(
  fs.readFileSync(path.join(__dirname, 'fixtures', 'xml_reales.json'), 'utf8'));

let ok = 0;
let fallos = 0;
function check(nombre, condicion, extra = '') {
  if (condicion) { ok += 1; console.log(`  OK    ${nombre}`); }
  else { fallos += 1; console.log(`  FALLA ${nombre} ${extra}`); }
}

console.log('1. Rastreo publico del envio');
const envio = X.parseShipment(muestras.shipment);
check('lee el numero y el estado',
  envio.orderNumber === 'PED-000005' && envio.status === 'enviado',
  JSON.stringify(envio));
check('lee la paqueteria y la guia',
  envio.carrier === 'Estafeta' && envio.trackingCode === 'EST-123456');
check('lee las piezas como numero', envio.itemCount === 3, String(envio.itemCount));
check('una fecha ausente queda vacia, no "undefined"', envio.deliveredAt === '');
check('el XML del envio NO trae cliente ni importes ni titulos',
  !/cliente@|<user|total|subtotal|Clean Code/i.test(muestras.shipment),
  muestras.shipment.slice(0, 200));

console.log('2. Pedido con sus lineas');
const pedido = X.parseOrder(muestras.order);
check('numero, estado y moneda',
  pedido.orderNumber === 'PED-000005' && pedido.status === 'enviado'
  && pedido.currency === 'MXN', JSON.stringify(pedido).slice(0, 180));
check('importes como numero, no texto',
  pedido.total === 1050 && pedido.subtotal === 1000 && pedido.shippingCost === 50,
  `${pedido.total} ${pedido.subtotal} ${pedido.shippingCost}`);
check('lo cobrado', pedido.paidAmount === 500, String(pedido.paidAmount));
check('el dueno', pedido.user.id === 7 && pedido.user.email === 'cliente@ejemplo.mx',
  JSON.stringify(pedido.user));
check('el envio anidado',
  pedido.shipping.carrier === 'Estafeta'
  && pedido.shipping.trackingCode === 'EST-123456',
  JSON.stringify(pedido.shipping));
check('las dos lineas', pedido.lines.length === 2, String(pedido.lines.length));
check('la primera linea completa',
  pedido.lines[0].title === 'Clean Code' && pedido.lines[0].quantity === 2
  && pedido.lines[0].unitPrice === 400 && pedido.lines[0].lineTotal === 800,
  JSON.stringify(pedido.lines[0]));

console.log('3. Coleccion de pedidos');
const lista = X.parseOrders(muestras.orders);
check('un pedido en la coleccion', lista.orders.length === 1,
  String(lista.orders.length));
check('los atributos de paginacion', lista.total === 1 && lista.offset === 0,
  `total=${lista.total} offset=${lista.offset}`);
check('cada pedido de la lista se lee entero',
  lista.orders[0].orderNumber === 'PED-000005' && lista.orders[0].total === 1050,
  JSON.stringify(lista.orders[0]).slice(0, 160));

console.log('4. Pagos');
const metodos = X.parseMethods(muestras.methods);
check('dos metodos', metodos.length === 2, String(metodos.length));
check('efectivo no requiere autorizacion',
  metodos[0].name === 'efectivo' && metodos[0].requiresAuthorization === false,
  JSON.stringify(metodos[0]));
check('tarjeta si la requiere', metodos[1].requiresAuthorization === true);

const pago = X.parsePayment(muestras.payment);
check('referencia, estado e importe',
  pago.reference === 'PAG-000009' && pago.status === 'aplicado'
  && pago.amount === 500, JSON.stringify(pago).slice(0, 160));
check('el metodo y el pedido anidados',
  pago.method.name === 'tarjeta' && pago.order.number === 'PED-000005',
  JSON.stringify({ m: pago.method, o: pago.order }));

const saldo = X.parseBalance(muestras.balance);
check('saldo: total, cobrado y lo que falta',
  saldo.total === 1050 && saldo.paid === 500 && saldo.balance === 550,
  JSON.stringify(saldo));

console.log('5. Health');
const salud = X.parseHealth(muestras.health);
check('estado y bloque de Redis',
  salud.status === 'ok' && salud.redisStatus === 'ok',
  JSON.stringify(salud));

console.log('6. Un error no se confunde con un recurso');
const errorXml = '<?xml version="1.0" encoding="UTF-8"?>'
  + '<error xmlns="urn:library:orders:1.0" status="404" code="not_found">'
  + '<message>No hay ningun pedido con ese numero.</message></error>';
try {
  X.parseShipment(errorXml);
  check('parseShipment rechaza un <error>', false, 'lo acepto como envio');
} catch (e) {
  check('parseShipment rechaza un <error>', e instanceof X.XmlParseError, e.message);
}

console.log('7. El catalogo sigue funcionando (sin regresion)');
const catalogoXml = '<?xml version="1.0" encoding="UTF-8"?>'
  + '<library xmlns="urn:library:catalog:1.0" generatedAt="2026-10-06T00:00:00Z">'
  + '<books count="1" total="14" limit="6" offset="0">'
  + '<book id="1" isbn="978-1"><title>Uno</title><publicationYear>2024</publicationYear>'
  + '<price currency="MXN">499.00</price><stock>3</stock>'
  + '<format ref="1">Fisico</format><category ref="1">Tecnico</category>'
  + '<authors><author ref="1">Ada</author></authors>'
  + '<genres/><concepts/><images/></book></books></library>';
const catalogo = X.parseCatalog(catalogoXml);
check('el catalogo se sigue interpretando',
  catalogo.books.length === 1 && catalogo.total === 14
  && catalogo.books[0].title === 'Uno',
  JSON.stringify(catalogo).slice(0, 160));

console.log(`\nResultado: ${ok} OK, ${fallos} fallos`);
process.exit(fallos ? 1 : 0);
