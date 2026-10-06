-- =====================================================================
-- data/pagos_migration.sql
-- MIGRACION del microservicio de PAGOS (apps/services/pagos).
-- Se aplica DESPUES de data/pedidos_migration.sql: payments apunta a orders.
--
-- QUE REGISTRA Y QUE NO
--   Registra el HECHO de un pago: cuanto, con que metodo, cuando, contra
--   que pedido y con que referencia de la pasarela.
--   NO guarda datos de instrumento de pago: ni numero de tarjeta, ni CVV,
--   ni fecha de vencimiento, ni titular. Solo la referencia que devuelve
--   la pasarela y, como mucho, los cuatro ultimos digitos que ella misma
--   publica. Lo que no se guarda no se puede filtrar.
--
-- ESTADOS DEL PAGO
--   pendiente  -> autorizado | rechazado
--   autorizado -> aplicado   | rechazado
--   aplicado   -> reembolsado
--   rechazado / reembolsado -> (final)
--
-- EFECTO SOBRE EL PEDIDO
--   Cuando la suma de los pagos APLICADOS alcanza el total del pedido,
--   el pedido pasa a 'pagado' automaticamente (disparador). Es la base
--   la que decide eso, no la aplicacion: asi no hay forma de marcar un
--   pedido como pagado sin que exista el dinero detras.
--
-- Aplicacion en la instancia (idempotente):
--   psql -U library_user -d library_db -f data/pagos_migration.sql
-- =====================================================================

SET search_path TO library, public;

-- ---------------------------------------------------------------------
-- 1. Estados del pago
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t
                     JOIN pg_namespace n ON n.oid = t.typnamespace
                    WHERE t.typname = 'payment_status' AND n.nspname = 'library') THEN
        CREATE TYPE library.payment_status AS ENUM
            ('pendiente', 'autorizado', 'aplicado', 'rechazado', 'reembolsado');
    END IF;
END
$$;

-- ---------------------------------------------------------------------
-- 2. Catalogo de metodos de pago  (catalogo independiente, 1:N)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS library.payment_methods (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(40)  NOT NULL UNIQUE,
    description VARCHAR(200) NOT NULL DEFAULT '',
    -- Si requiere autorizacion externa (pasarela) o se aplica al instante.
    requires_authorization BOOLEAN NOT NULL DEFAULT TRUE,
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE
);

INSERT INTO library.payment_methods (id, name, description, requires_authorization) VALUES
    (1, 'efectivo',      'Pago en mostrador; se aplica de inmediato',        FALSE),
    (2, 'tarjeta',       'Tarjeta de credito o debito via pasarela',         TRUE),
    (3, 'transferencia', 'Transferencia bancaria (SPEI); se confirma a mano', TRUE),
    (4, 'paypal',        'Cuenta PayPal via pasarela',                       TRUE)
ON CONFLICT (id) DO UPDATE
    SET name = EXCLUDED.name,
        description = EXCLUDED.description,
        requires_authorization = EXCLUDED.requires_authorization;

SELECT setval(pg_get_serial_sequence('library.payment_methods', 'id'),
              GREATEST((SELECT max(id) FROM library.payment_methods), 1));

-- ---------------------------------------------------------------------
-- 3. Numero de pago legible (PAG-000001)
-- ---------------------------------------------------------------------
CREATE SEQUENCE IF NOT EXISTS library.payment_reference_seq START 1;

CREATE OR REPLACE FUNCTION library.fn_next_payment_reference()
RETURNS TEXT AS $$
    SELECT 'PAG-' || lpad(nextval('library.payment_reference_seq')::text, 6, '0');
$$ LANGUAGE sql VOLATILE;

