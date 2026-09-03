package src.com;

import javax.swing.*;
import javax.swing.border.Border;
import java.awt.*;
import java.util.regex.Pattern;

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
 * Contiene unicamente la logica de clasificacion. No importa Swing ni sabe
 * como se presenta el resultado: recibe texto y devuelve un
 * CloudServiceModel. Al aislarla de la GUI se puede reutilizar o probar
 * (por ejemplo con JUnit) sin necesidad de levantar ninguna ventana.
 */
class CloudServiceClassifier {

    // Los patrones se compilan una sola vez como constantes de clase, ya
    // que Pattern.compile es una operacion costosa y el patron no cambia
    // entre llamadas.
    private static final Pattern IAAS_PATTERN = Pattern.compile(
            "\\b(servidor|maquina virtual|vm|infraestructura|almacenamiento|red|cpu|disco|aws ec2|azure vm)\\b");
    private static final Pattern PAAS_PATTERN = Pattern.compile(
            "\\b(plataforma|desarrollo|deploy|desplegar|runtime|contenedor|docker|kubernetes|heroku|google app engine)\\b");
    private static final Pattern SAAS_PATTERN = Pattern.compile(
            "\\b(software|aplicacion|correo|gmail|office 365|microsoft 365|salesforce|crm|erp|navegador)\\b");
    private static final Pattern FAAS_PATTERN = Pattern.compile(
            "\\b(funcion|funciones|evento|serverless|lambda|azure functions|cloud functions|ejecutar codigo)\\b");

    /**
     * Punto de entrada de la clasificacion. Se evalua en orden
     * IaaS -> PaaS -> SaaS -> FaaS porque una descripcion podria calzar en
     * mas de un patron (por ejemplo, mencionar "docker" y "aplicacion" a
     * la vez) y este orden prioriza la capa mas baja de la arquitectura
     * primero.
     *
     * @param descripcion texto a clasificar; no debe ser nulo
     * @return el modelo identificado, o DESCONOCIDO si ninguno aplica
     * @throws IllegalArgumentException si la descripcion es nula
     */
    public CloudServiceModel classify(String descripcion) {
        if (descripcion == null) {
            // Defensa adicional: aunque la GUI valida antes de invocar este
            // metodo, la clase no deberia asumir que siempre se usara desde
            // la interfaz grafica (podria llamarse desde pruebas u otro
            // punto del programa).
            throw new IllegalArgumentException("La descripcion no puede ser nula.");
        }

        String texto = descripcion.toLowerCase().trim();

        if (isIaaS(texto)) return CloudServiceModel.IAAS;
        if (isPaaS(texto)) return CloudServiceModel.PAAS;
        if (isSaaS(texto)) return CloudServiceModel.SAAS;
        if (isFaaS(texto)) return CloudServiceModel.FAAS;

        return CloudServiceModel.DESCONOCIDO;
    }

    // Cada modelo tiene su propio metodo independiente: facilita probar
    // cada regla por separado y deja explicito que patron corresponde a
    // cada capa de servicio.
    public boolean isIaaS(String texto) {
        return IAAS_PATTERN.matcher(texto).find();
    }

    public boolean isPaaS(String texto) {
        return PAAS_PATTERN.matcher(texto).find();
    }

    public boolean isSaaS(String texto) {
        return SAAS_PATTERN.matcher(texto).find();
    }

    public boolean isFaaS(String texto) {
        return FAAS_PATTERN.matcher(texto).find();
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
 * para poder ajustar las reglas (o probarlas) sin tocar Swing, y para que
 * la ventana no mezcle "como se ve" con "que es un dato valido".
 */
final class InputValidator {

    private static final int DESCRIPCION_MIN_LENGTH = 5;
    // Solo letras (incluye acentos y enie) y espacios; evita que Nombre y
    // Apellido acepten numeros o simbolos por error de captura.
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
 * Interfaz grafica. Su unica responsabilidad es capturar la entrada del
 * usuario, delegar la validacion a InputValidator y la clasificacion a
 * CloudServiceClassifier, y mostrar el resultado. No contiene expresiones
 * regulares ni reglas de negocio: si el dia de mañana cambian las reglas
 * de clasificacion, este archivo no deberia tocarse mas que en la parte
 * visual.
 */
public class CloudModelsClassifier extends JFrame {

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

    public CloudModelsClassifier() {
        setTitle("Clasificador de Servicios Cloud Computing");
        setSize(650, 560);
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

        lblResultado = new JLabel("Resultado: ");
        lblResultado.setFont(new Font("Arial", Font.BOLD, 18));
        lblResultado.setForeground(Color.BLUE);

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
        // retroalimentacion especifica junto a cada uno, en vez de un
        // unico mensaje generico como en la version anterior.
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
            CloudServiceModel modelo = classifier.classify(descripcion);
            mostrarResultado(nombre.trim(), apellido.trim(), modelo);
        } catch (IllegalArgumentException ex) {
            // Manejo basico de errores: si algo inesperado ocurre en la
            // logica de clasificacion, se informa al usuario en lugar de
            // dejar que la excepcion se propague y cierre la aplicacion.
            lblResultado.setForeground(COLOR_ERROR);
            lblResultado.setText("Ocurrio un error al clasificar: " + ex.getMessage());
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

    private void mostrarResultado(String nombre, String apellido, CloudServiceModel modelo) {
        lblResultado.setForeground(Color.BLUE);
        lblResultado.setText("<html><b>Usuario:</b> "
                + escapeHtml(nombre) + " " + escapeHtml(apellido)
                + "<br><b>Clasificacion:</b> " + escapeHtml(modelo.getEtiqueta()) + "</html>");
    }

    /**
     * Escapa caracteres especiales de HTML antes de insertarlos en un
     * JLabel con formato HTML. lblResultado usa &lt;html&gt; para permitir
     * negritas y salto de linea, y sin este escape un nombre o apellido
     * que contenga "&lt;" o "&amp;" podria romper el marcado.
     */
    private static String escapeHtml(String texto) {
        return texto
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;");
    }

    public static void main(String[] args) {
        SwingUtilities.invokeLater(() -> {
            try {
                new CloudModelsClassifier().setVisible(true);
            } catch (Exception ex) {
                // Manejo basico de errores tambien en el arranque: si algo
                // falla al construir la ventana, se informa por consola en
                // vez de dejar una traza cruda sin contexto.
                System.err.println("No se pudo iniciar la aplicacion: " + ex.getMessage());
            }
        });
    }
}
