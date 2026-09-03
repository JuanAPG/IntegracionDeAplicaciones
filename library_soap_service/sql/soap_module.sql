-- =====================================================================
-- library_soap_service/sql/soap_module.sql
-- Estructura (DDL) propia del microservicio SOAP.
--
-- Extiende library_db con las tablas que necesita el modulo SOAP para
-- registrar quien clasifica, que clasifico un modelo Cloud y que clientes
-- de escritorio consumen el servicio. NO se modifica ninguna tabla del
-- monolito (db/01_schema.sql): solo se referencian library.books(isbn) y
-- library.concepts(id), ambas ya UNIQUE/PK, sin tocar su definicion.
--
-- Requisito previo: db/01_schema.sql ya aplicado (existen library.books
-- y library.concepts).
-- =====================================================================

SET search_path TO library, public;


-- =====================================================================
-- CLASIFICADORES
-- Identidad minima del usuario (persona o proceso) que opera un cliente
-- SOAP y envia clasificaciones. "codigo" es el identificador estable que
-- el cliente presenta en cada peticion (p. ej. usuario o llave de
-- integracion); no se guardan credenciales aqui, eso es resorte de la
-- capa de autenticacion, no del modelo de datos.
-- =====================================================================
CREATE TABLE IF NOT EXISTS library.clasificadores (
    id          SERIAL PRIMARY KEY,
    codigo      VARCHAR(50)   NOT NULL UNIQUE,
    nombre      VARCHAR(150)  NOT NULL,
    email       VARCHAR(150),
    activo      BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT ck_clasificadores_codigo_no_vacio CHECK (length(btrim(codigo)) > 0),
    CONSTRAINT ck_clasificadores_nombre_no_vacio CHECK (length(btrim(nombre)) > 0),
    CONSTRAINT ck_clasificadores_email_formato
        CHECK (email IS NULL OR email ~* '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$')
);

-- Consultas de mantenimiento filtran habitualmente por clasificadores
-- activos; UNIQUE(codigo) ya cubre la busqueda por identidad exacta.
CREATE INDEX IF NOT EXISTS ix_clasificadores_activo ON library.clasificadores (activo);


-- =====================================================================
-- CLASIFICACIONES_CLOUD
-- Una fila = "el clasificador X registro, via un modelo Cloud, que el
-- concepto C aplica al libro L". libro_isbn referencia books.isbn (UNIQUE
-- en el monolito) en vez de books.id porque el ISBN es la clave natural
-- que ya maneja el cliente SOAP (ver books_repository.py); usar el mismo
-- valor evita una vuelta extra a /api/books solo para resolver el id
-- interno.
--
-- fecha_clasificacion: momento en que el modelo Cloud produjo el
-- resultado (lo declara el cliente). creado_en/registrado_por: datos de
-- auditoria de cuando y con que rol quedo insertada la fila en esta base,
-- generados siempre por el servidor y nunca por el cliente.
--
-- Restriccion pedida: un mismo clasificador no puede registrar dos veces
-- el mismo concepto -> UNIQUE (clasificador_id, concepto_id).
-- =====================================================================
CREATE TABLE IF NOT EXISTS library.clasificaciones_cloud (
    id                    BIGSERIAL     PRIMARY KEY,
    concepto_id           INTEGER       NOT NULL REFERENCES library.concepts(id)
                                         ON DELETE CASCADE,
    libro_isbn            VARCHAR(20)   NOT NULL REFERENCES library.books(isbn)
                                         ON UPDATE CASCADE ON DELETE CASCADE,
    clasificador_id       INTEGER       NOT NULL REFERENCES library.clasificadores(id)
                                         ON DELETE CASCADE,
    modelo_cloud          VARCHAR(100)  NOT NULL,
    fecha_clasificacion   TIMESTAMPTZ   NOT NULL DEFAULT now(),
    registrado_por        TEXT          NOT NULL DEFAULT current_user,
    creado_en             TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT ck_clasificaciones_cloud_modelo_no_vacio CHECK (length(btrim(modelo_cloud)) > 0),
    -- Mismo catalogo cerrado que valida el WSDL (ModeloServicioType) y la
    -- capa Flask: se repite aqui como ultima linea de defensa, para que
    -- ningun cliente que hable directo con la base pueda colar un valor
    -- fuera de catalogo.
    CONSTRAINT ck_clasificaciones_cloud_modelo_permitido
        CHECK (modelo_cloud IN ('IaaS', 'PaaS', 'SaaS', 'FaaS', 'N/A')),
    CONSTRAINT ux_clasificaciones_cloud_clasificador_concepto UNIQUE (clasificador_id, concepto_id)
);

