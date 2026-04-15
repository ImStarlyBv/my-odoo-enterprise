# Run l10n_do_electronic_invoice Tests
# =========================================
#
# This module includes tests to verify the JSON generation for DigiFact e-CF.
#
# To run the tests, execute one of the following commands:
#
# Option 1: Using Docker Compose (recommended)
# ---------------------------------------------
# docker exec -it odoo18_app python -m odoo.tests.run_tests -l l10n_do_electronic_invoice --test-tags=post_install
#
# Or more specifically:
# docker exec -it odoo18_app python odoo-bin -c /etc/odoo/odoo.conf -d <your_database> --test-enable --test-tags=l10n_do_electronic_invoice --stop-after-init
#
# Option 2: From the project root directory
# -----------------------------------------
# docker-compose exec odoo python odoo-bin -c /etc/odoo/odoo.conf -d <your_database> --test-enable --test-tags=/l10n_do_electronic_invoice:TestDigifactJsonGeneration --stop-after-init
#
# Option 3: Run a specific test method
# -------------------------------------
# docker-compose exec odoo python odoo-bin -c /etc/odoo/odoo.conf -d <your_database> --test-enable --test-tags=l10n_do_electronic_invoice.TestDigifactJsonGeneration.test_01_e31_invoice_basic --stop-after-init
#
# Replace <your_database> with your actual database name (e.g., "my-odoo-enterprise")
#
# Test Coverage
# -------------
# The test suite includes:
# 1. Basic E31 invoice (B2B) - validates complete payload structure
# 2. E32 final consumer invoice - validates NO_APLICA handling
# 3. E34 credit note - validates reference information
# 4. Multiple items - validates Items array
# 5. Validation errors - validates required fields
# 6. Payment type computation - validates auto-calculation
# 7. JSON serialization - validates payload can be serialized
# 8. Company is_live flag - validates environment toggle
# 9. Product with barcode - validates item code priority
# 10. Discount handling - validates discount blocks
# 11. Address information - validates seller/buyer addresses
# 12. Email/phone extraction - validates multiple contacts
#
