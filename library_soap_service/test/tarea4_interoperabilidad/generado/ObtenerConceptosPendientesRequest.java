
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
 *         &lt;element name="limite" type="{http://www.w3.org/2001/XMLSchema}int"/&gt;
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
    "limite"
})
@XmlRootElement(name = "ObtenerConceptosPendientesRequest")
public class ObtenerConceptosPendientesRequest {

    @XmlElement(name = "clasificador_email", required = true)
    protected String clasificadorEmail;
    protected int limite;

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
     * Gets the value of the limite property.
     * 
     */
    public int getLimite() {
        return limite;
    }

    /**
     * Sets the value of the limite property.
     * 
     */
    public void setLimite(int value) {
        this.limite = value;
    }

}
