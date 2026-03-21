from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        result = super().session_info()
        # Force enterprise flag in session so the JS frontend sets
        # odoo.info.isEnterprise = true (checks server_version_info[-1] === 'e')
        version_info = list(result.get('server_version_info', []))
        if version_info:
            version_info[-1] = 'e'
            result['server_version_info'] = version_info
        result['edition'] = 'enterprise'
        return result
