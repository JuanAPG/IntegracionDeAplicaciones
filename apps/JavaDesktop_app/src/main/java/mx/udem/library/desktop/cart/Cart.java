package mx.udem.library.desktop.cart;

import mx.udem.library.desktop.model.Book;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

/**
 * La cesta de compras. Vive EN MEMORIA, dentro de la aplicacion.
 *
 * POR QUE EN MEMORIA Y NO EN UN SERVICIO. Porque no hay ningun
 * microservicio de cesta y no se va a inventar uno: el enunciado permite
 * mantenerla en el cliente, y una cesta es estado efimero de una sesion
 * de compra. Lo que SI es responsabilidad del servidor -- el precio, las
 * existencias, el total -- se vuelve a pedir y a calcular alli en el
 * momento de crear el pedido.
 *
 * LOS PRECIOS DE AQUI SON UNA ESTIMACION PARA ENSENAR, NO LA VERDAD. El
 * subtotal que calcula esta clase sirve para que el usuario vea cuanto
 * va a gastar; el importe real lo fija el servicio de pedidos congelando
 * el precio del catalogo. Si el precio cambio entre que el libro entro en
 * la cesta y la compra, manda el del servidor. Por eso
 * {@link #revalidar} existe: antes de confirmar, se vuelven a pedir los
 * libros y se avisa de lo que cambio.
 */
public final class Cart {

    /** Una linea de la cesta: un libro y cuantos ejemplares. */
    public record Linea(Book libro, int cantidad) {
        public double subtotal() {
            return libro.price() * cantidad;
        }
    }

    /** Lo que cambio entre que se eligio un libro y se fue a pagar. */
    public record Aviso(Book libro, String texto) { }

    private final Map<Integer, Linea> porLibro = new LinkedHashMap<>();

    /**
     * VARIOS oyentes, no uno.
     *
     * Aqui hubo un defecto que merece quedar escrito: esto era un solo
     * `Consumer` con un `setListener` que lo REEMPLAZABA. La vista de la
     * cesta registraba el suyo para repintar la tabla y, justo despues,
     * la ventana principal registraba el del contador de la pestana
     * encima. El segundo pisaba al primero, de modo que al agregar un
     * libro se actualizaba el numerito y la tabla se quedaba vacia --
     * sin ningun error, que es lo que lo hacia dificil de ver.
     *
     * Con una lista, cada interesado se apunta y todos se enteran. Es la
     * diferencia entre "el oyente" y "los oyentes", y es justo el tipo
     * de suposicion que no se nota hasta que hay dos.
     */
    private final List<Consumer<Cart>> oyentes = new ArrayList<>();

    public void addListener(Consumer<Cart> listener) {
        if (listener != null) {
            oyentes.add(listener);
        }
    }

    private void avisar() {
        // Sobre una copia: un oyente podria darse de baja al recibir el
        // aviso, y modificar la lista mientras se recorre la rompe.
        for (Consumer<Cart> oyente : List.copyOf(oyentes)) {
            oyente.accept(this);
        }
    }

    /**
     * Anade ejemplares. Si el libro ya estaba, SUMA en lugar de duplicar
     * la linea: es lo que espera quien pulsa "agregar" dos veces, y es
     * ademas lo que hace el servicio de pedidos con dos lineas del mismo
     * libro.
     *
     * El tope de 100 por libro no es un capricho de la interfaz: es el
     * limite que impone el servicio, y rebasarlo seria un 400 al final
     * del flujo en lugar de un aviso aqui.
     */
    public void agregar(Book libro, int cantidad) {
        if (libro == null || cantidad <= 0) {
            return;
        }
        Linea actual = porLibro.get(libro.id());
        int nueva = (actual == null ? 0 : actual.cantidad()) + cantidad;
        porLibro.put(libro.id(), new Linea(libro, Math.min(nueva, 100)));
        avisar();
    }

    public void establecerCantidad(int bookId, int cantidad) {
        if (cantidad <= 0) {
            porLibro.remove(bookId);
        } else {
            Linea actual = porLibro.get(bookId);
            if (actual != null) {
                porLibro.put(bookId, new Linea(actual.libro(), Math.min(cantidad, 100)));
            }
        }
        avisar();
    }

    public void quitar(int bookId) {
        porLibro.remove(bookId);
        avisar();
    }

    public void vaciar() {
        porLibro.clear();
        avisar();
    }

    public List<Linea> lineas() {
        return List.copyOf(porLibro.values());
    }

    public boolean estaVacia() {
        return porLibro.isEmpty();
    }

    public int totalEjemplares() {
        return porLibro.values().stream().mapToInt(Linea::cantidad).sum();
    }

    /** Suma de los libros, sin envio. Estimacion del cliente. */
    public double subtotal() {
        return porLibro.values().stream().mapToDouble(Linea::subtotal).sum();
    }

    public double total(double costoEnvio) {
        return subtotal() + Math.max(0, costoEnvio);
    }

    /**
     * Vuelve a comprobar precios y existencias contra el catalogo.
     *
     * Es una CORTESIA, no una autoridad: el servicio lo volvera a
     * comprobar de forma atomica al crear el pedido, y su veredicto es el
     * que vale. Esto solo evita que el usuario llegue hasta el final para
     * descubrir que un libro se agoto hace diez minutos.
     *
     * Actualiza la cesta con los datos frescos y devuelve la lista de
     * cambios que merece la pena contarle a quien compra.
     */
    public List<Aviso> revalidar(java.util.function.IntFunction<Book> buscarPorId) {
        List<Aviso> avisos = new ArrayList<>();
        for (Linea linea : List.copyOf(porLibro.values())) {
            Book fresco;
            try {
                fresco = buscarPorId.apply(linea.libro().id());
            } catch (RuntimeException exc) {
                avisos.add(new Aviso(linea.libro(),
                        "No se pudo verificar \"" + linea.libro().title() + "\": " + exc.getMessage()));
                continue;
            }
            if (fresco == null) {
                avisos.add(new Aviso(linea.libro(),
                        "\"" + linea.libro().title() + "\" ya no esta en el catalogo. Se quito de la cesta."));
                porLibro.remove(linea.libro().id());
                continue;
            }
            if (Math.abs(fresco.price() - linea.libro().price()) > 0.004) {
                avisos.add(new Aviso(fresco, String.format(
                        "\"%s\" cambio de precio: antes %s, ahora %s.",
                        fresco.title(), linea.libro().precioFormateado(), fresco.precioFormateado())));
            }
            int cantidad = linea.cantidad();
            if (fresco.stock() < cantidad) {
                avisos.add(new Aviso(fresco, String.format(
                        "De \"%s\" quedan %d y pediste %d. Se ajusto la cantidad.",
                        fresco.title(), fresco.stock(), cantidad)));
                cantidad = Math.max(0, fresco.stock());
            }
            if (cantidad == 0) {
                porLibro.remove(fresco.id());
            } else {
                porLibro.put(fresco.id(), new Linea(fresco, cantidad));
            }
        }
        avisar();
        return avisos;
    }
}
