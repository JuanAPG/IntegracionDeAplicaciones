package mx.udem.library.desktop;

import mx.udem.library.desktop.config.Config;
import mx.udem.library.desktop.config.Service;
import mx.udem.library.desktop.model.Author;
import mx.udem.library.desktop.model.Book;
import mx.udem.library.desktop.service.BooksService;
import mx.udem.library.desktop.service.HealthService;

/**
 * Comprobacion de la capa de red SIN levantar la interfaz grafica.
 *
 * Para que sirve: cuando algo no funciona, lo primero es saber si el
 * problema esta en la aplicacion o en el otro lado. Esto contesta esa
 * pregunta en cinco segundos y sin abrir una ventana, usando EXACTAMENTE
 * los mismos clientes que usa la aplicacion -- mismo ApiClient, mismos
 * parametros de representacion, mismo manejo de errores.
 *
 * Solo toca operaciones PUBLICAS: no necesita credenciales y no cambia
 * nada. Lo que exige token se reporta como "requiere sesion".
 *
 *     mvn -s maven-settings.xml -q compile
 *     java -cp "target/classes:$(cat target/cp.txt)" \
 *          mx.udem.library.desktop.Diagnostico
 */
public final class Diagnostico {

    public static void main(String[] args) {
        Config config = Config.cargar();
        Contexto contexto = new Contexto(config);
        HealthService salud = contexto.salud();

        System.out.println("Destinos configurados");
        for (Service servicio : Service.values()) {
            System.out.printf("  %-9s %s%n", servicio.id(), config.base(servicio));
        }

        System.out.println("\nSalud de cada destino");
        for (Service servicio : Service.values()) {
            HealthService.Resultado resultado = salud.comprobar(servicio, contexto.cliente(servicio));
            System.out.printf("  %-9s %-10s %s%n",
                    servicio.id(), resultado.estado(), resultado.detalle());
        }

        System.out.println("\nCatalogo (lectura publica, sin token)");
        try {
            BooksService.Resultado pagina = contexto.libros().listar(3, 0);
            System.out.printf("  %d libros en total; primeros %d:%n",
                    pagina.total(), pagina.libros().size());
            for (Book libro : pagina.libros()) {
                System.out.printf("    %-38s %-18s %10s  existencias %d  portada %s%n",
                        recorta(libro.title(), 38), libro.isbn(), libro.precioFormateado(),
                        libro.stock(), libro.portada().isPresent() ? "si" : "no");
            }
        } catch (RuntimeException exc) {
            System.out.println("  FALLO: " + exc.getMessage());
        }

        System.out.println("\nAutores (lectura publica, sin token)");
        try {
            for (Author autor : contexto.autores().listar(null, 3)) {
                System.out.printf("    %-32s %d obras%n", autor.name(), autor.bookCount());
            }
        } catch (RuntimeException exc) {
            System.out.println("  FALLO: " + exc.getMessage());
        }

        System.out.println("\nOperaciones que exigen sesion (no se prueban aqui):");
        System.out.println("    GET /users/<id> · POST /pedidos · GET /pedidos · "
                + "GET /metodos · POST /pagos");
        System.exit(0);
    }

    private static String recorta(String texto, int largo) {
        return texto.length() <= largo ? texto : texto.substring(0, largo - 1) + "…";
    }
}
