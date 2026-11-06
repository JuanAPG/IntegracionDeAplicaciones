package mx.udem.library.desktop.service;

import mx.udem.library.desktop.model.UserProfile;
import mx.udem.library.desktop.net.ApiClient;

/**
 * Microservicio de usuarios (5002).
 *
 * NO HAY LECTURAS PUBLICAS AQUI. Ni una. Una lista de cuentas con sus
 * correos son datos personales, de modo que todo exige token.
 *
 * NO EXISTE /users/me -- se comprobo. El perfil propio se pide con el
 * propio id, que sale del claim `user_id` del JWT. Un usuario normal
 * puede leer SU perfil sin ningun permiso; pedir el de otro exige
 * `users:read` y sin el es 403.
 */
public final class UsersService {

    private final ApiClient api;

    public UsersService(ApiClient api) {
        this.api = api;
    }

    public UserProfile perfil(int userId) {
        return UserProfile.de(api.get("/users/" + userId, true));
    }
}