CREATE INDEX IF NOT EXISTS ix_clasificaciones_cloud_concepto  ON library.clasificaciones_cloud (concepto_id);
CREATE INDEX IF NOT EXISTS ix_clasificaciones_cloud_libro     ON library.clasificaciones_cloud (libro_isbn);
CREATE INDEX IF NOT EXISTS ix_clasificaciones_cloud_fecha     ON library.clasificaciones_cloud (fecha_clasificacion DESC);


-- =====================================================================
-- CLIENTES_SERVIDOS
-- Un cliente de escritorio de clasificacion se identifica por su tipo
-- (p. ej. la plataforma/app: "JavaFX-Clasificador", "WinForms-Cloud") y
-- un identificador propio de la instancia (host, MAC, GUID de
-- instalacion...). UNIQUE(tipo_cliente, identificador) evita filas
-- duplicadas para la misma instancia; peticiones_atendidas es un
-- contador que el servicio incrementa en cada llamada SOAP.
-- =====================================================================
CREATE TABLE IF NOT EXISTS library.clientes_servidos (
    id                    SERIAL        PRIMARY KEY,
    tipo_cliente          VARCHAR(50)   NOT NULL,
    identificador         VARCHAR(100)  NOT NULL,
    peticiones_atendidas  INTEGER       NOT NULL DEFAULT 0,
    primer_contacto_en    TIMESTAMPTZ   NOT NULL DEFAULT now(),
    ultima_peticion_en    TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT ck_clientes_servidos_tipo_no_vacio CHECK (length(btrim(tipo_cliente)) > 0),
    CONSTRAINT ck_clientes_servidos_identificador_no_vacio CHECK (length(btrim(identificador)) > 0),
    CONSTRAINT ck_clientes_servidos_peticiones_no_negativas CHECK (peticiones_atendidas >= 0),
    CONSTRAINT ux_clientes_servidos_tipo_identificador UNIQUE (tipo_cliente, identificador)
);

CREATE INDEX IF NOT EXISTS ix_clientes_servidos_tipo    ON library.clientes_servidos (tipo_cliente);
CREATE INDEX IF NOT EXISTS ix_clientes_servidos_ultima  ON library.clientes_servidos (ultima_peticion_en DESC);


-- =====================================================================
-- VISTA: v_conceptos_catalogo
--
-- Modelo de lectura para ObtenerConceptosPendientes: reune, sin tocar el
-- esquema del monolito, cada par (libro, concepto) con el dato que la
-- app de escritorio necesita mostrar. Mismo criterio que
-- db/06_views.sql: el modelo normalizado (book_concepts + concepts +
-- books + categories) sigue siendo la verdad; la vista es la forma
-- comoda de leerlo, y evita repetir el JOIN en cada funcion de este
-- archivo.
--
-- concepto_id viaja en la vista para poder filtrar contra
-- clasificaciones_cloud; el contrato SOAP no lo expone (usa
-- referencia_concepto, el nombre, que es la clave logica/UNIQUE).
-- =====================================================================
CREATE OR REPLACE VIEW library.v_conceptos_catalogo AS
SELECT bk.concept_id AS concepto_id,
       b.isbn         AS referencia_libro,
       k.name         AS referencia_concepto,
       b.title        AS titulo_libro,
       cat.name       AS nombre_categoria,
       k.name         AS nombre_concepto
  FROM library.book_concepts bk
  JOIN library.books      b   ON b.id = bk.book_id
  JOIN library.categories cat ON cat.id = b.category_id
  JOIN library.concepts   k   ON k.id = bk.concept_id;


-- =====================================================================
-- FUNCIONES Y PROCEDIMIENTOS ALMACENADOS
--
-- Igual que en db/04_stored_procedures.sql: todas reciben sus datos por
-- PARAMETRO (nunca se arma una sentencia concatenando texto del
-- cliente), y las que escriben en mas de una tabla en la misma llamada
-- son atomicas -- el motor garantiza la atomicidad, no el orden en que
-- soap_endpoint.py/clasificacion_repository.py llamen a la base.
--
-- SECURITY INVOKER (el valor por defecto): corren con los privilegios
-- de quien llama, no con los del creador de la funcion.
-- =====================================================================

