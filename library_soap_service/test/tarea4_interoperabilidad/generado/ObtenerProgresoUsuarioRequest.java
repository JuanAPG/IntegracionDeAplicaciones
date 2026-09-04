
package mx.udem.iac.clasificacion.client;

import javax.xml.bind.annotation.XmlAccessType;
import javax.xml.bind.annotation.XmlAccessorType;
import javax.xml.bind.annotation.XmlElement;
import javax.xml.bind.annotation.XmlRootElement;
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
    "clasificadorEmail"
})
@XmlRootElement(name = "ObtenerProgresoUsuarioRequest")
public class ObtenerProgresoUsuarioRequest {

    @XmlElement(name = "clasificador_email", required = true)
    protected String clasificadorEmail;

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

}
