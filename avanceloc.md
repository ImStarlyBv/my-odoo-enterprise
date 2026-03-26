# Avance Localización Dominicana (l10n_do_accounting)

## Errores Resueltos

### 1. `account_invoice_refund_views.xml` — atributo `attrs` obsoleto (Odoo 18)
**Archivo:** `extra-addons/l10n_do_accounting/wizard/account_invoice_refund_views.xml`
**Vista:** `view.account.move.reversal.inherited`

**Error:**
```
A partir de 17.0 ya no se usan los atributos "attrs" y "states".
```

**Causa:** Los campos `refund_ref` y `ncf_expiration_date` usaban el atributo `attrs` (sintaxis Odoo ≤16) para controlar visibilidad y requerimiento.

**Solución:** Reemplazar `attrs` con atributos directos de Odoo 17/18:
- `attrs="{'invisible': [('is_vendor_refund', '=', False)]}"` → `invisible="not is_vendor_refund"`
- `attrs="{'required': [('is_fiscal_refund', '=', True), ('is_vendor_refund', '=', True)]}"` → `required="is_fiscal_refund and is_vendor_refund"`
