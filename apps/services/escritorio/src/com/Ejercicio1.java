package src.com;
import javax.swing.*;
import java.awt.*;
import java.util.regex.Pattern;

public class Ejercicio1 extends JFrame {

    private JTextField txtNombre;
    private JTextField txtApellido;
    private JTextArea txtDescripcion;
    private JLabel lblResultado;

    public Ejercicio1() {

        setTitle("Clasificador de Servicios Cloud Computing");
        setSize(650, 500);
        setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
        setLocationRelativeTo(null);

        JPanel panel = new JPanel();
        panel.setLayout(new BorderLayout(10,10));

        // Panel superior
        JPanel datos = new JPanel(new GridLayout(2,2,5,5));

        datos.add(new JLabel("Nombre:"));
        txtNombre = new JTextField();
        datos.add(txtNombre);

        datos.add(new JLabel("Apellido:"));
        txtApellido = new JTextField();
        datos.add(txtApellido);

        panel.add(datos, BorderLayout.NORTH);

        // Area de texto
        txtDescripcion = new JTextArea(10,40);
        txtDescripcion.setLineWrap(true);
        txtDescripcion.setWrapStyleWord(true);

        JScrollPane scroll = new JScrollPane(txtDescripcion);
        scroll.setBorder(BorderFactory.createTitledBorder(
                "Escriba una descripcion del servicio Cloud"));

        panel.add(scroll, BorderLayout.CENTER);

        // Panel inferior
        JPanel inferior = new JPanel(new BorderLayout());

        JButton btnClasificar = new JButton("Clasificar");

        lblResultado = new JLabel("Resultado: ");
        lblResultado.setFont(new Font("Arial", Font.BOLD, 18));
        lblResultado.setForeground(Color.BLUE);

        btnClasificar.addActionListener(e -> clasificar());

        inferior.add(btnClasificar, BorderLayout.NORTH);
        inferior.add(lblResultado, BorderLayout.CENTER);

        panel.add(inferior, BorderLayout.SOUTH);

        add(panel);
    }

    private void clasificar() {

        String nombre = txtNombre.getText().trim();
        String apellido = txtApellido.getText().trim();
        String texto = txtDescripcion.getText().toLowerCase();

        if(nombre.isEmpty() || apellido.isEmpty() || texto.isEmpty()){
            JOptionPane.showMessageDialog(this,
                    "Complete todos los campos.",
                    "Aviso",
                    JOptionPane.WARNING_MESSAGE);
            return;
        }

        String resultado = "No identificado";

        // -------- IaaS --------
        if(Pattern.compile("\\b(servidor|maquina virtual|vm|infraestructura|almacenamiento|red|cpu|disco|aws ec2|azure vm)\\b")
                .matcher(texto).find()){

            resultado = "IaaS (Infrastructure as a Service)";
        }

        // -------- PaaS --------
        else if(Pattern.compile("\\b(plataforma|desarrollo|deploy|desplegar|runtime|contenedor|docker|kubernetes|heroku|google app engine)\\b")
                .matcher(texto).find()){

            resultado = "PaaS (Platform as a Service)";
        }

        // -------- SaaS --------
        else if(Pattern.compile("\\b(software|aplicacion|correo|gmail|office 365|microsoft 365|salesforce|crm|erp|navegador)\\b")
                .matcher(texto).find()){

            resultado = "SaaS (Software as a Service)";
        }

        // -------- FaaS --------
        else if(Pattern.compile("\\b(funcion|funciones|evento|serverless|lambda|azure functions|cloud functions|ejecutar codigo)\\b")
                .matcher(texto).find()){

            resultado = "FaaS (Function as a Service)";
        }

        lblResultado.setText("<html><b>Usuario:</b> "
                + nombre + " " + apellido
                + "<br><b>Clasificacion:</b> " + resultado + "</html>");
    }

    public static void main(String[] args) {

        SwingUtilities.invokeLater(() -> {
            new Ejercicio1().setVisible(true);
        });

    }

}


