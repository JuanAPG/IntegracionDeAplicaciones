
package mx.udem.iac.clasificacion.client;

import javax.xml.bind.annotation.XmlRegistry;


/**
 * This object contains factory methods for each 
 * Java content interface and Java element interface 
 * generated in the mx.udem.iac.clasificacion.client package. 
 * <p>An ObjectFactory allows you to programatically 
 * construct new instances of the Java representation 
 * for XML content. The Java representation of XML 
 * content can consist of schema derived interfaces 
 * and classes representing the binding of schema 
 * type definitions, element declarations and model 
 * groups.  Factory methods for each of these are 
 * provided in this class.
 * 
 */
@XmlRegistry
public class ObjectFactory {


    /**
     * Create a new ObjectFactory that can be used to create new instances of schema derived classes for package: mx.udem.iac.clasificacion.client
     * 
     */
    public ObjectFactory() {
    }

    /**
     * Create an instance of {@link ObtenerConceptosPendientesRequest }
     * 
     */
    public ObtenerConceptosPendientesRequest createObtenerConceptosPendientesRequest() {
        return new ObtenerConceptosPendientesRequest();
    }

    /**
     * Create an instance of {@link ObtenerConceptosPendientesResponse }
     * 
     */
    public ObtenerConceptosPendientesResponse createObtenerConceptosPendientesResponse() {
        return new ObtenerConceptosPendientesResponse();
    }

    /**
     * Create an instance of {@link ConceptoPendiente }
     * 
     */
    public ConceptoPendiente createConceptoPendiente() {
        return new ConceptoPendiente();
    }

    /**
     * Create an instance of {@link RegistrarClasificacionRequest }
     * 
     */
    public RegistrarClasificacionRequest createRegistrarClasificacionRequest() {
        return new RegistrarClasificacionRequest();
    }

    /**
     * Create an instance of {@link RegistrarClasificacionResponse }
     * 
     */
    public RegistrarClasificacionResponse createRegistrarClasificacionResponse() {
        return new RegistrarClasificacionResponse();
    }

    /**
     * Create an instance of {@link ObtenerProgresoUsuarioRequest }
     * 
     */
    public ObtenerProgresoUsuarioRequest createObtenerProgresoUsuarioRequest() {
        return new ObtenerProgresoUsuarioRequest();
    }

    /**
     * Create an instance of {@link ObtenerProgresoUsuarioResponse }
     * 
     */
    public ObtenerProgresoUsuarioResponse createObtenerProgresoUsuarioResponse() {
        return new ObtenerProgresoUsuarioResponse();
    }

    /**
     * Create an instance of {@link ObtenerEstadisticasPorModeloRequest }
     * 
     */
    public ObtenerEstadisticasPorModeloRequest createObtenerEstadisticasPorModeloRequest() {
        return new ObtenerEstadisticasPorModeloRequest();
    }

    /**
     * Create an instance of {@link ObtenerEstadisticasPorModeloResponse }
     * 
     */
    public ObtenerEstadisticasPorModeloResponse createObtenerEstadisticasPorModeloResponse() {
        return new ObtenerEstadisticasPorModeloResponse();
    }

    /**
     * Create an instance of {@link EstadisticaModelo }
     * 
     */
    public EstadisticaModelo createEstadisticaModelo() {
        return new EstadisticaModelo();
    }

    /**
     * Create an instance of {@link ErrorDetalle }
     * 
     */
    public ErrorDetalle createErrorDetalle() {
        return new ErrorDetalle();
    }

}
