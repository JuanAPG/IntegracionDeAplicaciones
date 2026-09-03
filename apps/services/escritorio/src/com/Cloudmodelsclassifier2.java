package src.com;

import javax.swing.*;
import javax.swing.border.Border;
import java.awt.*;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Scanner;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * Modelo de servicio Cloud identificado por el clasificador.
 * Se usa un enum en lugar de Strings sueltos para evitar errores de tipeo
 * y para centralizar en un solo lugar el texto que se muestra al usuario.
 */
enum CloudServiceModel {
    IAAS("IaaS (Infrastructure as a Service)"),
    PAAS("PaaS (Platform as a Service)"),
    SAAS("SaaS (Software as a Service)"),
    FAAS("FaaS (Function as a Service)"),
    DESCONOCIDO("No identificado");

    private final String etiqueta;

    CloudServiceModel(String etiqueta) {
        this.etiqueta = etiqueta;
    }

    public String getEtiqueta() {
        return etiqueta;
    }
}

/**
 * Una coincidencia individual entre el texto del usuario y el lexico de
 * una categoria: que termino (palabra o frase) se detecto y cuantos
 * puntos aporto. Sirve para que tanto la GUI como la CLI puedan mostrar
 * "por que" se eligio una categoria, no solo el resultado final.
 */
record Coincidencia(String termino, int peso) {
}

/**
 * Una frase clave (secuencia de N palabras ya normalizadas) junto con el
 * puntaje que aporta si aparece en el texto. Se usa para detectar
 * conceptos de mas de una palabra, como "sistema operativo" o
 * "cada vez que", que una simple lista de palabras sueltas no podria
 * capturar.
 */
record FraseClave(int peso, List<String> palabras) {
    static FraseClave de(int peso, String... palabras) {
        return new FraseClave(peso, List.of(palabras));
    }
}

/**
 * Texto ya procesado por el pipeline de NLP: conserva tanto la lista
 * completa de tokens (para poder detectar frases, que necesitan a veces
 * palabras de enlace como "el" o "que") como la lista de tokens de
 * contenido (sin stopwords, para el conteo de palabras clave sueltas).
 */
final class ProcessedText {

    private final String textoOriginal;
    private final List<String> tokensCompletos;   // normalizados y con stemming, incluye stopwords
    private final List<String> tokensContenido;   // igual que arriba, pero sin stopwords
    private final boolean contieneNegacion;

    ProcessedText(String textoOriginal, List<String> tokensCompletos,
                  List<String> tokensContenido, boolean contieneNegacion) {
        this.textoOriginal = textoOriginal;
        this.tokensCompletos = tokensCompletos;
        this.tokensContenido = tokensContenido;
        this.contieneNegacion = contieneNegacion;
    }

    public String getTextoOriginal() {
        return textoOriginal;
    }

    public boolean contieneNegacion() {
        return contieneNegacion;
    }

    /** True si la palabra (ya normalizada) aparece entre los tokens de contenido. */
    public boolean contienePalabra(String palabra) {
        return tokensContenido.contains(palabra);
    }

    /**
     * True si la secuencia de palabras aparece de forma consecutiva en el
     * texto. Se busca sobre tokensCompletos (no sobre tokensContenido)
     * porque frases como "desde el navegador" o "cada vez que" dependen
     * de palabras que, sueltas, se habrian eliminado como stopwords.
     */
    public boolean contieneFrase(List<String> palabrasFrase) {
        int n = palabrasFrase.size();
        if (n == 0 || tokensCompletos.size() < n) {
            return false;
        }
        for (int i = 0; i <= tokensCompletos.size() - n; i++) {
            if (tokensCompletos.subList(i, i + n).equals(palabrasFrase)) {
                return true;
            }
        }
        return false;
    }
}

/**
 * Pipeline de procesamiento de lenguaje natural. Aplica, en orden, las
 * tecnicas basicas de NLP pedidas para este ejercicio:
 *
 *   1. Conversion a minusculas
 *   2. Limpieza de texto (quitar tildes, puntuacion y simbolos)
 *   3. Tokenizacion (separar en palabras)
 *   4. Normalizacion (unificar acentos/mayusculas, ya cubierta en 1-2)
 *   5. Stemming (reducir variantes/plurales a una raiz comun)
 *   6. Eliminacion de stopwords (para el conteo de palabras sueltas)
 *
 * Esta clase no sabe nada sobre "IaaS" ni sobre puntuaciones: solo
 * transforma texto libre en una estructura (ProcessedText) que el
 * clasificador pueda consultar. Esa separacion permite, por ejemplo,
 * cambiar la lista de stopwords sin tocar la logica de clasificacion.
 */
final class NlpPipeline {

