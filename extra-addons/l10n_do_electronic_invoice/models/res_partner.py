from odoo import models, fields, api


class Partner(models.Model):
    _inherit = 'res.partner'

    l10n_do_municipality_id = fields.Many2one(
        comodel_name='l10n_do.municipality',
        string='Municipio (DGII)',
        domain="[('state_id', '=', state_id)]",
        help='Municipio oficial DGII. Sincroniza automáticamente con el campo Ciudad.',
    )

    @api.onchange('state_id')
    def _onchange_state_id_clear_municipality(self):
        for partner in self:
            if partner.state_id and partner.l10n_do_municipality_id.state_id != partner.state_id:
                partner.l10n_do_municipality_id = False

    @api.onchange('l10n_do_municipality_id')
    def _onchange_l10n_do_municipality_sync_city(self):
        for partner in self:
            if partner.l10n_do_municipality_id:
                partner.city = partner.l10n_do_municipality_id.name

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('l10n_do_municipality_id'):
                mun = self.env['l10n_do.municipality'].browse(vals['l10n_do_municipality_id'])
                if mun.exists():
                    vals['city'] = mun.name
            elif vals.get('city') and vals.get('country_id'):
                country = self.env['res.country'].browse(vals['country_id'])
                if country.code == 'DO':
                    domain = [('name', '=ilike', vals['city'])]
                    if vals.get('state_id'):
                        domain.append(('state_id', '=', vals['state_id']))
                    mun = self.env['l10n_do.municipality'].search(domain, limit=1)
                    if mun:
                        vals['l10n_do_municipality_id'] = mun.id
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('l10n_do_municipality_id'):
            mun = self.env['l10n_do.municipality'].browse(vals['l10n_do_municipality_id'])
            if mun.exists():
                vals['city'] = mun.name
        elif vals.get('city') and not vals.get('l10n_do_municipality_id'):
            for partner in self:
                if partner.country_code == 'DO':
                    domain = [('name', '=ilike', vals['city'])]
                    if partner.state_id:
                        domain.append(('state_id', '=', partner.state_id.id))
                    mun = self.env['l10n_do.municipality'].search(domain, limit=1)
                    if mun:
                        vals['l10n_do_municipality_id'] = mun.id
                    break
        return super().write(vals)
