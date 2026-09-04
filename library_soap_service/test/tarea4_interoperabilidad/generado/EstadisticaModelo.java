
package mx.udem.iac.clasificacion.client;

import javax.xml.bind.annotation.XmlAccessType;
import javax.xml.bind.annotation.XmlAccessorType;
import javax.xml.bind.annotation.XmlElement;
import javax.xml.bind.annotation.XmlSchemaType;
import javax.xml.bind.annotation.XmlType;


/**
 * <p>Java class for EstadisticaModelo complex type</p>.
 * 
 * <p>The following schema fragment specifies the expected content contained within this class.</p>
 * 
 * <pre>
 * &lt;complexType name="EstadisticaModelo"&gt;
 *   &lt;complexContent&gt;
 *     &lt;restriction base="{http://www.w3.org/2001/XMLSchema}anyType"&gt;
 *       &lt;sequence&gt;
 *         &lt;element name="modelo_servicio" type="{urn:library:clasificacion:1.0}ModeloServicioType"/&gt;
 *         &lt;element name="total" type="{http://www.w3.org/2001/XMLSchema}int"/&gt;
 *       &lt;/sequence&gt;
 *     &lt;/restriction&gt;
 *   &lt;/complexContent&gt;
 * &lt;/complexType&gt;
 * </pre>
 * 
 * 
 */
@XmlAccessorType(XmlAccessType.FIELD)
@XmlType(name = "EstadisticaModelo", propOrder = {
    "modeloServicio",
    "total"
})
public class EstadisticaModelo {

    @XmlElement(name = "modelo_servicio", required = true)
    @XmlSchemaType(name = "string")
    protected ModeloServicioType modeloServicio;
    protected int total;

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

    /**
     * Gets the value of the total property.
     * 
     */
    public int getTotal() {
        return total;
    }

    /**
     * Sets the value of the total property.
     * 
     */
    public void setTotal(int value) {
        this.total = value;
    }

}