    // Palabras de negacion: se excluyen deliberadamente de STOPWORDS
    // porque son la clave para detectar frases como "sin administrar
    // servidores", donde negar un termino cambia por completo su
    // significado para el clasificador (ver CloudServiceClassifier).
    private static final Set<String> NEGACIONES = Set.of("no", "sin", "ni", "nunca", "jamas");

    // Lista basica de stopwords en español (articulos, preposiciones,
    // pronombres y conectores muy frecuentes). No pretende ser exhaustiva:
    // basta con cubrir las palabras que mas ruido meten en el conteo de
    // palabras clave para este dominio.
    private static final Set<String> STOPWORDS = Set.of(
            "el", "la", "los", "las", "de", "del", "al", "un", "una", "unos", "unas",
            "y", "o", "u", "a", "en", "que", "con", "para", "por", "es", "son", "se",
            "su", "sus", "mi", "mis", "tu", "tus", "lo", "le", "les", "como", "mas",
            "pero", "si", "tambien", "muy", "desde", "hasta", "entre", "sobre",
            "este", "esta", "estos", "estas", "ese", "esa", "esos", "esas"
    );

    private NlpPipeline() {
        // Clase de utilidades: no debe instanciarse.
    }

    public static ProcessedText process(String textoOriginal) {
        String limpio = limpiar(textoOriginal);
        List<String> tokensCrudos = tokenizar(limpio);

        // Se aplica stemming a TODOS los tokens (incluidas las stopwords)
        // antes de filtrar nada, para que las frases de varias palabras
        // (que a veces necesitan una stopword como "el" o "que" para
        // mantener la posicion relativa) sigan siendo detectables.
        List<String> tokensCompletos = tokensCrudos.stream()
                .map(NlpPipeline::stem)
                .collect(Collectors.toList());

        boolean contieneNegacion = tokensCompletos.stream().anyMatch(NEGACIONES::contains);

        List<String> tokensContenido = tokensCompletos.stream()
                .filter(t -> !t.isBlank() && !STOPWORDS.contains(t))
                .collect(Collectors.toList());

        return new ProcessedText(textoOriginal, tokensCompletos, tokensContenido, contieneNegacion);
    }

    /**
     * Limpieza + normalizacion: pasa a minusculas, descompone los
     * caracteres acentuados (NFD) y descarta las marcas diacriticas
     * (tildes), para que "aplicación" y "aplicacion" se traten como la
     * misma palabra. Cualquier caracter que no sea una letra o un espacio
     * (puntuacion, numeros, simbolos) se reemplaza por espacio.
     */
    private static String limpiar(String texto) {
        String sinAcentos = Normalizer.normalize(texto.toLowerCase(), Normalizer.Form.NFD)
                .replaceAll("\\p{Mn}+", "");
        String soloLetras = sinAcentos.replaceAll("[^a-z ]", " ");
        return soloLetras.replaceAll("\\s+", " ").trim();
    }

    private static List<String> tokenizar(String textoLimpio) {
        if (textoLimpio.isEmpty()) {
            return new ArrayList<>();
        }
        return new ArrayList<>(Arrays.asList(textoLimpio.split(" ")));
    }

    /**
     * Stemming simplificado para español. No es un algoritmo completo
     * (como Snowball); solo cubre los dos casos que mas afectan a este
     * dominio: adverbios en "-mente" y las dos formas tipicas de plural
     * ("-es" para palabras terminadas en consonante, "-s" para palabras
     * terminadas en vocal). Es suficiente para que "servidores",
     * "aplicaciones" o "virtuales" calcen con sus formas singulares en el
     * lexico del clasificador.
     */
    private static String stem(String palabra) {
        if (palabra.length() > 7 && palabra.endsWith("mente")) {
            return palabra.substring(0, palabra.length() - 5);
        }
        if (palabra.length() > 4 && palabra.endsWith("es")) {
            return palabra.substring(0, palabra.length() - 2);
        }
        if (palabra.length() > 3 && palabra.endsWith("s")) {
            return palabra.substring(0, palabra.length() - 1);
        }
        return palabra;
    }
}

/**
 * Resultado completo de una clasificacion: el modelo elegido, el puntaje
 * que obtuvo cada categoria y que terminos concretos se detectaron en
 * cada una. Se expone todo esto (y no solo el modelo ganador) para que
 * tanto la GUI como la CLI puedan explicarle al usuario el porque de la
 * decision, algo que un clasificador "caja negra" no permitiria.
 */
final class ClassificationResult {

    private final CloudServiceModel modelo;
    private final Map<CloudServiceModel, Integer> puntuaciones;
    private final Map<CloudServiceModel, List<Coincidencia>> coincidencias;

