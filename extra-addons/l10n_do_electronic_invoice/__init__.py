from . import models
from . import wizard


def post_init_hook(env):
    env['l10n_do.municipality']._sync_dgii_codes_and_states()


def post_migrate_hook(env):
    env['l10n_do.municipality']._sync_dgii_codes_and_states()
    _fix_auto_purchase_ncf_defaults(env)


def _fix_auto_purchase_ncf_defaults(env):
    """Corrige registros existentes de l10n_do.ecf.doc.type.config.

    Al agregar la columna allow_manual_ncf con DEFAULT TRUE, los registros
    preexistentes de E41/E43/E47 quedan en True, pero deben ser False porque
    l10n_do_accounting los trata como automáticos (e-informal, e-minor, e-exterior).

    Se ejecuta en cada upgrade; es idempotente.
    """
    auto_types = ('41', '43', '47')
    env.cr.execute(
        """
        UPDATE l10n_do_ecf_doc_type_config
           SET allow_manual_ncf = FALSE
         WHERE doc_type IN %s
           AND allow_manual_ncf = TRUE
        """,
        (auto_types,),
    )
