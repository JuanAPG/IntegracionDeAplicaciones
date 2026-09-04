
package mx.udem.iac.clasificacion.client;

import javax.xml.bind.annotation.XmlAccessType;
import javax.xml.bind.annotation.XmlAccessorType;
import javax.xml.bind.annotation.XmlElement;
import javax.xml.bind.annotation.XmlRootElement;
import javax.xml.bind.annotation.XmlSchemaType;
import javax.xml.bind.annotation.XmlType;


/**
 * <p>Java class for anonymous complex type</p>.
 * 
 * <p>The following schema fragment specifies the expected content contained within this class.</p>
 * 
 * <pre>
 * &lt;complexType&gt;
 *   &lt;complexContent&gt;
 *     &lt;restriction base="{http://www.w3.org/2001/XMLSchema}anyType"&gt;
 *       &lt;sequence&gt;
 *         &lt;element name="clasificador_email" type="{http://www.w3.org/2001/XMLSchema}string"/&gt;
 *         &lt;element name="referencia_libro" type="{http://www.w3.org/2001/XMLSchema}string"/&gt;
 *         &lt;element name="referencia_concepto" type="{http://www.w3.org/2001/XMLSchema}string"/&gt;
 *         &lt;element name="modelo_servicio" type="{urn:library:clasificacion:1.0}ModeloServicioType"/&gt;
 *       &lt;/sequence&gt;
 *     &lt;/restriction&gt;
 *   &lt;/complexContent&gt;
 * &lt;/complexType&gt;
 * </pre>
 * 
 * 
 */
@XmlAccessorType(XmlAccessType.FIELD)
@XmlType(name = "", propOrder = {
    "clasificadorEmail",
    "referenciaLibro",
    "referenciaConcepto",
    "modeloServicio"
})
@XmlRootElement(name = "RegistrarClasificacionRequest")
public class RegistrarClasificacionRequest {

    @XmlElement(name = "clasificador_email", required = true)
    protected String clasificadorEmail;
    @XmlElement(name = "referencia_libro", required = true)
    protected String referenciaLibro;
    @XmlElement(name = "referencia_concepto", required = true)
    protected String referenciaConcepto;
    @XmlElement(name = "modelo_servicio", required = true)
    @XmlSchemaType(name = "string")
    protected ModeloServicioType modeloServicio;

    /**
     * Gets the value of the clasificadorEmail property.
     * 
     * @return
     *     possible object is
     *     {@link String }
     *     
     */
    public String getClasificadorEmail() {
        return clasificadorEmail;
    }

    /**
     * Sets the value of the clasificadorEmail property.
     * 
     * @param value
     *     allowed object is
     *     {@link String }
     *     
     */
    public void setClasificadorEmail(String value) {
        this.clasificadorEmail = value;
    }

    /**
     * Gets the value of the referenciaLibro property.
     * 
     * @return
     *     possible object is
     *     {@link String }
     *     
     */
    public String getReferenciaLibro() {
        return referenciaLibro;
    }

    /**
     * Sets the value of the referenciaLibro property.
     * 
     * @param value
     *     allowed object is
     *     {@link String }
     *     
     */
    public void setReferenciaLibro(String value) {
        this.referenciaLibro = value;
    }

    /**
     * Gets the value of the referenciaConcepto property.
     * 
     * @return
     *     possible object is
     *     {@link String }
     *     
     */
    public String getReferenciaConcepto() {
        return referenciaConcepto;
    }

    /**
     * Sets the value of the referenciaConcepto property.
     * 
     * @param value
     *     allowed object is
     *     {@link String }
     *     
     */
    public void setReferenciaConcepto(String value) {
        this.referenciaConcepto = value;
    }

    /**
     * Gets the value of the modeloServicio property.
     * 
     * @return
     *     possible object is
     *     {@link ModeloServicioType }
     *     
     */
    public ModeloServicioType getModeloServicio() {
        return modeloServicio;
    }

    /**
     * Sets the value of the modeloServicio property.
     * 
     * @param value
     *     allowed object is
     *     {@link ModeloServicioType }
     *     
     */
    public void setModeloServicio(ModeloServicioType value) {
        this.modeloServicio = value;
    }

}