    ClassificationResult(CloudServiceModel modelo,
                          Map<CloudServiceModel, Integer> puntuaciones,
                          Map<CloudServiceModel, List<Coincidencia>> coincidencias) {
        this.modelo = modelo;
        this.puntuaciones = puntuaciones;
        this.coincidencias = coincidencias;
    }

    public CloudServiceModel getModelo() {
        return modelo;
    }

    public Map<CloudServiceModel, Integer> getPuntuaciones() {
        return puntuaciones;
    }

    public Map<CloudServiceModel, List<Coincidencia>> getCoincidencias() {
        return coincidencias;
    }
}

/**
 * Logica de clasificacion basada en reglas, reforzada con las tecnicas de
 * NLP del enunciado (ver NlpPipeline). No importa Swing ni sabe como se
 * presenta el resultado: recibe texto y devuelve un ClassificationResult,
 * lo que permite que la GUI y la CLI compartan exactamente la misma
 * implementacion sin duplicar reglas.
 *
 * Cada categoria tiene su propio metodo de puntuacion independiente
 * (scoreIaaS, scorePaaS, scoreSaaS, scoreFaaS), como se pedia en la
 * version anterior; la unica diferencia es que ahora, en vez de "encontro
 * / no encontro" un patron, cada uno suma puntos por cada palabra o frase
 * clave detectada (identificacion de conceptos relevantes + asignacion de
 * puntuaciones).
 */
class CloudServiceClassifier {

    // --- IaaS -----------------------------------------------------------
    // Palabras de infraestructura "neutras": aparecen en descripciones de
    // IaaS pero tambien, a veces, como parte de otras cosas (por eso
    // llevan un peso bajo y no se ven afectadas por la negacion).
    private static final Map<String, Integer> IAAS_PALABRAS_GENERALES = Map.of(
            "almacenamiento", 1,
            "red", 1,
            "cpu", 2,
            "disco", 2,
            "vm", 1
    );

    // Palabras y frases que implican explicitamente "administrar/tener
    // infraestructura propia". Son el corazon de la definicion de IaaS,
    // pero si aparecen negadas ("sin administrar servidores") en realidad
    // describen lo opuesto: por eso se tratan aparte (ver scoreIaaS y
    // scorePaaS).
    private static final Map<String, Integer> IAAS_PALABRAS_GESTION = Map.of(
            "servidor", 3,
            "infraestructura", 3,
            "hardware", 2
    );
    private static final List<FraseClave> IAAS_FRASES_GESTION = List.of(
            FraseClave.de(4, "maquina", "virtual"),
            FraseClave.de(4, "servidor", "virtual"),
            FraseClave.de(3, "sistema", "operativo")
    );
    private static final List<FraseClave> IAAS_FRASES_GENERALES = List.of(
            FraseClave.de(5, "infraestructura", "como", "servicio"),
            FraseClave.de(4, "aws", "ec"),
            FraseClave.de(4, "azure", "vm")
    );

    // --- PaaS -------------------------------------------------------------
    private static final Map<String, Integer> PAAS_PALABRAS = Map.of(
            "plataforma", 3,
            "desplegar", 3,
            "desarrollo", 2,
            "runtime", 3,
            "contenedor", 2,
            "docker", 3,
            "kubernetes", 3,
            "heroku", 3
    );
    private static final List<FraseClave> PAAS_FRASES = List.of(
            FraseClave.de(3, "aplicacion", "web"),
            FraseClave.de(5, "plataforma", "como", "servicio"),
            FraseClave.de(4, "google", "app", "engine")
    );
    // Bono que se suma a PaaS cuando el texto niega explicitamente la
    // gestion de infraestructura (ver scorePaaS): "no administrar
    // servidores" es, en la practica, la definicion de PaaS.
    private static final int PAAS_BONO_GESTION_DELEGADA = 4;

    // --- SaaS ---------------------------------------------------------
    private static final Map<String, Integer> SAAS_PALABRAS = Map.of(
            "software", 3,
            "aplicacion", 1,
            "correo", 3,
            "gmail", 3,
            "salesforce", 3,
            "crm", 3,
            "erp", 3,
            "navegador", 2,
            "suscripcion", 3
    );
    private static final List<FraseClave> SAAS_FRASES = List.of(
            FraseClave.de(5, "software", "como", "servicio"),
            FraseClave.de(4, "suscripcion", "mensual"),
            FraseClave.de(3, "desde", "el", "navegador"),
            FraseClave.de(4, "office", "365"),
            FraseClave.de(4, "microsoft", "365")
    );

