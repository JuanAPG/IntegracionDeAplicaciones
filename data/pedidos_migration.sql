-- =====================================================================
-- data/pedidos_migration.sql
-- MIGRACION del microservicio de PEDIDOS (apps/services/pedidos).
-- Una migracion por archivo, junto al esquema inicial.
--
-- EL STOCK NO SE DUPLICA
--   library.books.stock ya existe desde data/schema.sql y el
--   microservicio de libros ya lo expone y lo filtra
--   (stock_min/stock_max/in_stock). Este modulo NO crea una tabla de
--   inventario paralela: reserva y devuelve unidades sobre books.stock,
--   dentro de la MISMA transaccion que escribe las lineas del pedido.
--   Dos tablas de stock serian dos verdades.
--
-- DISENO
--   * orders               cabecera del pedido (dueno, estado, importes, envio)
--   * order_lines          linea ->> pedido: un pedido tiene muchas lineas.
--                          El precio se CONGELA al momento de la compra
--                          (unit_price), porque books.price puede cambiar
--                          despues y un pedido historico no debe mutar.
--   * order_status_history bitacora de cambios de estado: quien, cuando,
--                          de que a que. Es lo que hace auditable un
--                          pedido y lo que alimenta el rastreo publico.
--
-- MAQUINA DE ESTADOS (la impone un disparador, no la aplicacion)
--   pendiente -> pagado | cancelado
--   pagado    -> enviado | cancelado
--   enviado   -> entregado
--   entregado -> (final)
--   cancelado -> (final)
--
-- Aplicacion en la instancia (idempotente):
--   psql -U library_user -d library_db -f data/pedidos_migration.sql
-- =====================================================================

SET search_path TO library, public;

-- ---------------------------------------------------------------------
-- 1. Estados
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t
                     JOIN pg_namespace n ON n.oid = t.typnamespace
                    WHERE t.typname = 'order_status' AND n.nspname = 'library') THEN
        CREATE TYPE library.order_status AS ENUM
            ('pendiente', 'pagado', 'enviado', 'entregado', 'cancelado');
    END IF;
END
$$;

-- ---------------------------------------------------------------------
-- 2. Numero de pedido legible (PED-000001)
-- ---------------------------------------------------------------------
CREATE SEQUENCE IF NOT EXISTS library.order_number_seq START 1;

CREATE OR REPLACE FUNCTION library.fn_next_order_number()
RETURNS TEXT AS $$
    SELECT 'PED-' || lpad(nextval('library.order_number_seq')::text, 6, '0');
$$ LANGUAGE sql VOLATILE;

