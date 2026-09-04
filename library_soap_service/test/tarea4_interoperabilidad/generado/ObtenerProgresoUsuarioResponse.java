
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
 *         &lt;element name="total_clasificados" type="{http://www.w3.org/2001/XMLSchema}int"/&gt;
 *         &lt;element name="total_pendientes" type="{http://www.w3.org/2001/XMLSchema}int"/&gt;
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
    "totalClasificados",
    "totalPendientes"
})
@XmlRootElement(name = "ObtenerProgresoUsuarioResponse")
public class ObtenerProgresoUsuarioResponse {

    @XmlElement(name = "total_clasificados")
    protected int totalClasificados;
    @XmlElement(name = "total_pendientes")
    protected int totalPendientes;

    /**
     * Gets the value of the totalClasificados property.
     * 
     */
    public int getTotalClasificados() {
        return totalClasificados;
    }

    /**
     * Sets the value of the totalClasificados property.
     * 
     */
    public void setTotalClasificados(int value) {
        this.totalClasificados = value;
    }

    /**
     * Gets the value of the totalPendientes property.
     * 
     */
    public int getTotalPendientes() {
        return totalPendientes;
    }

    /**
     * Sets the value of the totalPendientes property.
     * 
     */
    public void setTotalPendientes(int value) {
        this.totalPendientes = value;
    }

}