    // --- FaaS ----------------------------------------------------------
    private static final Map<String, Integer> FAAS_PALABRAS = Map.of(
            "funcion", 3,
            "evento", 3,
            "serverless", 4,
            "lambda", 3,
            "automatica", 2,
            "trigger", 3,
            "disparar", 3,
            "codigo", 1
    );
    private static final List<FraseClave> FAAS_FRASES = List.of(
            FraseClave.de(4, "cada", "vez", "que"),
            FraseClave.de(5, "funcion", "como", "servicio"),
            FraseClave.de(4, "azure", "function"),
            FraseClave.de(4, "cloud", "function"),
            FraseClave.de(3, "ejecutar", "codigo")
    );

    /**
     * Punto de entrada simple: devuelve solo el modelo ganador. Se
     * mantiene por compatibilidad y porque, la mayoria de las veces, es
     * lo unico que hace falta.
     */
    public CloudServiceModel classify(String descripcion) {
        return classifyConDetalle(descripcion).getModelo();
    }

    /**
     * Clasifica el texto y devuelve, ademas del modelo elegido, el
     * puntaje y las coincidencias de cada categoria. Es el metodo que
     * realmente usan tanto la GUI como la CLI (ver Cloudmodelsclassifier2
     * y CloudClassifierCLI): al compartir esta unica implementacion se
     * evita que ambas interfaces terminen con reglas de clasificacion
     * distintas.
     *
     * @throws IllegalArgumentException si la descripcion es nula
     */
    public ClassificationResult classifyConDetalle(String descripcion) {
        if (descripcion == null) {
            // Defensa adicional: aunque la GUI y la CLI validan antes de
            // llamar aqui, el metodo no deberia asumir que siempre se
            // invoca desde uno de esos dos lugares.
            throw new IllegalArgumentException("La descripcion no puede ser nula.");
        }

        ProcessedText texto = NlpPipeline.process(descripcion);

        Map<CloudServiceModel, List<Coincidencia>> coincidencias = new LinkedHashMap<>();
        coincidencias.put(CloudServiceModel.IAAS, scoreIaaS(texto));
        coincidencias.put(CloudServiceModel.PAAS, scorePaaS(texto));
        coincidencias.put(CloudServiceModel.SAAS, scoreSaaS(texto));
        coincidencias.put(CloudServiceModel.FAAS, scoreFaaS(texto));

        Map<CloudServiceModel, Integer> puntuaciones = new LinkedHashMap<>();
        for (Map.Entry<CloudServiceModel, List<Coincidencia>> entrada : coincidencias.entrySet()) {
            int total = entrada.getValue().stream().mapToInt(Coincidencia::peso).sum();
            puntuaciones.put(entrada.getKey(), total);
        }

        // Se elige la categoria con mayor puntaje; en caso de empate se
        // respeta el orden IaaS -> PaaS -> SaaS -> FaaS (el mismo orden de
        // evaluacion de la version anterior basada solo en reglas). Si
        // ninguna categoria acumulo puntos, el resultado es DESCONOCIDO.
        CloudServiceModel ganador = CloudServiceModel.DESCONOCIDO;
        int mejorPuntaje = 0;
        for (CloudServiceModel candidato : List.of(CloudServiceModel.IAAS, CloudServiceModel.PAAS,
                CloudServiceModel.SAAS, CloudServiceModel.FAAS)) {
            int puntaje = puntuaciones.get(candidato);
            if (puntaje > mejorPuntaje) {
                mejorPuntaje = puntaje;
                ganador = candidato;
            }
        }

        return new ClassificationResult(ganador, puntuaciones, coincidencias);
    }

    // Cada metodo de puntuacion es independiente: recibe el texto ya
    // procesado y devuelve la lista de coincidencias de su propia
    // categoria, sin conocer nada de las demas (salvo la excepcion
    // documentada en scorePaaS, que solo LEE informacion publica del
    // texto, no el resultado de scoreIaaS).

    public List<Coincidencia> scoreIaaS(ProcessedText texto) {
        List<Coincidencia> resultado = new ArrayList<>();

        agregarPalabras(resultado, texto, IAAS_PALABRAS_GENERALES);
        agregarFrases(resultado, texto, IAAS_FRASES_GENERALES);

        // Las palabras/frases de "gestion de infraestructura" solo cuentan
        // si NO estan negadas. Si el texto dice "sin administrar
        // servidores", mencionar "servidor" no es evidencia de IaaS.
        if (!texto.contieneNegacion()) {
            agregarPalabras(resultado, texto, IAAS_PALABRAS_GESTION);
            agregarFrases(resultado, texto, IAAS_FRASES_GESTION);
        }

        return resultado;
    }

