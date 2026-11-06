package mx.udem.library.desktop.model;

import com.fasterxml.jackson.databind.JsonNode;

/**
 * El perfil del usuario autenticado, de GET /users/&lt;id&gt; (5002).
 *
 * NO EXISTE /users/me: se comprobo. El id sale del claim `user_id` del
 * JWT, o del objeto `user` que devolvio el login. Un usuario normal puede
 * consultar SU PROPIO perfil sin ningun permiso especial; pedir el de
 * otro exige `users:read` y, sin el, es 403.
 *
 * Los nombres de campo mezclan espanol e ingles porque asi los emite el
 * servicio (`nombre`, `apellidoPaterno`, `fullName`, `emailVerified`).
 * Se respetan en lugar de normalizarlos: el dia que haya que compararlo
 * con la respuesta cruda, cuadran.
 */
public record UserProfile(
        int id,
        String nombre,
        String apellidoPaterno,
        String apellidoMaterno,
        String fullName,
        String email,
        String role,
        int roleId,
        boolean emailVerified,
        boolean isActive,
        String createdAt,
        String lastLoginAt) {

    public static UserProfile de(JsonNode nodo) {
        return new UserProfile(
                nodo.path("id").asInt(0),
                nodo.path("nombre").asText(""),
                nodo.path("apellidoPaterno").asText(""),
                nodo.path("apellidoMaterno").asText(""),
                nodo.path("fullName").asText(""),
                nodo.path("email").asText(""),
                nodo.path("role").asText(""),
                nodo.path("roleId").asInt(0),
                nodo.path("emailVerified").asBoolean(false),
                nodo.path("isActive").asBoolean(false),
                nodo.path("createdAt").asText(""),
                nodo.path("lastLoginAt").asText(""));
    }

    public String nombreVisible() {
        return fullName == null || fullName.isBlank() ? email : fullName;
    }
}