-- ---------------------------------------------------------------------
-- 3. Cabecera del pedido
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS library.orders (
    id              BIGSERIAL PRIMARY KEY,
    order_number    VARCHAR(20)   NOT NULL UNIQUE
                                  DEFAULT library.fn_next_order_number(),
    user_id         INTEGER       NOT NULL REFERENCES library.users(id)
                                  ON UPDATE CASCADE ON DELETE RESTRICT,
    status          library.order_status NOT NULL DEFAULT 'pendiente',
    currency        CHAR(3)       NOT NULL DEFAULT 'MXN',

    -- Importes. subtotal y total los recalcula un disparador a partir de
    -- las lineas: la aplicacion no puede mentir sobre el total.
    subtotal        NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (subtotal >= 0),
    shipping_cost   NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (shipping_cost >= 0),
    total           NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (total >= 0),

    -- Envio: lo unico de un pedido que se publica sin token, para que un
    -- tercero pueda manejar su logistica (ver v_order_tracking).
    carrier         VARCHAR(60),
    tracking_code   VARCHAR(60),
    shipping_address TEXT,

    notes           TEXT,
    placed_at       TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    paid_at         TIMESTAMPTZ,
    shipped_at      TIMESTAMPTZ,
    delivered_at    TIMESTAMPTZ,
    cancelled_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_orders_user      ON library.orders (user_id);
CREATE INDEX IF NOT EXISTS ix_orders_status    ON library.orders (status);
CREATE INDEX IF NOT EXISTS ix_orders_placed_at ON library.orders (placed_at DESC);
-- El rastreo publico busca por codigo de guia: indice parcial, porque
-- solo los pedidos ya enviados lo tienen.
CREATE INDEX IF NOT EXISTS ix_orders_tracking
    ON library.orders (tracking_code) WHERE tracking_code IS NOT NULL;

-- ---------------------------------------------------------------------
-- 4. Lineas del pedido  (pedido ->> linea)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS library.order_lines (
    id          BIGSERIAL PRIMARY KEY,
    order_id    BIGINT        NOT NULL REFERENCES library.orders(id) ON DELETE CASCADE,
    book_id     INTEGER       NOT NULL REFERENCES library.books(id)
                              ON UPDATE CASCADE ON DELETE RESTRICT,
    quantity    INTEGER       NOT NULL CHECK (quantity > 0),
    -- Precio congelado: books.price puede cambiar manana.
    unit_price  NUMERIC(10,2) NOT NULL CHECK (unit_price >= 0),
    line_total  NUMERIC(12,2) GENERATED ALWAYS AS (quantity * unit_price) STORED,
    -- Titulo e ISBN congelados tambien: si el libro se renombra, el
    -- pedido historico sigue diciendo que se compro.
    book_title  VARCHAR(255)  NOT NULL,
    book_isbn   VARCHAR(20)   NOT NULL,
    created_at  TIMESTAMPTZ   NOT NULL DEFAULT now(),
    -- Un libro aparece una sola vez por pedido: se acumula en quantity.
    UNIQUE (order_id, book_id)
);

CREATE INDEX IF NOT EXISTS ix_order_lines_order ON library.order_lines (order_id);
CREATE INDEX IF NOT EXISTS ix_order_lines_book  ON library.order_lines (book_id);

-- ---------------------------------------------------------------------
-- 5. Bitacora de estados
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS library.order_status_history (
    id          BIGSERIAL PRIMARY KEY,
    order_id    BIGINT      NOT NULL REFERENCES library.orders(id) ON DELETE CASCADE,
    from_status library.order_status,
    to_status   library.order_status NOT NULL,
    changed_by  INTEGER     REFERENCES library.users(id) ON DELETE SET NULL,
    note        VARCHAR(300),
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_order_history_order
    ON library.order_status_history (order_id, changed_at DESC);

-- ---------------------------------------------------------------------
-- 6. Disparadores
-- ---------------------------------------------------------------------
-- 6.1 updated_at
CREATE OR REPLACE FUNCTION library.trg_orders_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_orders_updated_at ON library.orders;
CREATE TRIGGER trg_orders_updated_at
    BEFORE UPDATE ON library.orders
    FOR EACH ROW EXECUTE FUNCTION library.trg_orders_updated_at();

-- 6.2 Importes derivados de las lineas: la cabecera nunca se escribe a mano.
CREATE OR REPLACE FUNCTION library.trg_order_lines_totals()
RETURNS TRIGGER AS $$
DECLARE
    v_order BIGINT := COALESCE(NEW.order_id, OLD.order_id);
BEGIN
    UPDATE library.orders o
       SET subtotal = COALESCE((SELECT sum(line_total) FROM library.order_lines
                                 WHERE order_id = v_order), 0),
           total    = COALESCE((SELECT sum(line_total) FROM library.order_lines
                                 WHERE order_id = v_order), 0) + o.shipping_cost
     WHERE o.id = v_order;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_order_lines_totals ON library.order_lines;
CREATE TRIGGER trg_order_lines_totals
    AFTER INSERT OR UPDATE OR DELETE ON library.order_lines
    FOR EACH ROW EXECUTE FUNCTION library.trg_order_lines_totals();

-- 6.3 Maquina de estados y sellos de tiempo.
--     La regla vive en la base: ningun cliente (ni un microservicio con
--     un error) puede dejar un pedido en un estado imposible.
CREATE OR REPLACE FUNCTION library.trg_orders_status_guard()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status IS NOT DISTINCT FROM OLD.status THEN
        RETURN NEW;
    END IF;

    -- Transiciones permitidas, escritas tal cual para que la regla se lea
    -- de un vistazo. 'entregado' y 'cancelado' son finales: ninguna rama
    -- sale de ellos.
    IF NOT (
           (OLD.status = 'pendiente' AND NEW.status IN ('pagado', 'cancelado'))
        OR (OLD.status = 'pagado'    AND NEW.status IN ('enviado', 'cancelado'))
        OR (OLD.status = 'enviado'   AND NEW.status =  'entregado')
    ) THEN
        RAISE EXCEPTION 'Transicion de estado no permitida: % -> %',
            OLD.status, NEW.status
            USING ERRCODE = 'check_violation';
    END IF;

    -- Sellos de tiempo del estado alcanzado.
    IF NEW.status = 'pagado'    AND NEW.paid_at      IS NULL THEN NEW.paid_at      := now(); END IF;
    IF NEW.status = 'enviado'   AND NEW.shipped_at   IS NULL THEN NEW.shipped_at   := now(); END IF;
    IF NEW.status = 'entregado' AND NEW.delivered_at IS NULL THEN NEW.delivered_at := now(); END IF;
    IF NEW.status = 'cancelado' AND NEW.cancelled_at IS NULL THEN NEW.cancelled_at := now(); END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_orders_status_guard ON library.orders;
CREATE TRIGGER trg_orders_status_guard
    BEFORE UPDATE OF status ON library.orders
    FOR EACH ROW EXECUTE FUNCTION library.trg_orders_status_guard();

-- 6.4 Bitacora automatica de cada cambio de estado.
CREATE OR REPLACE FUNCTION library.trg_orders_log_status()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO library.order_status_history (order_id, from_status, to_status, changed_by, note)
        VALUES (NEW.id, NULL, NEW.status, NEW.user_id, 'pedido creado');
    ELSIF NEW.status IS DISTINCT FROM OLD.status THEN
        INSERT INTO library.order_status_history (order_id, from_status, to_status, changed_by)
        VALUES (NEW.id, OLD.status, NEW.status, NULL);
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_orders_log_status ON library.orders;
CREATE TRIGGER trg_orders_log_status
    AFTER INSERT OR UPDATE OF status ON library.orders
    FOR EACH ROW EXECUTE FUNCTION library.trg_orders_log_status();

-- ---------------------------------------------------------------------
-- 7. Procedimientos almacenados
-- ---------------------------------------------------------------------
-- 7.1 Crear pedido reservando stock.
--
-- Las lineas llegan como JSON: [{"bookId": 3, "quantity": 2}, ...]
-- El precio NO lo manda el cliente: se toma de library.books, para que
-- nadie pueda comprarse un libro a su propio precio.
--
-- La reserva de stock es la parte delicada. Se hace con
--     UPDATE books SET stock = stock - q WHERE id = ? AND stock >= q
-- y se comprueba que haya afectado una fila: si dos pedidos piden la
-- ultima unidad al mismo tiempo, uno gana y el otro recibe el error. El
-- UPDATE toma el bloqueo de fila, de modo que no hay ventana entre
-- "consultar stock" y "restarlo". Las filas se recorren ORDENADAS por
-- book_id para que dos pedidos con los mismos libros no se bloqueen
-- mutuamente en orden inverso (interbloqueo).
CREATE OR REPLACE FUNCTION library.sp_crear_pedido(
    p_user_id        INTEGER,
    p_lines          JSONB,
    p_notes          TEXT    DEFAULT NULL,
    p_currency       CHAR(3) DEFAULT 'MXN',
    p_shipping_cost  NUMERIC(12,2) DEFAULT 0,
    p_shipping_address TEXT  DEFAULT NULL
) RETURNS BIGINT AS $$
DECLARE
    v_order_id BIGINT;
    v_line     RECORD;
    v_book     RECORD;
    v_affected INTEGER;
    v_count    INTEGER := 0;
BEGIN
    IF p_lines IS NULL OR jsonb_typeof(p_lines) <> 'array'
       OR jsonb_array_length(p_lines) = 0 THEN
        RAISE EXCEPTION 'El pedido debe tener al menos una linea'
            USING ERRCODE = 'check_violation';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM library.users
                    WHERE id = p_user_id AND is_active) THEN
        RAISE EXCEPTION 'El usuario % no existe o esta desactivado', p_user_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    INSERT INTO library.orders (user_id, currency, shipping_cost, notes,
                                shipping_address)
    VALUES (p_user_id, COALESCE(p_currency, 'MXN'),
            COALESCE(p_shipping_cost, 0), p_notes, p_shipping_address)
    RETURNING id INTO v_order_id;

    FOR v_line IN
        SELECT (item->>'bookId')::INTEGER AS book_id,
               (item->>'quantity')::INTEGER AS quantity
          FROM jsonb_array_elements(p_lines) AS item
         ORDER BY (item->>'bookId')::INTEGER      -- orden fijo: evita interbloqueos
    LOOP
        IF v_line.book_id IS NULL OR v_line.quantity IS NULL THEN
            RAISE EXCEPTION 'Cada linea necesita bookId y quantity'
                USING ERRCODE = 'check_violation';
        END IF;
        IF v_line.quantity <= 0 THEN
            RAISE EXCEPTION 'La cantidad del libro % debe ser mayor que cero',
                v_line.book_id USING ERRCODE = 'check_violation';
        END IF;

        SELECT id, isbn, title, price, stock INTO v_book
          FROM library.books WHERE id = v_line.book_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'El libro % no existe', v_line.book_id
                USING ERRCODE = 'foreign_key_violation';
        END IF;

        -- Reserva atomica sobre books.stock (la unica tabla de stock).
        UPDATE library.books
           SET stock = stock - v_line.quantity
         WHERE id = v_line.book_id
           AND stock >= v_line.quantity;
        GET DIAGNOSTICS v_affected = ROW_COUNT;
        IF v_affected = 0 THEN
            RAISE EXCEPTION 'Stock insuficiente de "%" (ISBN %): hay %, se piden %',
                v_book.title, v_book.isbn, v_book.stock, v_line.quantity
                USING ERRCODE = 'check_violation';
        END IF;

        INSERT INTO library.order_lines (order_id, book_id, quantity, unit_price,
                                         book_title, book_isbn)
        VALUES (v_order_id, v_line.book_id, v_line.quantity, v_book.price,
                v_book.title, v_book.isbn);
        v_count := v_count + 1;
    END LOOP;

    IF v_count = 0 THEN
        RAISE EXCEPTION 'El pedido debe tener al menos una linea valida'
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN v_order_id;
END;
$$ LANGUAGE plpgsql;

-- 7.2 Cambiar la cantidad de una linea ajustando el stock por la diferencia.
--     Solo tiene sentido mientras el pedido siga pendiente.
CREATE OR REPLACE FUNCTION library.sp_ajustar_linea_pedido(
    p_order_id    BIGINT,
    p_book_id     INTEGER,
    p_quantity    INTEGER        -- 0 = quitar la linea
) RETURNS VOID AS $$
DECLARE
    v_status   library.order_status;
    v_current  INTEGER;
    v_delta    INTEGER;
    v_affected INTEGER;
    v_book     RECORD;
BEGIN
    SELECT status INTO v_status FROM library.orders WHERE id = p_order_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'El pedido % no existe', p_order_id
            USING ERRCODE = 'no_data_found';
    END IF;
    IF v_status <> 'pendiente' THEN
        RAISE EXCEPTION 'Solo se puede modificar un pedido pendiente (esta en %)',
            v_status USING ERRCODE = 'check_violation';
    END IF;
    IF p_quantity < 0 THEN
        RAISE EXCEPTION 'La cantidad no puede ser negativa'
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT quantity INTO v_current FROM library.order_lines
     WHERE order_id = p_order_id AND book_id = p_book_id;

    IF NOT FOUND THEN
        IF p_quantity = 0 THEN
            RETURN;                                 -- quitar lo que no esta
        END IF;
        SELECT id, isbn, title, price, stock INTO v_book
          FROM library.books WHERE id = p_book_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'El libro % no existe', p_book_id
                USING ERRCODE = 'foreign_key_violation';
        END IF;
        UPDATE library.books SET stock = stock - p_quantity
         WHERE id = p_book_id AND stock >= p_quantity;
        GET DIAGNOSTICS v_affected = ROW_COUNT;
        IF v_affected = 0 THEN
            RAISE EXCEPTION 'Stock insuficiente de "%" (ISBN %): hay %, se piden %',
                v_book.title, v_book.isbn, v_book.stock, p_quantity
                USING ERRCODE = 'check_violation';
        END IF;
        INSERT INTO library.order_lines (order_id, book_id, quantity, unit_price,
                                         book_title, book_isbn)
        VALUES (p_order_id, p_book_id, p_quantity, v_book.price,
                v_book.title, v_book.isbn);
        RETURN;
    END IF;

    v_delta := p_quantity - v_current;              -- >0 reserva mas, <0 devuelve

    IF v_delta > 0 THEN
        SELECT id, isbn, title, stock INTO v_book
          FROM library.books WHERE id = p_book_id;
        UPDATE library.books SET stock = stock - v_delta
         WHERE id = p_book_id AND stock >= v_delta;
        GET DIAGNOSTICS v_affected = ROW_COUNT;
        IF v_affected = 0 THEN
            RAISE EXCEPTION 'Stock insuficiente de "%" (ISBN %): hay %, faltan %',
                v_book.title, v_book.isbn, v_book.stock, v_delta
                USING ERRCODE = 'check_violation';
        END IF;
    ELSIF v_delta < 0 THEN
        UPDATE library.books SET stock = stock + (-v_delta) WHERE id = p_book_id;
    END IF;

    IF p_quantity = 0 THEN
        DELETE FROM library.order_lines
         WHERE order_id = p_order_id AND book_id = p_book_id;
    ELSE
        UPDATE library.order_lines SET quantity = p_quantity
         WHERE order_id = p_order_id AND book_id = p_book_id;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- 7.3 Cancelar un pedido DEVOLVIENDO el stock reservado.
CREATE OR REPLACE FUNCTION library.sp_cancelar_pedido(
    p_order_id   BIGINT,
    p_changed_by INTEGER DEFAULT NULL,
    p_reason     VARCHAR(300) DEFAULT NULL
) RETURNS VOID AS $$
DECLARE
    v_status library.order_status;
BEGIN
    SELECT status INTO v_status FROM library.orders WHERE id = p_order_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'El pedido % no existe', p_order_id
            USING ERRCODE = 'no_data_found';
    END IF;
    IF v_status IN ('cancelado', 'entregado', 'enviado') THEN
        RAISE EXCEPTION 'Un pedido en estado % ya no se puede cancelar', v_status
            USING ERRCODE = 'check_violation';
    END IF;

    -- Devuelve al catalogo lo que el pedido tenia reservado.
    UPDATE library.books b
       SET stock = b.stock + l.quantity
      FROM library.order_lines l
     WHERE l.order_id = p_order_id AND b.id = l.book_id;

    UPDATE library.orders SET status = 'cancelado' WHERE id = p_order_id;

    UPDATE library.order_status_history
       SET changed_by = COALESCE(p_changed_by, changed_by),
           note = COALESCE(p_reason, 'pedido cancelado')
     WHERE id = (SELECT max(id) FROM library.order_status_history
                  WHERE order_id = p_order_id)
       AND to_status = 'cancelado';
END;
$$ LANGUAGE plpgsql;

-- 7.4 Mover el estado (envio, entrega, pago) dejando constancia de quien.
CREATE OR REPLACE FUNCTION library.sp_cambiar_estado_pedido(
    p_order_id      BIGINT,
    p_to_status     library.order_status,
    p_changed_by    INTEGER DEFAULT NULL,
    p_note          VARCHAR(300) DEFAULT NULL,
    p_carrier       VARCHAR(60) DEFAULT NULL,
    p_tracking_code VARCHAR(60) DEFAULT NULL
) RETURNS VOID AS $$
BEGIN
    IF p_to_status = 'cancelado' THEN
        -- La cancelacion tiene que devolver stock: se delega.
        PERFORM library.sp_cancelar_pedido(p_order_id, p_changed_by, p_note);
        RETURN;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM library.orders WHERE id = p_order_id) THEN
        RAISE EXCEPTION 'El pedido % no existe', p_order_id
            USING ERRCODE = 'no_data_found';
    END IF;

    UPDATE library.orders
       SET status = p_to_status,
           carrier = COALESCE(p_carrier, carrier),
           tracking_code = COALESCE(p_tracking_code, tracking_code)
     WHERE id = p_order_id;

    -- COALESCE en los dos campos: un cambio de estado SIN nota no debe
    -- borrar la que ya hubiera puesto el disparador (por ejemplo, la que
    -- escribe trg_payments_settle_order al liquidar el pedido).
    -- Y se exige que la ultima fila sea la de ESTE estado: si el estado no
    -- cambio, el disparador no inserto nada y se estaria pisando la
    -- bitacora de un cambio anterior.
    UPDATE library.order_status_history
       SET changed_by = COALESCE(p_changed_by, changed_by),
           note       = COALESCE(p_note, note)
     WHERE id = (SELECT max(id) FROM library.order_status_history
                  WHERE order_id = p_order_id)
       AND to_status = p_to_status;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------
