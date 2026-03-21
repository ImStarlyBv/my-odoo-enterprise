from . import models


def post_init_hook(env):
    env.cr.execute("UPDATE ir_module_module SET to_buy = false WHERE to_buy = true")