-- ---------------------------------------------------------------------
-- fn_get_or_create_clasificador
-- "Buscar o crear" atomico por email. El WSDL no define una operacion
-- de alta de clasificador aparte: el primer contacto de un email lo da
-- de alta. clasificadores.codigo es la columna UNIQUE NOT NULL de la
-- tabla (email se dejo abierta para no forzar unicidad de un dato de
-- contacto), asi que se usa el propio email como codigo; el INSERT ...
-- ON CONFLICT (codigo) resuelve todo en una sola sentencia, sin la
-- condicion de carrera de un SELECT seguido de un INSERT separados.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION library.fn_get_or_create_clasificador(
    p_email VARCHAR
) RETURNS INTEGER
LANGUAGE plpgsql AS $$
DECLARE
    v_id INTEGER;
BEGIN
    INSERT INTO library.clasificadores (codigo, nombre, email)
    VALUES (p_email, split_part(p_email, '@', 1), p_email)
    ON CONFLICT (codigo) DO UPDATE SET codigo = library.clasificadores.codigo
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;


-- ---------------------------------------------------------------------
-- sp_conceptos_pendientes
-- Backend de ObtenerConceptosPendientes: conceptos de v_conceptos_catalogo
-- que el clasificador (resuelto/alta por email) todavia no registro en
-- clasificaciones_cloud. La restriccion UNIQUE (clasificador_id,
-- concepto_id) de esa tabla es sobre el concepto solo, no sobre el par
-- libro-concepto: en cuanto un concepto queda clasificado desaparece de
-- este listado para todos los libros donde aparezca.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION library.sp_conceptos_pendientes(
    p_clasificador_email VARCHAR,
    p_limite             INTEGER DEFAULT 10
) RETURNS TABLE (
    referencia_libro    VARCHAR,
    referencia_concepto VARCHAR,
    titulo_libro        VARCHAR,
    nombre_categoria    VARCHAR,
    nombre_concepto     VARCHAR
)
LANGUAGE plpgsql AS $$
DECLARE
    v_clasificador_id INTEGER;
BEGIN
    v_clasificador_id := library.fn_get_or_create_clasificador(p_clasificador_email);

    RETURN QUERY
    SELECT v.referencia_libro, v.referencia_concepto, v.titulo_libro,
           v.nombre_categoria, v.nombre_concepto
      FROM library.v_conceptos_catalogo v
     WHERE v.concepto_id NOT IN (
               SELECT cc.concepto_id FROM library.clasificaciones_cloud cc
                WHERE cc.clasificador_id = v_clasificador_id
           )
     ORDER BY v.nombre_concepto, v.titulo_libro
     LIMIT p_limite;
END;
$$;


-- ---------------------------------------------------------------------
-- sp_registrar_clasificacion
-- Backend de RegistrarClasificacion. Puede escribir en DOS tablas
-- (clasificadores, si el email es nuevo, y clasificaciones_cloud) en
-- una sola llamada atomica.
--
-- El bloque BEGIN/EXCEPTION interno crea un SAVEPOINT implicito
-- alrededor del INSERT final: si choca con la restriccion UNIQUE
-- (clasificador_id, concepto_id), PostgreSQL deshace SOLO esa
-- subtransaccion -- el alta del clasificador hecha arriba, si ocurrio,
-- permanece -- y la funcion sigue con exito=false en vez de abortar
-- toda la transaccion que abrio el cliente. Un error que SI deba
-- deshacer la llamada completa (por ejemplo, que la base se caiga a la
-- mitad) no lo captura este bloque: sube sin manejar y la transaccion
-- del cliente (db.cursor(commit=True) en clasificacion_repository.py)
-- hace ROLLBACK completo, como con cualquier excepcion no controlada.
--
-- modelo_servicio invalido y libro/concepto inexistente se resuelven
-- ANTES del INSERT, para no gastar un intento contra una restriccion
-- que ya se sabe que va a fallar.
--
-- codigo_error identifica la causa cuando exito=FALSE (NULL cuando
-- exito=TRUE), para que la capa Python traduzca cada caso al tipo de
-- SOAP Fault correcto sin tener que interpretar el texto de mensaje:
--   MODELO_INVALIDO, LIBRO_INEXISTENTE, CONCEPTO_INEXISTENTE, DUPLICADO
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION library.sp_registrar_clasificacion(
    p_clasificador_email VARCHAR,
    p_isbn               VARCHAR,
    p_concepto_nombre    VARCHAR,
    p_modelo_servicio    VARCHAR
) RETURNS TABLE (exito BOOLEAN, mensaje TEXT, codigo_error TEXT)
LANGUAGE plpgsql AS $$
DECLARE
    v_clasificador_id INTEGER;
    v_concepto_id     INTEGER;