-- 8. Vistas
-- ---------------------------------------------------------------------
-- 8.1 Pedido con su dueno y sus importes (lectura administrativa).
CREATE OR REPLACE VIEW library.v_orders_detail AS
SELECT o.id, o.order_number, o.status, o.currency,
       o.subtotal, o.shipping_cost, o.total,
       o.user_id, u.email AS user_email, u.full_name AS user_name,
       o.carrier, o.tracking_code,
       o.placed_at, o.paid_at, o.shipped_at, o.delivered_at, o.cancelled_at,
       (SELECT count(*) FROM library.order_lines l WHERE l.order_id = o.id) AS line_count,
       (SELECT COALESCE(sum(l.quantity), 0) FROM library.order_lines l
         WHERE l.order_id = o.id) AS item_count
  FROM library.orders o
  JOIN library.users u ON u.id = o.user_id;
-- Nota de dependencia: data/pagos_migration.sql REEMPLAZA esta vista
-- anadiendole la columna paid_amount, una vez que library.payments
-- existe. Las migraciones se aplican en orden: roles, pedidos, pagos.

-- 8.2 RASTREO PUBLICO. Es la unica cara de un pedido que se sirve sin
--     token, para que la paqueteria pueda manejar su logistica. No
--     lleva dueno, ni correo, ni importes, ni que libros se compraron:
--     solo el estado del envio y sus fechas.
CREATE OR REPLACE VIEW library.v_order_tracking AS
SELECT o.order_number,
       o.status,
       o.carrier,
       o.tracking_code,
       o.placed_at,
       o.shipped_at,
       o.delivered_at,
       (SELECT COALESCE(sum(l.quantity), 0) FROM library.order_lines l
         WHERE l.order_id = o.id) AS item_count
  FROM library.orders o;

-- ---------------------------------------------------------------------
-- 9. Comprobacion
-- ---------------------------------------------------------------------
--   SELECT library.sp_crear_pedido(1, '[{"bookId":1,"quantity":1}]'::jsonb);
--   SELECT * FROM library.v_orders_detail ORDER BY id DESC LIMIT 5;
--   SELECT * FROM library.v_order_tracking WHERE order_number = 'PED-000001';
