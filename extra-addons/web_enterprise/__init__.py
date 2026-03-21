from . import models


def _clear_to_buy(env):
    env.cr.execute("UPDATE ir_module_module SET to_buy = false WHERE to_buy = true")


def post_init_hook(env):
    _clear_to_buy(env)


def post_migrate_hook(env, *args, **kwargs):
    _clear_to_buy(env)
