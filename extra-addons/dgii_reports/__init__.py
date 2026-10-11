# Part of Domincana Premium.
# See LICENSE file for full copyright and licensing details.
# © 2018 José López <jlopez@indexa.do>

from . import controllers
from . import models
from . import wizard


def post_init_hook(env):
    """Classify the taxes of already installed Dominican charts and compute
    the DGII fields of the existing fiscal invoices."""
    tax_data = env['account.chart.template']._get_do_dgii_account_tax()
    companies = env['res.company'].search([
        ('chart_template', '=', 'do'),
        ('parent_id', '=', False),
    ])
    for company in companies:
        for xml_id, vals in tax_data.items():
            tax = env.ref('account.%s_%s' % (company.id, xml_id), raise_if_not_found=False)
            if tax:
                tax.write({
                    fname: vals[fname]
                    for fname in ('l10n_do_tax_type', 'isr_retention_type')
                    if fname in vals
                })

    env['account.move'].search([
        ('company_id', 'child_of', companies.ids),
        ('move_type', 'in', ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')),
        ('state', '!=', 'draft'),
    ])._dgii_recompute_fields()