    public List<Coincidencia> scorePaaS(ProcessedText texto) {
        List<Coincidencia> resultado = new ArrayList<>();

        agregarPalabras(resultado, texto, PAAS_PALABRAS);
        agregarFrases(resultado, texto, PAAS_FRASES);

        // Si el texto niega explicitamente administrar infraestructura
        // (servidores, sistema operativo, maquinas virtuales...), eso es
        // en si mismo un indicio de PaaS: alguien mas se encarga de esa
        // capa. Este metodo solo consulta al texto directamente (via los
        // mismos terminos de IAAS_PALABRAS_GESTION / IAAS_FRASES_GESTION),
        // no el resultado de scoreIaaS, para que ambos metodos sigan
        // siendo independientes entre si.
        boolean mencionaGestionInfraestructura =
                IAAS_PALABRAS_GESTION.keySet().stream().anyMatch(texto::contienePalabra)
                        || IAAS_FRASES_GESTION.stream().anyMatch(f -> texto.contieneFrase(f.palabras()));

        if (texto.contieneNegacion() && mencionaGestionInfraestructura) {
            resultado.add(new Coincidencia("gestion de infraestructura delegada (negacion detectada)",
                    PAAS_BONO_GESTION_DELEGADA));
        }

        return resultado;
    }

    public List<Coincidencia> scoreSaaS(ProcessedText texto) {
        List<Coincidencia> resultado = new ArrayList<>();
        agregarPalabras(resultado, texto, SAAS_PALABRAS);
        agregarFrases(resultado, texto, SAAS_FRASES);
        return resultado;
    }

    public List<Coincidencia> scoreFaaS(ProcessedText texto) {
        List<Coincidencia> resultado = new ArrayList<>();
        agregarPalabras(resultado, texto, FAAS_PALABRAS);
        agregarFrases(resultado, texto, FAAS_FRASES);
        return resultado;
    }

    private static void agregarPalabras(List<Coincidencia> destino, ProcessedText texto,
                                         Map<String, Integer> lexico) {
        for (Map.Entry<String, Integer> entrada : lexico.entrySet()) {
            if (texto.contienePalabra(entrada.getKey())) {
                destino.add(new Coincidencia(entrada.getKey(), entrada.getValue()));
            }
        }
    }

    private static void agregarFrases(List<Coincidencia> destino, ProcessedText texto,
                                       List<FraseClave> frases) {
        for (FraseClave frase : frases) {
            if (texto.contieneFrase(frase.palabras())) {
                destino.add(new Coincidencia(String.join(" ", frase.palabras()), frase.peso()));
            }
        }
    }
}

/**
 * Resultado inmutable de una validacion: indica si el campo es valido y,
 * si no lo es, el mensaje que se debe mostrar al usuario.
 */
final class ValidationResult {
    private final boolean valida;
    private final String mensaje;

    private ValidationResult(boolean valida, String mensaje) {
        this.valida = valida;
        this.mensaje = mensaje;
    }

    public static ValidationResult ok() {
        return new ValidationResult(true, "");
    }

    public static ValidationResult error(String mensaje) {
        return new ValidationResult(false, mensaje);
    }

    public boolean isValida() {
        return valida;
    }

    public String getMensaje() {
        return mensaje;
    }
}

/**
 * Reglas de validacion de los campos del formulario. Se separa de la GUI
 * (y de la CLI) para poder ajustar las reglas sin tocar ninguna de las
 * dos interfaces, y para que ambas compartan exactamente los mismos
 * criterios de "dato valido".
 */
final class InputValidator {

    private static final int DESCRIPCION_MIN_LENGTH = 5;
    private static final Pattern SOLO_LETRAS = Pattern.compile("^[A-Za-zÁÉÍÓÚáéíóúÑñ ]+$");

    private InputValidator() {
        // Clase de utilidades: no debe instanciarse.
    }

    public static ValidationResult validarNombre(String nombre) {
        if (nombre == null || nombre.trim().isEmpty()) {
            return ValidationResult.error("El nombre es obligatorio.");
        }
        if (!SOLO_LETRAS.matcher(nombre.trim()).matches()) {
            return ValidationResult.error("El nombre solo debe contener letras.");
        }
        return ValidationResult.ok();
    }

    public static ValidationResult validarApellido(String apellido) {
        if (apellido == null || apellido.trim().isEmpty()) {
            return ValidationResult.error("El apellido es obligatorio.");
        }
        if (!SOLO_LETRAS.matcher(apellido.trim()).matches()) {
            return ValidationResult.error("El apellido solo debe contener letras.");
        }
        return ValidationResult.ok();
    }

    public static ValidationResult validarDescripcion(String descripcion) {
        if (descripcion == null || descripcion.trim().isEmpty()) {
            return ValidationResult.error("Escriba una descripcion del servicio Cloud.");
        }
        if (descripcion.trim().length() < DESCRIPCION_MIN_LENGTH) {
            return ValidationResult.error(
                    "La descripcion es demasiado corta (minimo " + DESCRIPCION_MIN_LENGTH + " caracteres).");
        }
        return ValidationResult.ok();
    }
}

