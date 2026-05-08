from . import models
from . import wizard


def post_init_hook(env):
    env['l10n_do.municipality']._sync_dgii_codes_and_states()


def post_migrate_hook(env):
    env['l10n_do.municipality']._sync_dgii_codes_and_states()
