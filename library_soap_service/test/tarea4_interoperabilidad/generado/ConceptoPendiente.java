
package mx.udem.iac.clasificacion.client;

import javax.xml.bind.annotation.XmlAccessType;
import javax.xml.bind.annotation.XmlAccessorType;
import javax.xml.bind.annotation.XmlElement;
import javax.xml.bind.annotation.XmlType;


/**
 * <p>Java class for ConceptoPendiente complex type</p>.
 * 
 * <p>The following schema fragment specifies the expected content contained within this class.</p>
 * 
 * <pre>
 * &lt;complexType name="ConceptoPendiente"&gt;
 *   &lt;complexContent&gt;
 *     &lt;restriction base="{http://www.w3.org/2001/XMLSchema}anyType"&gt;
 *       &lt;sequence&gt;
 *         &lt;element name="referencia_libro" type="{http://www.w3.org/2001/XMLSchema}string"/&gt;
 *         &lt;element name="referencia_concepto" type="{http://www.w3.org/2001/XMLSchema}string"/&gt;
 *         &lt;element name="titulo_libro" type="{http://www.w3.org/2001/XMLSchema}string"/&gt;
 *         &lt;element name="nombre_categoria" type="{http://www.w3.org/2001/XMLSchema}string"/&gt;
 *         &lt;element name="nombre_concepto" type="{http://www.w3.org/2001/XMLSchema}string"/&gt;
 *       &lt;/sequence&gt;
 *     &lt;/restriction&gt;
 *   &lt;/complexContent&gt;
 * &lt;/complexType&gt;
 * </pre>
 * 
 * 
 */
@XmlAccessorType(XmlAccessType.FIELD)
@XmlType(name = "ConceptoPendiente", propOrder = {
    "referenciaLibro",
    "referenciaConcepto",
    "tituloLibro",
    "nombreCategoria",
    "nombreConcepto"
})
public class ConceptoPendiente {

    @XmlElement(name = "referencia_libro", required = true)
    protected String referenciaLibro;
    @XmlElement(name = "referencia_concepto", required = true)
    protected String referenciaConcepto;
    @XmlElement(name = "titulo_libro", required = true)
    protected String tituloLibro;
    @XmlElement(name = "nombre_categoria", required = true)
    protected String nombreCategoria;
    @XmlElement(name = "nombre_concepto", required = true)
    protected String nombreConcepto;

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
     * Gets the value of the tituloLibro property.
     * 
     * @return
     *     possible object is
     *     {@link String }
     *     
     */
    public String getTituloLibro() {
        return tituloLibro;
    }

    /**
     * Sets the value of the tituloLibro property.
     * 
     * @param value
     *     allowed object is
     *     {@link String }
     *     
     */
    public void setTituloLibro(String value) {
        this.tituloLibro = value;
    }

    /**
     * Gets the value of the nombreCategoria property.
     * 
     * @return
     *     possible object is
     *     {@link String }
     *     
     */
    public String getNombreCategoria() {
        return nombreCategoria;
    }

    /**
     * Sets the value of the nombreCategoria property.
     * 
     * @param value
     *     allowed object is
     *     {@link String }
     *     
     */
    public void setNombreCategoria(String value) {
        this.nombreCategoria = value;
    }

    /**
     * Gets the value of the nombreConcepto property.
     * 
     * @return
     *     possible object is
     *     {@link String }
     *     
     */
    public String getNombreConcepto() {
        return nombreConcepto;
    }

    /**
     * Sets the value of the nombreConcepto property.
     * 
     * @param value
     *     allowed object is
     *     {@link String }
     *     
     */
    public void setNombreConcepto(String value) {
        this.nombreConcepto = value;
    }

}