/**
 * Interfaz de linea de comandos. Igual que la GUI, su unica
 * responsabilidad es capturar la entrada (por argumentos o por stdin),
 * validarla y mostrar el resultado; toda la logica de clasificacion vive
 * en CloudServiceClassifier, la misma clase que usa la ventana grafica.
 *
 * Nota sobre acentos: cuando la descripcion se pasa como argumento (no
 * por stdin), Java decodifica los argumentos usando la codificacion por
 * defecto del sistema operativo antes de que este programa pueda
 * intervenir. En una terminal configurada en UTF-8 (lo habitual en
 * Windows, macOS y Linux modernos) las tildes y la "ñ" se leen bien; en
 * una terminal con una configuracion regional antigua (por ejemplo,
 * "POSIX" o "C") podrian perderse. Si eso ocurre, se recomienda escribir
 * la descripcion sin tildes o usar el modo interactivo (sin argumentos),
 * que si fuerza UTF-8 explicitamente (ver obtenerDescripcion).
 */
final class CloudClassifierCLI {

    private CloudClassifierCLI() {
        // Clase de utilidades: no debe instanciarse.
    }

    public static void ejecutar(String[] argsDescripcion) {
        try {
            String descripcion = obtenerDescripcion(argsDescripcion);

            ValidationResult validacion = InputValidator.validarDescripcion(descripcion);
            if (!validacion.isValida()) {
                System.out.println("Error: " + validacion.getMensaje());
                return;
            }

            // Misma clase, mismo metodo que usa la GUI: la CLI no
            // reimplementa ninguna regla de clasificacion.
            CloudServiceClassifier classifier = new CloudServiceClassifier();
            ClassificationResult resultado = classifier.classifyConDetalle(descripcion);

            imprimirResultado(resultado);
        } catch (Exception ex) {
            // Manejo basico de errores: cualquier fallo inesperado se
            // informa por consola en vez de imprimir una traza cruda.
            System.out.println("Ocurrio un error inesperado: " + ex.getMessage());
        }
    }

    private static String obtenerDescripcion(String[] argsDescripcion) {
        if (argsDescripcion.length > 0) {
            return String.join(" ", argsDescripcion);
        }
        System.out.println("=== Clasificador de Servicios Cloud Computing (modo linea de comandos) ===");
        System.out.print("Descripcion del servicio Cloud: ");
        // Se fuerza UTF-8 explicitamente (en vez de confiar en la
        // codificacion por defecto del sistema operativo) para que
        // tildes y "ñ" se lean bien sin importar la configuracion
        // regional de la terminal donde se ejecute el programa.
        Scanner scanner = new Scanner(System.in, java.nio.charset.StandardCharsets.UTF_8);
        return scanner.hasNextLine() ? scanner.nextLine() : "";
    }

    private static void imprimirResultado(ClassificationResult resultado) {
        System.out.println();
        System.out.println("Clasificacion: " + resultado.getModelo().getEtiqueta());
        System.out.println();
        System.out.println("Puntuaciones por categoria:");

        for (CloudServiceModel modelo : List.of(CloudServiceModel.IAAS, CloudServiceModel.PAAS,
                CloudServiceModel.SAAS, CloudServiceModel.FAAS)) {
            int puntaje = resultado.getPuntuaciones().getOrDefault(modelo, 0);
            System.out.printf("  %-6s %d puntos%n", modelo.name(), puntaje);
            for (Coincidencia c : resultado.getCoincidencias().getOrDefault(modelo, List.of())) {
                System.out.printf("      + %s (%d)%n", c.termino(), c.peso());
            }
        }
    }
}

/**
 * Interfaz grafica. Su unica responsabilidad es capturar la entrada del
 * usuario, delegar la validacion a InputValidator y la clasificacion a
 * CloudServiceClassifier, y mostrar el resultado. No contiene expresiones
 * regulares ni reglas de negocio: si el dia de mañana cambian las reglas
 * de clasificacion, este archivo no deberia tocarse mas que en la parte
 * visual.
 *
 * Tambien actua como punto de entrada del programa: si se ejecuta con el
 * argumento "--cli", delega en CloudClassifierCLI en vez de abrir la
 * ventana (ver main). Ambos modos reutilizan la misma
 * CloudServiceClassifier.
 */
public class Cloudmodelsclassifier2 extends JFrame {

    private static final Color COLOR_ERROR = new Color(192, 57, 43);
    private static final Border BORDE_ERROR = BorderFactory.createLineBorder(COLOR_ERROR, 1);

    private JTextField txtNombre;
    private JTextField txtApellido;
    private JTextArea txtDescripcion;
    private JLabel lblResultado;

