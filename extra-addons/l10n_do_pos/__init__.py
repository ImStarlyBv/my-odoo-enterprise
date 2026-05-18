from . import models


def _l10n_do_pos_post_init(env):
    """
    Hook post-instalación:
    - Agrega el método de pago NC al POS principal si existe.
    - Asigna el partner consumidor por defecto al POS principal si existe.
    """
    credit_note = env.ref('l10n_do_pos.credit_note', raise_if_not_found=False)
    pos_config = env.ref('point_of_sale.pos_config_main', raise_if_not_found=False)
    consumer = env.ref('l10n_do_pos.default_pos_partner', raise_if_not_found=False)

    if pos_config:
        vals = {}
        if consumer:
            vals['l10n_do_default_consumer_partner_id'] = consumer.id
        if credit_note and credit_note not in pos_config.payment_method_ids:
            vals['payment_method_ids'] = [(4, credit_note.id)]
        if vals:
            pos_config.write(vals)
