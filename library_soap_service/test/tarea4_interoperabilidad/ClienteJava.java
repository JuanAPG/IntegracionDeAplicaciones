import mx.udem.iac.clasificacion.client.*;
import javax.xml.ws.BindingProvider;
import java.util.List;

/**
 * Cliente de interoperabilidad (Tarea 4): generado por wsimport a partir
 * de library-classiffier.wsdl, sin conocer nada de la implementacion
 * interna del servidor (Flask + xml.etree + PostgreSQL). Consume
 * ObtenerConceptosPendientes y RegistrarClasificacion.
 */
public class ClienteJava {
    public static void main(String[] args) throws Exception {
        String endpoint = args.length > 0 ? args[0] : "http://127.0.0.1:5099/soap/clasificacion";

        ClasificacionLibrosService service = new ClasificacionLibrosService();
        ClasificacionLibrosPortType port = service.getClasificacionLibrosPort();
        ((BindingProvider) port).getRequestContext()
            .put(BindingProvider.ENDPOINT_ADDRESS_PROPERTY, endpoint);

        System.out.println("Endpoint: " + endpoint);

        System.out.println("\n=== ObtenerConceptosPendientes ===");
        ObtenerConceptosPendientesRequest req1 = new ObtenerConceptosPendientesRequest();
        req1.setClasificadorEmail("java.cliente@example.com");
        req1.setLimite(10);
        ObtenerConceptosPendientesResponse resp1 = port.obtenerConceptosPendientes(req1);
        List<ConceptoPendiente> pendientes = resp1.getConcepto();
        for (ConceptoPendiente c : pendientes) {
            System.out.println("  - " + c.getNombreConcepto() + "  (" + c.getTituloLibro()
                + " / " + c.getNombreCategoria() + ")  isbn=" + c.getReferenciaLibro());
        }
        if (pendientes.isEmpty()) {
            System.out.println("  (sin pendientes)");
            return;
        }

        ConceptoPendiente elegido = pendientes.get(0);

        System.out.println("\n=== RegistrarClasificacion (valido) ===");
        RegistrarClasificacionRequest req2 = new RegistrarClasificacionRequest();
        req2.setClasificadorEmail("java.cliente@example.com");
        req2.setReferenciaLibro(elegido.getReferenciaLibro());
        req2.setReferenciaConcepto(elegido.getReferenciaConcepto());
        req2.setModeloServicio(ModeloServicioType.SAA_S);
        try {
            RegistrarClasificacionResponse resp2 = port.registrarClasificacion(req2);
            System.out.println("  exito=" + resp2.isExito() + "  mensaje=" + resp2.getMensaje());
        } catch (ErrorDetalleMessage fault) {
            ErrorDetalle d = fault.getFaultInfo();
            System.out.println("  SOAP Fault -> categoria=" + d.getCategoria()
                + " codigo=" + d.getCodigo() + " mensaje=" + d.getMensaje());
        }

        System.out.println("\n=== RegistrarClasificacion (repetido: mismo clasificador/concepto) ===");
        try {
            RegistrarClasificacionResponse resp3 = port.registrarClasificacion(req2);
            System.out.println("  exito=" + resp3.isExito() + "  mensaje=" + resp3.getMensaje());
        } catch (ErrorDetalleMessage fault) {
            ErrorDetalle d = fault.getFaultInfo();
            System.out.println("  SOAP Fault (parseado por JAX-WS) -> categoria=" + d.getCategoria()
                + " codigo=" + d.getCodigo() + " mensaje=" + d.getMensaje());
        } catch (javax.xml.ws.WebServiceException transporte) {
            // Hallazgo de interoperabilidad (Tarea 4): el servidor responde
            // este caso con HTTP 409 (lo exige el enunciado del ejercicio
            // guiado, "conflicto 409"), pero el runtime JAX-WS RI, siguiendo
            // WS-I Basic Profile a la letra, solo intenta leer un
            // soap:Fault del cuerpo cuando el status es 500 -- con 409
            // lanza esta excepcion de transporte SIN mirar el cuerpo. El
            // cliente manual (soap_client.py) no tiene ese problema porque
            // se escribio sabiendo la convencion real del servidor; un
            // cliente generado y "a ciegas" del WSDL, no.
            System.out.println("  (sin parsear como SOAP Fault -- ver nota de interoperabilidad) " + transporte);
        }

        System.out.println("\n=== Modelo invalido: el propio cliente tipado ya lo rechaza ===");
        // "Blockchain" no es un valor de ModeloServicioType (el enum que
        // wsimport genero a partir del XSD): esto ni siquiera compila con
        // un valor literal invalido, y en tiempo de ejecucion
        // fromValue(...) lanza IllegalArgumentException ANTES de llamar al
        // servidor. Es la prueba en Java de por que un XSD tipado da
        // certeza al contrato (una de las preguntas de reflexion de esta
        // tarea): el error se detecta en el cliente, no como un SOAP Fault
        // del servidor.
        try {
            ModeloServicioType.fromValue("Blockchain");
            System.out.println("  ERROR: no debio aceptar 'Blockchain'");
        } catch (IllegalArgumentException esperado) {
            System.out.println("  Rechazado localmente por el cliente generado: " + esperado);
        }
    }
}