    // Etiquetas de retroalimentacion (una por campo) para mostrar errores
    // de validacion junto al campo correspondiente, en vez de interrumpir
    // al usuario con un dialogo por cada campo invalido.
    private JLabel lblErrorNombre;
    private JLabel lblErrorApellido;
    private JLabel lblErrorDescripcion;

    // Bordes originales de cada campo, guardados para poder restaurarlos
    // cuando el usuario corrige un dato invalido.
    private Border bordeOriginalNombre;
    private Border bordeOriginalApellido;
    private Border bordeOriginalDescripcion;

    // La GUI delega en esta instancia; no reimplementa la logica de
    // clasificacion dentro de la clase de ventana.
    private final CloudServiceClassifier classifier = new CloudServiceClassifier();

    public Cloudmodelsclassifier2() {
        setTitle("Clasificador de Servicios Cloud Computing");
        setSize(650, 600);
        setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
        setLocationRelativeTo(null);

        JPanel panel = new JPanel(new BorderLayout(10, 10));
        panel.setBorder(BorderFactory.createEmptyBorder(10, 10, 10, 10));

        panel.add(construirPanelDatos(), BorderLayout.NORTH);
        panel.add(construirPanelDescripcion(), BorderLayout.CENTER);
        panel.add(construirPanelInferior(), BorderLayout.SOUTH);

        add(panel);
    }

    private JPanel construirPanelDatos() {
        JPanel panelDatos = new JPanel();
        panelDatos.setLayout(new BoxLayout(panelDatos, BoxLayout.Y_AXIS));

        txtNombre = new JTextField();
        bordeOriginalNombre = txtNombre.getBorder();
        lblErrorNombre = crearEtiquetaError();
        panelDatos.add(crearFilaCampo("Nombre:", txtNombre, lblErrorNombre));

        panelDatos.add(Box.createVerticalStrut(6));

        txtApellido = new JTextField();
        bordeOriginalApellido = txtApellido.getBorder();
        lblErrorApellido = crearEtiquetaError();
        panelDatos.add(crearFilaCampo("Apellido:", txtApellido, lblErrorApellido));

        return panelDatos;
    }

    private JPanel construirPanelDescripcion() {
        JPanel contenedor = new JPanel(new BorderLayout(0, 4));

        txtDescripcion = new JTextArea(10, 40);
        txtDescripcion.setLineWrap(true);
        txtDescripcion.setWrapStyleWord(true);
        bordeOriginalDescripcion = txtDescripcion.getBorder();

        JScrollPane scroll = new JScrollPane(txtDescripcion);
        scroll.setBorder(BorderFactory.createTitledBorder(
                "Escriba una descripcion del servicio Cloud"));

        lblErrorDescripcion = crearEtiquetaError();

        contenedor.add(scroll, BorderLayout.CENTER);
        contenedor.add(lblErrorDescripcion, BorderLayout.SOUTH);

        return contenedor;
    }

    private JPanel construirPanelInferior() {
        JPanel inferior = new JPanel(new BorderLayout());

        JButton btnClasificar = new JButton("Clasificar");
        btnClasificar.addActionListener(e -> onClasificar());

        lblResultado = new JLabel("<html>Resultado: </html>");
        lblResultado.setFont(new Font("Arial", Font.BOLD, 16));
        lblResultado.setForeground(Color.BLUE);
        lblResultado.setVerticalAlignment(SwingConstants.TOP);

        inferior.add(btnClasificar, BorderLayout.NORTH);
        inferior.add(lblResultado, BorderLayout.CENTER);

        return inferior;
    }

    private JPanel crearFilaCampo(String etiquetaTexto, JTextField campo, JLabel etiquetaError) {
        JPanel fila = new JPanel(new BorderLayout(8, 2));

        JPanel campoConEtiqueta = new JPanel(new BorderLayout(8, 0));
        campoConEtiqueta.add(new JLabel(etiquetaTexto), BorderLayout.WEST);
        campoConEtiqueta.add(campo, BorderLayout.CENTER);

        fila.add(campoConEtiqueta, BorderLayout.NORTH);
        fila.add(etiquetaError, BorderLayout.SOUTH);
        return fila;
    }

    private JLabel crearEtiquetaError() {
        JLabel etiqueta = new JLabel(" ");
        etiqueta.setForeground(COLOR_ERROR);
        etiqueta.setFont(etiqueta.getFont().deriveFont(11f));
        return etiqueta;
    }

