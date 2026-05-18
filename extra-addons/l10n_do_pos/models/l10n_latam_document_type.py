from odoo import api, models, _
from odoo.exceptions import ValidationError


class L10nLatamDocumentType(models.Model):
    """
    Extiende l10n_latam.document.type para cargarlo en el frontend del POS
    mediante pos.load.mixin. Solo se cargan los tipos configurados en el
    diario de facturación del POS config activo.
    """
    _inherit = ['l10n_latam.document.type', 'pos.load.mixin']
    _name = 'l10n_latam.document.type'

    @api.model
    def _load_pos_data_domain(self, data):
        """
        Filtra los tipos de documento disponibles para el POS activo.
        Solo devuelve los tipos asignados al diario de facturación del config.
        """
        config = self.env['pos.config'].browse(data['config_id'])
        doc_type_ids = (
            config.invoice_journal_id.l10n_do_document_type_ids
            .mapped('l10n_latam_document_type_id').ids
        )
        return [('id', 'in', doc_type_ids)]

    @api.model
    def _load_pos_data_fields(self, config_id):
        """Campos expuestos al frontend del POS."""
        return [
            'id',
            'name',
            'doc_code_prefix',
            'l10n_do_ncf_type',
            'is_vat_required',
            'internal_type',
        ]

    def write(self, vals):
        """
        Bloquea el archivado de un tipo de documento si hay sesiones POS
        abiertas que usan el diario donde está configurado ese tipo.
        """
        if vals.get('active') is False:
            for doc_type in self:
                open_sessions = self.env['pos.session'].sudo().search([
                    ('state', '!=', 'closed'),
                    ('config_id.invoice_journal_id.l10n_do_document_type_ids'
                     '.l10n_latam_document_type_id', '=', doc_type.id),
                ])
                if open_sessions:
                    config_names = ', '.join(
                        open_sessions.mapped('config_id.name')
                    )
                    raise ValidationError(_(
                        'No puedes archivar el tipo de documento "%s" porque '
                        'está en uso por sesiones POS activas: %s'
                    ) % (doc_type.name, config_names))
        return super().write(vals)
