
package mx.udem.iac.clasificacion.client;

import javax.xml.bind.annotation.XmlEnum;
import javax.xml.bind.annotation.XmlEnumValue;
import javax.xml.bind.annotation.XmlType;


/**
 * 
 * 
 * <p>Java class for ModeloServicioType</p>.
 * 
 * <p>The following schema fragment specifies the expected content contained within this class.</p>
 * <pre>
 * &lt;simpleType name="ModeloServicioType"&gt;
 *   &lt;restriction base="{http://www.w3.org/2001/XMLSchema}string"&gt;
 *     &lt;enumeration value="IaaS"/&gt;
 *     &lt;enumeration value="PaaS"/&gt;
 *     &lt;enumeration value="SaaS"/&gt;
 *     &lt;enumeration value="FaaS"/&gt;
 *     &lt;enumeration value="N/A"/&gt;
 *   &lt;/restriction&gt;
 * &lt;/simpleType&gt;
 * </pre>
 * 
 */
@XmlType(name = "ModeloServicioType")
@XmlEnum
public enum ModeloServicioType {

    @XmlEnumValue("IaaS")
    IAA_S("IaaS"),
    @XmlEnumValue("PaaS")
    PAA_S("PaaS"),
    @XmlEnumValue("SaaS")
    SAA_S("SaaS"),
    @XmlEnumValue("FaaS")
    FAA_S("FaaS"),
    @XmlEnumValue("N/A")
    N_A("N/A");
    private final String value;

    ModeloServicioType(String v) {
        value = v;
    }

    /**
     * Gets the value associated to the enum constant.
     * 
     * @return
     *     The value linked to the enum.
     */
    public String value() {
        return value;
    }

    /**
     * Gets the enum associated to the value passed as parameter.
     * 
     * @param v
     *     The value to get the enum from.
     * @return
     *     The enum which corresponds to the value, if it exists.
     * @throws IllegalArgumentException
     *     If no value matches in the enum declaration.
     */
    public static ModeloServicioType fromValue(String v) {
        for (ModeloServicioType c: ModeloServicioType.values()) {
            if (c.value.equals(v)) {
                return c;
            }
        }
        throw new IllegalArgumentException(v);
    }

}
