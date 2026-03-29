from . import models


def _l10n_do_pos_post_init(env):
    credit_note = env.ref('l10n_do_pos.credit_note', raise_if_not_found=False)
    pos_config = env.ref('point_of_sale.pos_config_main', raise_if_not_found=False)
    if credit_note and pos_config:
        pos_config.with_context(
            bypass_payment_method_ids_forbidden_change=True
        ).write({'payment_method_ids': [(4, credit_note.id)]})
