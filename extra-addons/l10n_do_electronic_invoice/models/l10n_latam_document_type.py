from odoo import models, fields, api


class L10nLatamDocumentType(models.Model):
    _inherit = 'l10n_latam.document.type'

    # -------------------------------------------------------------------------
    # Control de secuencias NCF autorizadas por la DGII
    # Solo aplica a tipos e-CF dominicanos (doc_code_prefix comienza con 'E')
    # -------------------------------------------------------------------------

    ecf_sequence_max = fields.Integer(
        string='Último NCF Autorizado (DGII)',
        default=0,
        help='Número más alto del bloque autorizado por la DGII. 0 = sin límite configurado.',
    )
    ecf_warning_threshold = fields.Integer(
        string='Alerta cuando queden menos de',
        default=50,
        help='Muestra advertencia en la factura cuando los comprobantes restantes bajan de este número.',
    )
    ecf_last_used_sequence = fields.Integer(
        string='Último NCF usado',
        compute='_compute_ecf_sequence_stats',
        help='Número más alto emitido en facturas confirmadas (empresa actual).',
    )
    ecf_remaining_sequences = fields.Integer(
        string='Comprobantes restantes',
        compute='_compute_ecf_sequence_stats',
    )
    ecf_sequence_status = fields.Selection(
        selection=[
            ('unconfigured', 'Sin configurar'),
            ('ok', 'Disponible'),
            ('low', 'Pocos disponibles'),
            ('exhausted', 'Agotado'),
        ],
        string='Estado de secuencia',
        compute='_compute_ecf_sequence_stats',
    )

    @api.depends('ecf_sequence_max', 'ecf_warning_threshold')
    def _compute_ecf_sequence_stats(self):
        company_id = self.env.company.id
        for doc_type in self:
            if not doc_type.ecf_sequence_max:
                doc_type.ecf_last_used_sequence = 0
                doc_type.ecf_remaining_sequences = 0
                doc_type.ecf_sequence_status = 'unconfigured'
                continue

            # Número más alto entre facturas confirmadas de este tipo en la empresa activa
            self.env.cr.execute("""
                SELECT COALESCE(
                    MAX(CAST(
                        REGEXP_REPLACE(l10n_latam_document_number, '^[A-Z]+[0-9]+', '')
                        AS INTEGER
                    )), 0
                )
                FROM account_move
                WHERE company_id = %s
                  AND state = 'posted'
                  AND l10n_latam_document_type_id = %s
                  AND l10n_latam_document_number ~ '^[A-Z]+[0-9]+'
            """, (company_id, doc_type.id))
            last_used = self.env.cr.fetchone()[0] or 0

            remaining = doc_type.ecf_sequence_max - last_used
            doc_type.ecf_last_used_sequence = last_used
            doc_type.ecf_remaining_sequences = max(remaining, 0)

            if remaining <= 0:
                doc_type.ecf_sequence_status = 'exhausted'
            elif remaining <= doc_type.ecf_warning_threshold:
                doc_type.ecf_sequence_status = 'low'
            else:
                doc_type.ecf_sequence_status = 'ok'