BEGIN
    IF p_modelo_servicio NOT IN ('IaaS', 'PaaS', 'SaaS', 'FaaS', 'N/A') THEN
        RETURN QUERY SELECT FALSE, format(
            'El modelo de servicio ''%s'' no es valido. '
            'Valores permitidos: IaaS, PaaS, SaaS, FaaS, N/A.', p_modelo_servicio),
            'MODELO_INVALIDO'::TEXT;
        RETURN;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM library.books WHERE isbn = p_isbn) THEN
        RETURN QUERY SELECT FALSE, format('No existe un libro con ISBN ''%s''.', p_isbn),
            'LIBRO_INEXISTENTE'::TEXT;
        RETURN;
    END IF;

    SELECT id INTO v_concepto_id FROM library.concepts WHERE name = p_concepto_nombre;
    IF v_concepto_id IS NULL THEN
        RETURN QUERY SELECT FALSE, format('No existe el concepto ''%s''.', p_concepto_nombre),
            'CONCEPTO_INEXISTENTE'::TEXT;
        RETURN;
    END IF;

    v_clasificador_id := library.fn_get_or_create_clasificador(p_clasificador_email);

    BEGIN
        INSERT INTO library.clasificaciones_cloud
            (concepto_id, libro_isbn, clasificador_id, modelo_cloud)
        VALUES (v_concepto_id, p_isbn, v_clasificador_id, p_modelo_servicio);

        RETURN QUERY SELECT TRUE, 'Clasificacion guardada exitosamente.'::TEXT, NULL::TEXT;
    EXCEPTION
        WHEN unique_violation THEN
            RETURN QUERY SELECT FALSE, format(
                'El clasificador ''%s'' ya habia registrado el concepto ''%s''.',
                p_clasificador_email, p_concepto_nombre),
                'DUPLICADO'::TEXT;
    END;
END;
$$;


-- ---------------------------------------------------------------------
-- sp_progreso_usuario
-- Backend de ObtenerProgresoUsuario: cuantos conceptos clasifico ya el
-- clasificador y cuantos le quedan (misma definicion de "pendiente" que
-- sp_conceptos_pendientes, sobre v_conceptos_catalogo).
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION library.sp_progreso_usuario(
    p_clasificador_email VARCHAR
) RETURNS TABLE (
    total_clasificados INTEGER,
    total_pendientes   INTEGER
)
LANGUAGE plpgsql AS $$
DECLARE
    v_clasificador_id INTEGER;
BEGIN
    v_clasificador_id := library.fn_get_or_create_clasificador(p_clasificador_email);

    RETURN QUERY
    SELECT
        (SELECT count(*)::INTEGER
           FROM library.clasificaciones_cloud
          WHERE clasificador_id = v_clasificador_id),
        (SELECT count(DISTINCT v.concepto_id)::INTEGER
           FROM library.v_conceptos_catalogo v
          WHERE v.concepto_id NOT IN (
                    SELECT cc.concepto_id FROM library.clasificaciones_cloud cc
                     WHERE cc.clasificador_id = v_clasificador_id
                ));
END;
$$;


-- ---------------------------------------------------------------------
-- sp_registrar_cliente_servido
-- Bitacora de que cliente de escritorio hizo la peticion (viaja en un
-- encabezado SOAP opcional, ver soap_endpoint.py). Upsert de una sola
-- tabla: no necesita bloque de excepcion propio, el UNIQUE
-- (tipo_cliente, identificador) ya resuelve "alta o incremento" via
-- ON CONFLICT.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION library.sp_registrar_cliente_servido(
    p_tipo_cliente  VARCHAR,
    p_identificador VARCHAR
) RETURNS VOID
LANGUAGE sql AS $$
    INSERT INTO library.clientes_servidos (tipo_cliente, identificador, peticiones_atendidas)
    VALUES (p_tipo_cliente, p_identificador, 1)
    ON CONFLICT (tipo_cliente, identificador) DO UPDATE
        SET peticiones_atendidas = library.clientes_servidos.peticiones_atendidas + 1,
            ultima_peticion_en = now();
$$;