-- ---------------------------------------------------------------------
-- 4. Pagos
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS library.payments (
    id              BIGSERIAL PRIMARY KEY,
    payment_reference VARCHAR(20) NOT NULL UNIQUE
                                  DEFAULT library.fn_next_payment_reference(),
    order_id        BIGINT        NOT NULL REFERENCES library.orders(id)
                                  ON UPDATE CASCADE ON DELETE RESTRICT,
    method_id       INTEGER       NOT NULL REFERENCES library.payment_methods(id)
                                  ON UPDATE CASCADE ON DELETE RESTRICT,
    status          library.payment_status NOT NULL DEFAULT 'pendiente',
    amount          NUMERIC(12,2) NOT NULL CHECK (amount > 0),
    currency        CHAR(3)       NOT NULL DEFAULT 'MXN',

    -- Lo que devuelve la pasarela. NUNCA el instrumento de pago.
    authorization_code VARCHAR(60),
    -- Clave de idempotencia del cliente: dos intentos con la misma clave
    -- son el MISMO pago, no dos. Es lo que evita el cobro doble cuando
    -- una peticion se reintenta por un tiempo de espera.
    idempotency_key VARCHAR(80),
    -- Ultimos cuatro digitos, si la pasarela los publica. Nada mas.
    card_last4      CHAR(4) CHECK (card_last4 IS NULL OR card_last4 ~ '^[0-9]{4}$'),

    registered_by   INTEGER       REFERENCES library.users(id) ON DELETE SET NULL,
    notes           VARCHAR(300),
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    authorized_at   TIMESTAMPTZ,
    applied_at      TIMESTAMPTZ,
    rejected_at     TIMESTAMPTZ,
    refunded_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_payments_order  ON library.payments (order_id);
CREATE INDEX IF NOT EXISTS ix_payments_status ON library.payments (status);
CREATE INDEX IF NOT EXISTS ix_payments_created ON library.payments (created_at DESC);

-- La clave de idempotencia es unica cuando viene (indice parcial: los
-- pagos de mostrador pueden no traerla).
CREATE UNIQUE INDEX IF NOT EXISTS ux_payments_idempotency
    ON library.payments (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

-- ---------------------------------------------------------------------
-- 5. Bitacora de estados del pago
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS library.payment_status_history (
    id          BIGSERIAL PRIMARY KEY,
    payment_id  BIGINT      NOT NULL REFERENCES library.payments(id) ON DELETE CASCADE,
    from_status library.payment_status,
    to_status   library.payment_status NOT NULL,
    changed_by  INTEGER     REFERENCES library.users(id) ON DELETE SET NULL,
    note        VARCHAR(300),
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_payment_history_payment
    ON library.payment_status_history (payment_id, changed_at DESC);

-- ---------------------------------------------------------------------
-- 6. Disparadores
-- ---------------------------------------------------------------------
-- 6.1 updated_at
CREATE OR REPLACE FUNCTION library.trg_payments_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_payments_updated_at ON library.payments;
CREATE TRIGGER trg_payments_updated_at
    BEFORE UPDATE ON library.payments
    FOR EACH ROW EXECUTE FUNCTION library.trg_payments_updated_at();

-- 6.2 Moneda y pedido coherentes: un pago en otra divisa que su pedido
--     seria imposible de cuadrar.
CREATE OR REPLACE FUNCTION library.trg_payments_validate()
RETURNS TRIGGER AS $$
DECLARE
    v_order RECORD;
BEGIN
    SELECT status, currency, total INTO v_order
      FROM library.orders WHERE id = NEW.order_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'El pedido % no existe', NEW.order_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF NEW.currency <> v_order.currency THEN
        RAISE EXCEPTION 'El pago esta en % y el pedido en %',
            NEW.currency, v_order.currency USING ERRCODE = 'check_violation';
    END IF;
    IF TG_OP = 'INSERT' AND v_order.status = 'cancelado' THEN
        RAISE EXCEPTION 'No se puede pagar un pedido cancelado'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_payments_validate ON library.payments;
CREATE TRIGGER trg_payments_validate
    BEFORE INSERT OR UPDATE OF order_id, currency ON library.payments
    FOR EACH ROW EXECUTE FUNCTION library.trg_payments_validate();

-- 6.3 Maquina de estados del pago + sellos de tiempo.
CREATE OR REPLACE FUNCTION library.trg_payments_status_guard()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status IS NOT DISTINCT FROM OLD.status THEN
        RETURN NEW;
    END IF;

    -- 'rechazado' y 'reembolsado' son finales: ninguna rama sale de ellos.
    IF NOT (
           (OLD.status = 'pendiente'  AND NEW.status IN ('autorizado', 'aplicado', 'rechazado'))
        OR (OLD.status = 'autorizado' AND NEW.status IN ('aplicado', 'rechazado'))
        OR (OLD.status = 'aplicado'   AND NEW.status =  'reembolsado')
    ) THEN
        RAISE EXCEPTION 'Transicion de pago no permitida: % -> %',
            OLD.status, NEW.status USING ERRCODE = 'check_violation';
    END IF;

    IF NEW.status = 'autorizado'  AND NEW.authorized_at IS NULL THEN NEW.authorized_at := now(); END IF;
    IF NEW.status = 'aplicado'    AND NEW.applied_at    IS NULL THEN NEW.applied_at    := now(); END IF;
    IF NEW.status = 'rechazado'   AND NEW.rejected_at   IS NULL THEN NEW.rejected_at   := now(); END IF;
    IF NEW.status = 'reembolsado' AND NEW.refunded_at   IS NULL THEN NEW.refunded_at   := now(); END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_payments_status_guard ON library.payments;
CREATE TRIGGER trg_payments_status_guard
    BEFORE UPDATE OF status ON library.payments
    FOR EACH ROW EXECUTE FUNCTION library.trg_payments_status_guard();

-- 6.4 Bitacora automatica.
CREATE OR REPLACE FUNCTION library.trg_payments_log_status()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO library.payment_status_history (payment_id, from_status, to_status,
                                                    changed_by, note)
        VALUES (NEW.id, NULL, NEW.status, NEW.registered_by, 'pago registrado');
    ELSIF NEW.status IS DISTINCT FROM OLD.status THEN
        INSERT INTO library.payment_status_history (payment_id, from_status, to_status,
                                                    changed_by)
        VALUES (NEW.id, OLD.status, NEW.status, NEW.registered_by);
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_payments_log_status ON library.payments;
CREATE TRIGGER trg_payments_log_status
    AFTER INSERT OR UPDATE OF status ON library.payments
    FOR EACH ROW EXECUTE FUNCTION library.trg_payments_log_status();

-- 6.5 EL PAGO ACTUALIZA EL ESTADO DEL PEDIDO.
--     Cuando lo aplicado alcanza el total, el pedido pasa a 'pagado'.
--     Si un pago aplicado se reembolsa y deja de cubrir el total, el
--     pedido NO vuelve atras solo: 'pagado' -> 'pendiente' no es una
--     transicion valida y rehacer la historia seria peor que dejar
--     constancia. Queda registrado en payment_status_history y lo
--     resuelve una persona.
CREATE OR REPLACE FUNCTION library.trg_payments_settle_order()
RETURNS TRIGGER AS $$
DECLARE
    v_order   RECORD;
    v_applied NUMERIC(12,2);
BEGIN
    SELECT id, status, total INTO v_order
      FROM library.orders WHERE id = NEW.order_id FOR UPDATE;

    SELECT COALESCE(sum(amount), 0) INTO v_applied
      FROM library.payments
     WHERE order_id = NEW.order_id AND status = 'aplicado';

    IF v_applied >= v_order.total AND v_order.status = 'pendiente' THEN
        UPDATE library.orders SET status = 'pagado' WHERE id = v_order.id;
        UPDATE library.order_status_history
           SET changed_by = NEW.registered_by,
               note = 'pago ' || NEW.payment_reference || ' aplicado'
         WHERE id = (SELECT max(id) FROM library.order_status_history
                      WHERE order_id = v_order.id);
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_payments_settle_order ON library.payments;
CREATE TRIGGER trg_payments_settle_order
    AFTER INSERT OR UPDATE OF status ON library.payments
    FOR EACH ROW WHEN (NEW.status = 'aplicado')
    EXECUTE FUNCTION library.trg_payments_settle_order();

-- ---------------------------------------------------------------------
-- 7. Procedimientos almacenados
-- ---------------------------------------------------------------------
-- 7.1 Registrar un pago.
--
-- No se permite pagar MAS de lo que falta: el importe se compara contra
-- el saldo pendiente del pedido (total menos lo ya aplicado o
-- autorizado). Un metodo que no requiere autorizacion (efectivo) nace
-- directamente 'aplicado'.
--
-- p_idempotency_key: si ya existe un pago con esa clave, se devuelve el
-- que ya estaba en lugar de crear otro. Asi un reintento del cliente no
-- cobra dos veces.
CREATE OR REPLACE FUNCTION library.sp_registrar_pago(
    p_order_id        BIGINT,
    p_method_id       INTEGER,
    p_amount          NUMERIC(12,2),
    p_registered_by   INTEGER DEFAULT NULL,
    p_idempotency_key VARCHAR(80) DEFAULT NULL,
    p_authorization_code VARCHAR(60) DEFAULT NULL,
    p_card_last4      CHAR(4) DEFAULT NULL,
    p_notes           VARCHAR(300) DEFAULT NULL
) RETURNS BIGINT AS $$
DECLARE
    v_existing  BIGINT;
    v_order     RECORD;
    v_committed NUMERIC(12,2);
    v_method    RECORD;
    v_status    library.payment_status;
    v_id        BIGINT;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT id INTO v_existing FROM library.payments
         WHERE idempotency_key = p_idempotency_key;
        IF FOUND THEN
            RETURN v_existing;                      -- mismo pago, no uno nuevo
        END IF;
    END IF;

    IF p_amount IS NULL OR p_amount <= 0 THEN
        RAISE EXCEPTION 'El importe del pago debe ser mayor que cero'
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT id, status, currency, total INTO v_order
      FROM library.orders WHERE id = p_order_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'El pedido % no existe', p_order_id
            USING ERRCODE = 'no_data_found';
    END IF;
    IF v_order.status IN ('cancelado') THEN
        RAISE EXCEPTION 'No se puede pagar un pedido cancelado'
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT id, name, requires_authorization, is_active INTO v_method
      FROM library.payment_methods WHERE id = p_method_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'El metodo de pago % no existe', p_method_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF NOT v_method.is_active THEN
        RAISE EXCEPTION 'El metodo de pago "%" esta desactivado', v_method.name
            USING ERRCODE = 'check_violation';
    END IF;

    -- Saldo ya comprometido: aplicado + autorizado + pendiente.
    SELECT COALESCE(sum(amount), 0) INTO v_committed
      FROM library.payments
     WHERE order_id = p_order_id
       AND status IN ('aplicado', 'autorizado', 'pendiente');

    IF v_committed + p_amount > v_order.total THEN
        RAISE EXCEPTION 'El pago excede el saldo del pedido: total %, comprometido %, se intenta %',
            v_order.total, v_committed, p_amount USING ERRCODE = 'check_violation';
    END IF;

    v_status := CASE
        WHEN NOT v_method.requires_authorization THEN 'aplicado'
        WHEN p_authorization_code IS NOT NULL     THEN 'autorizado'
        ELSE 'pendiente'
    END;

    INSERT INTO library.payments (order_id, method_id, status, amount,
                                  currency, authorization_code, idempotency_key,
                                  card_last4, registered_by, notes)
    VALUES (p_order_id, p_method_id, v_status, p_amount,
            v_order.currency, p_authorization_code, p_idempotency_key,
            p_card_last4, p_registered_by, p_notes)
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$ LANGUAGE plpgsql;

-- 7.1b Sella la fila de bitacora que acaba de escribir el disparador.
--
-- trg_payments_log_status inserta la fila del cambio de estado, pero no
-- sabe QUIEN lo hizo (el disparador solo ve la fila, no al usuario). Esta
-- funcion completa ese dato en la fila recien insertada.
--
-- Importante: se exige que la ultima fila corresponda AL ESTADO que se
-- acaba de fijar. Si el estado no cambio, el disparador no inserto nada y
-- sin esa condicion se estaria pisando la bitacora de un cambio anterior.
CREATE OR REPLACE FUNCTION library.sp_sellar_historial_pago(
    p_payment_id BIGINT,
    p_to_status  library.payment_status,
    p_changed_by INTEGER,
    p_note       VARCHAR(300)
) RETURNS VOID AS $$
BEGIN
    UPDATE library.payment_status_history
       SET changed_by = COALESCE(p_changed_by, changed_by),
           note       = COALESCE(p_note, note)
     WHERE id = (SELECT max(id) FROM library.payment_status_history
                  WHERE payment_id = p_payment_id)
       AND to_status = p_to_status;
END;
$$ LANGUAGE plpgsql;

-- 7.2 Aplicar (confirmar) un pago ya autorizado.
--
-- registered_by NO se toca: significa QUIEN REGISTRO el pago y es un dato
-- historico. Quien lo aplica despues puede ser otra persona, y eso se
-- anota en payment_status_history, no pisando el registrante. (Una
-- version anterior hacia registered_by = COALESCE(p_changed_by, ...) y
-- perdia el rastro del original.)
CREATE OR REPLACE FUNCTION library.sp_aplicar_pago(
    p_payment_id BIGINT,
    p_changed_by INTEGER DEFAULT NULL,
    p_authorization_code VARCHAR(60) DEFAULT NULL
) RETURNS VOID AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM library.payments WHERE id = p_payment_id) THEN
        RAISE EXCEPTION 'El pago % no existe', p_payment_id
            USING ERRCODE = 'no_data_found';
    END IF;

    UPDATE library.payments
       SET status = 'aplicado',
           authorization_code = COALESCE(p_authorization_code, authorization_code)
     WHERE id = p_payment_id;

    PERFORM library.sp_sellar_historial_pago(p_payment_id, 'aplicado',
                                             p_changed_by, NULL);
END;
$$ LANGUAGE plpgsql;

-- 7.3 Rechazar o reembolsar.
--
-- Igual que arriba: ni registered_by ni notes se pisan. `notes` es la nota
-- del PAGO; el motivo de ESTE cambio de estado va a la bitacora.
CREATE OR REPLACE FUNCTION library.sp_cambiar_estado_pago(
    p_payment_id BIGINT,
    p_to_status  library.payment_status,
    p_changed_by INTEGER DEFAULT NULL,
    p_note       VARCHAR(300) DEFAULT NULL
) RETURNS VOID AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM library.payments WHERE id = p_payment_id) THEN
        RAISE EXCEPTION 'El pago % no existe', p_payment_id
            USING ERRCODE = 'no_data_found';
    END IF;

    UPDATE library.payments SET status = p_to_status WHERE id = p_payment_id;

    PERFORM library.sp_sellar_historial_pago(p_payment_id, p_to_status,
                                             p_changed_by, p_note);
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------
-- 8. Vistas
-- ---------------------------------------------------------------------
-- 8.1 Pago con su pedido y su metodo (lectura administrativa; nunca publica).
CREATE OR REPLACE VIEW library.v_payments_detail AS
SELECT p.id, p.payment_reference, p.status, p.amount, p.currency,
       p.authorization_code, p.card_last4,
       p.order_id, o.order_number, o.status AS order_status, o.total AS order_total,
       o.user_id, u.email AS user_email,
       p.method_id, m.name AS method_name,
       p.registered_by, p.notes,
       p.created_at, p.authorized_at, p.applied_at, p.rejected_at, p.refunded_at
  FROM library.payments p
  JOIN library.orders o ON o.id = p.order_id
  JOIN library.users u ON u.id = o.user_id
  JOIN library.payment_methods m ON m.id = p.method_id;

-- 8.2 Saldo por pedido: lo que se debe y lo que ya se cobro.
CREATE OR REPLACE VIEW library.v_order_balance AS
SELECT o.id AS order_id, o.order_number, o.status, o.total, o.currency,
       COALESCE(sum(p.amount) FILTER (WHERE p.status = 'aplicado'), 0) AS paid,
       COALESCE(sum(p.amount) FILTER (WHERE p.status IN ('autorizado', 'pendiente')), 0) AS committed,
       o.total - COALESCE(sum(p.amount) FILTER (WHERE p.status = 'aplicado'), 0) AS balance
  FROM library.orders o
  LEFT JOIN library.payments p ON p.order_id = o.id
 GROUP BY o.id, o.order_number, o.status, o.total, o.currency;

-- 8.3 Ahora que library.payments existe, la vista de pedidos puede
--     informar cuanto se ha cobrado. CREATE OR REPLACE VIEW admite
--     ANADIR columnas al final, que es exactamente lo que se hace.
CREATE OR REPLACE VIEW library.v_orders_detail AS
SELECT o.id, o.order_number, o.status, o.currency,
       o.subtotal, o.shipping_cost, o.total,
       o.user_id, u.email AS user_email, u.full_name AS user_name,
       o.carrier, o.tracking_code,
       o.placed_at, o.paid_at, o.shipped_at, o.delivered_at, o.cancelled_at,
       (SELECT count(*) FROM library.order_lines l WHERE l.order_id = o.id) AS line_count,
       (SELECT COALESCE(sum(l.quantity), 0) FROM library.order_lines l
         WHERE l.order_id = o.id) AS item_count,
       COALESCE((SELECT sum(p.amount) FROM library.payments p
                  WHERE p.order_id = o.id AND p.status = 'aplicado'), 0) AS paid_amount
  FROM library.orders o
  JOIN library.users u ON u.id = o.user_id;

-- ---------------------------------------------------------------------
-- 9. Comprobacion
-- ---------------------------------------------------------------------
--   SELECT library.sp_registrar_pago(1, 1, 199.00, 1, 'demo-001');
--   SELECT * FROM library.v_order_balance WHERE order_id = 1;
--   SELECT * FROM library.v_payments_detail ORDER BY id DESC LIMIT 5;
