
package mx.udem.iac.clasificacion.client;

import java.util.ArrayList;
import java.util.List;
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
 *         &lt;element name="estadistica" type="{urn:library:clasificacion:1.0}EstadisticaModelo" maxOccurs="4" minOccurs="4"/&gt;
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
    "estadistica"
})
@XmlRootElement(name = "ObtenerEstadisticasPorModeloResponse")
public class ObtenerEstadisticasPorModeloResponse {

    @XmlElement(required = true)
    protected List<EstadisticaModelo> estadistica;

    /**
     * Gets the value of the estadistica property.
     * 
     * <p>This accessor method returns a reference to the live list,
     * not a snapshot. Therefore any modification you make to the
     * returned list will be present inside the JAXB object.
     * This is why there is not a <CODE>set</CODE> method for the estadistica property.</p>
     * 
     * <p>
     * For example, to add a new item, do as follows:
     * </p>
     * <pre>
     * getEstadistica().add(newItem);
     * </pre>
     * 
     * 
     * <p>
     * Objects of the following type(s) are allowed in the list
     * {@link EstadisticaModelo }
     * </p>
     * 
     * 
     * @return
     *     The value of the estadistica property.
     */
    public List<EstadisticaModelo> getEstadistica() {
        if (estadistica == null) {
            estadistica = new ArrayList<EstadisticaModelo>();
        }
        return this.estadistica;
    }

}
