
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
 *         &lt;element name="categoria" type="{urn:library:clasificacion:1.0}CategoriaErrorType"/&gt;
 *         &lt;element name="codigo" type="{http://www.w3.org/2001/XMLSchema}string"/&gt;
 *         &lt;element name="mensaje" type="{http://www.w3.org/2001/XMLSchema}string"/&gt;
 *         &lt;element name="ayuda" type="{http://www.w3.org/2001/XMLSchema}string" minOccurs="0"/&gt;
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
    "categoria",
    "codigo",
    "mensaje",
    "ayuda"
})
@XmlRootElement(name = "ErrorDetalle")
public class ErrorDetalle {

    @XmlElement(required = true)
    @XmlSchemaType(name = "string")
    protected CategoriaErrorType categoria;
    @XmlElement(required = true)
    protected String codigo;
    @XmlElement(required = true)
    protected String mensaje;
    protected String ayuda;

    /**
     * Gets the value of the categoria property.
     * 
     * @return
     *     possible object is
     *     {@link CategoriaErrorType }
     *     
     */
    public CategoriaErrorType getCategoria() {
        return categoria;
    }

    /**
     * Sets the value of the categoria property.
     * 
     * @param value
     *     allowed object is
     *     {@link CategoriaErrorType }
     *     
     */
    public void setCategoria(CategoriaErrorType value) {
        this.categoria = value;
    }

    /**
     * Gets the value of the codigo property.
     * 
     * @return
     *     possible object is
     *     {@link String }
     *     
     */
    public String getCodigo() {
        return codigo;
    }

    /**
     * Sets the value of the codigo property.
     * 
     * @param value
     *     allowed object is
     *     {@link String }
     *     
     */
    public void setCodigo(String value) {
        this.codigo = value;
    }

    /**
     * Gets the value of the mensaje property.
     * 
     * @return
     *     possible object is
     *     {@link String }
     *     
     */
    public String getMensaje() {
        return mensaje;
    }

    /**
     * Sets the value of the mensaje property.
     * 
     * @param value
     *     allowed object is
     *     {@link String }
     *     
     */
    public void setMensaje(String value) {
        this.mensaje = value;
    }

    /**
     * Gets the value of the ayuda property.
     * 
     * @return
     *     possible object is
     *     {@link String }
     *     
     */
    public String getAyuda() {
        return ayuda;
    }

    /**
     * Sets the value of the ayuda property.
     * 
     * @param value
     *     allowed object is
     *     {@link String }
     *     
     */
    public void setAyuda(String value) {
        this.ayuda = value;
    }

}