    /**
     * Maneja el clic del boton "Clasificar": valida, clasifica y actualiza
     * la interfaz. La logica de clasificacion en si vive en
     * CloudServiceClassifier; aqui solo se orquesta el flujo y se traducen
     * los resultados a elementos visuales.
     */
    private void onClasificar() {
        String nombre = txtNombre.getText();
        String apellido = txtApellido.getText();
        String descripcion = txtDescripcion.getText();

        // Se valida cada campo por separado para poder mostrar
        // retroalimentacion especifica junto a cada uno.
        ValidationResult resultadoNombre = InputValidator.validarNombre(nombre);
        ValidationResult resultadoApellido = InputValidator.validarApellido(apellido);
        ValidationResult resultadoDescripcion = InputValidator.validarDescripcion(descripcion);

        actualizarRetroalimentacion(txtNombre, lblErrorNombre, bordeOriginalNombre, resultadoNombre);
        actualizarRetroalimentacion(txtApellido, lblErrorApellido, bordeOriginalApellido, resultadoApellido);
        actualizarRetroalimentacion(txtDescripcion, lblErrorDescripcion, bordeOriginalDescripcion, resultadoDescripcion);

        boolean todoValido = resultadoNombre.isValida()
                && resultadoApellido.isValida()
                && resultadoDescripcion.isValida();

        if (!todoValido) {
            // Si algun campo no es valido, no se invoca al clasificador:
            // se evita trabajo innecesario y resultados con datos
            // incompletos o incorrectos.
            return;
        }

        try {
            ClassificationResult resultado = classifier.classifyConDetalle(descripcion);
            mostrarResultado(nombre.trim(), apellido.trim(), resultado);
        } catch (IllegalArgumentException ex) {
            // Manejo basico de errores: si algo inesperado ocurre en la
            // logica de clasificacion, se informa al usuario en lugar de
            // dejar que la excepcion se propague y cierre la aplicacion.
            lblResultado.setForeground(COLOR_ERROR);
            lblResultado.setText("<html>Ocurrio un error al clasificar: " + escapeHtml(ex.getMessage()) + "</html>");
        }
    }

    /**
     * Refleja el resultado de una validacion en el campo (color de borde)
     * y en su etiqueta de error asociada.
     */
    private void actualizarRetroalimentacion(JComponent campo, JLabel etiquetaError,
                                              Border bordeOriginal, ValidationResult resultado) {
        if (resultado.isValida()) {
            etiquetaError.setText(" ");
            campo.setBorder(bordeOriginal);
        } else {
            etiquetaError.setText(resultado.getMensaje());
            campo.setBorder(BORDE_ERROR);
        }
    }

    private void mostrarResultado(String nombre, String apellido, ClassificationResult resultado) {
        CloudServiceModel modelo = resultado.getModelo();
        List<Coincidencia> coincidencias = resultado.getCoincidencias().getOrDefault(modelo, List.of());

        String palabrasClave = coincidencias.stream()
                .map(Coincidencia::termino)
                .collect(Collectors.joining(", "));

        StringBuilder html = new StringBuilder("<html><b>Usuario:</b> ")
                .append(escapeHtml(nombre)).append(" ").append(escapeHtml(apellido))
                .append("<br><b>Clasificacion:</b> ").append(escapeHtml(modelo.getEtiqueta()));

        if (!palabrasClave.isEmpty()) {
            html.append("<br><b>Palabras clave detectadas:</b> ").append(escapeHtml(palabrasClave));
        }
        html.append("</html>");

        lblResultado.setForeground(Color.BLUE);
        lblResultado.setText(html.toString());
    }

    /**
     * Escapa caracteres especiales de HTML antes de insertarlos en un
     * JLabel con formato HTML, para que un nombre, apellido o mensaje de
     * error que contenga "&lt;" o "&amp;" no rompa el marcado.
     */
    private static String escapeHtml(String texto) {
        if (texto == null) {
            return "";
        }
        return texto
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;");
    }

    /**
     * Punto de entrada del programa. Si se invoca con el argumento
     * "--cli" (por ejemplo: {@code java src.com.Cloudmodelsclassifier2
     * --cli "descripcion del servicio"}), se ejecuta en modo linea de
     * comandos; en cualquier otro caso se abre la interfaz grafica. Ambos
     * modos usan la misma CloudServiceClassifier, por lo que nunca pueden
     * dar resultados distintos para la misma descripcion.
     */
    public static void main(String[] args) {
        if (args.length > 0 && "--cli".equalsIgnoreCase(args[0])) {
            String[] resto = Arrays.copyOfRange(args, 1, args.length);
            CloudClassifierCLI.ejecutar(resto);
            return;
        }

        SwingUtilities.invokeLater(() -> {
            try {
                new Cloudmodelsclassifier2().setVisible(true);
            } catch (Exception ex) {
                // Manejo basico de errores tambien en el arranque: si algo
                // falla al construir la ventana, se informa por consola en
                // vez de dejar una traza cruda sin contexto.
                System.err.println("No se pudo iniciar la aplicacion: " + ex.getMessage());
            }
        });
    }
}