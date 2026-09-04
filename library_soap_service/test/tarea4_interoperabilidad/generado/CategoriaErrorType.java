
package mx.udem.iac.clasificacion.client;

import javax.xml.bind.annotation.XmlEnum;
import javax.xml.bind.annotation.XmlType;


/**
 * 
 * 
 * <p>Java class for CategoriaErrorType</p>.
 * 
 * <p>The following schema fragment specifies the expected content contained within this class.</p>
 * <pre>
 * &lt;simpleType name="CategoriaErrorType"&gt;
 *   &lt;restriction base="{http://www.w3.org/2001/XMLSchema}string"&gt;
 *     &lt;enumeration value="CLIENTE"/&gt;
 *     &lt;enumeration value="VALIDACION"/&gt;
 *     &lt;enumeration value="CONFLICTO"/&gt;
 *     &lt;enumeration value="AUTENTICACION"/&gt;
 *     &lt;enumeration value="SERVIDOR"/&gt;
 *   &lt;/restriction&gt;
 * &lt;/simpleType&gt;
 * </pre>
 * 
 */
@XmlType(name = "CategoriaErrorType")
@XmlEnum
public enum CategoriaErrorType {

    CLIENTE,
    VALIDACION,
    CONFLICTO,
    AUTENTICACION,
    SERVIDOR;

    public String value() {
        return name();
    }

    public static CategoriaErrorType fromValue(String v) {
        return valueOf(v);
    }

}
